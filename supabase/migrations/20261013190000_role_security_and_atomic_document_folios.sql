-- SIGACEcyTEO: role-aware RLS and atomic folio reservation.
-- Review this migration against the current production schema before re-applying.
create or replace function public.current_app_role()
returns public.app_role language sql stable security definer set search_path = ''
as $$
  select p.rol from public.perfiles p
  where p.id_usuario = (select auth.uid()) and p.activo = true limit 1
$$;
revoke all on function public.current_app_role() from public;
grant execute on function public.current_app_role() to authenticated;

do $$
declare r record;
begin
  for r in select schemaname, tablename, policyname from pg_policies
    where schemaname = 'public' and tablename in
    ('grupos_especialidades','alumnos','materias','historial_academico','perfiles','plantillas','contadores_folios','documentos_emitidos')
  loop execute format('drop policy if exists %I on %I.%I',r.policyname,r.schemaname,r.tablename); end loop;
end $$;

create policy "active users read groups" on public.grupos_especialidades for select to authenticated
using (public.current_app_role() in ('Administrador','Operativo'));
create policy "admins manage groups" on public.grupos_especialidades for all to authenticated
using (public.current_app_role()='Administrador') with check (public.current_app_role()='Administrador');
create policy "active users read students" on public.alumnos for select to authenticated
using (public.current_app_role() in ('Administrador','Operativo'));
create policy "admins manage students" on public.alumnos for all to authenticated
using (public.current_app_role()='Administrador') with check (public.current_app_role()='Administrador');
create policy "active users read subjects" on public.materias for select to authenticated
using (public.current_app_role() in ('Administrador','Operativo'));
create policy "admins manage subjects" on public.materias for all to authenticated
using (public.current_app_role()='Administrador') with check (public.current_app_role()='Administrador');
create policy "active users read academic history" on public.historial_academico for select to authenticated
using (public.current_app_role() in ('Administrador','Operativo'));
create policy "admins manage academic history" on public.historial_academico for all to authenticated
using (public.current_app_role()='Administrador') with check (public.current_app_role()='Administrador');
create policy "users read own profile" on public.perfiles for select to authenticated using (id_usuario=(select auth.uid()));
create policy "admins read all profiles" on public.perfiles for select to authenticated using (public.current_app_role()='Administrador');
create policy "admins manage profiles" on public.perfiles for all to authenticated
using (public.current_app_role()='Administrador') with check (public.current_app_role()='Administrador');
create policy "active users read templates" on public.plantillas for select to authenticated
using (public.current_app_role() in ('Administrador','Operativo'));
create policy "admins manage templates" on public.plantillas for all to authenticated
using (public.current_app_role()='Administrador') with check (public.current_app_role()='Administrador');
create policy "admins read folio counters" on public.contadores_folios for select to authenticated
using (public.current_app_role()='Administrador');
create policy "active users read issued docs" on public.documentos_emitidos for select to authenticated
using (public.current_app_role() in ('Administrador','Operativo'));

create unique index if not exists contadores_folios_tipo_ciclo_uidx
on public.contadores_folios(tipo_documento,ciclo_fiscal);

create or replace function public.emitir_documento(
 p_tipo public.document_type, p_ciclo_fiscal text,
 p_prefijo text default 'CECYTEO/P14/DIR', p_id_alumno uuid default null,
 p_datos jsonb default '{}'::jsonb
) returns table(id_documento uuid, folio_asignado text, numero_folio bigint, fecha_emision timestamptz)
language plpgsql security definer set search_path = ''
as $$
declare v_uid uuid:=auth.uid(); v_num bigint; v_folio text; v_id uuid; v_fecha timestamptz;
begin
 if v_uid is null then raise exception 'Se requiere una sesión autenticada' using errcode='28000'; end if;
 if not exists(select 1 from public.perfiles p where p.id_usuario=v_uid and p.activo=true and p.rol in ('Administrador','Operativo')) then
   raise exception 'Usuario sin permisos para emitir documentos' using errcode='42501';
 end if;
 if p_ciclo_fiscal is null or length(trim(p_ciclo_fiscal))=0 or length(p_ciclo_fiscal)>20 then
   raise exception 'Ciclo fiscal inválido' using errcode='22023';
 end if;
 if p_prefijo is null or p_prefijo !~ '^[A-Za-z0-9/-]{1,60}$' then raise exception 'Prefijo de folio inválido' using errcode='22023'; end if;
 if p_id_alumno is not null and not exists(select 1 from public.alumnos a where a.id_alumno=p_id_alumno) then
   raise exception 'El alumno no existe' using errcode='22023';
 end if;
 insert into public.contadores_folios(tipo_documento,ciclo_fiscal,prefijo,ultimo_numero)
 values(p_tipo,trim(p_ciclo_fiscal),p_prefijo,1)
 on conflict(tipo_documento,ciclo_fiscal) do update
 set ultimo_numero=public.contadores_folios.ultimo_numero+1,prefijo=excluded.prefijo
 returning ultimo_numero into v_num;
 v_folio:=p_prefijo||'/'||lpad(v_num::text,3,'0')||'/'||trim(p_ciclo_fiscal);
 insert into public.documentos_emitidos(folio_asignado,numero_folio,ciclo_fiscal,tipo_documento,id_alumno,id_usuario_emisor,datos_documento)
 values(v_folio,v_num,trim(p_ciclo_fiscal),p_tipo,p_id_alumno,v_uid,coalesce(p_datos,'{}'::jsonb))
 returning public.documentos_emitidos.id_documento,public.documentos_emitidos.fecha_emision into v_id,v_fecha;
 return query select v_id,v_folio,v_num,v_fecha;
end $$;
revoke all on function public.emitir_documento(public.document_type,text,text,uuid,jsonb) from public,anon;
grant execute on function public.emitir_documento(public.document_type,text,text,uuid,jsonb) to authenticated;
revoke insert,update,delete on public.contadores_folios from anon,authenticated;
revoke insert,update,delete on public.documentos_emitidos from anon,authenticated;
