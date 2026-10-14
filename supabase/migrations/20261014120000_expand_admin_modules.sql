-- SIGACEcyTEO: módulos administrativos para un solo plantel.
-- Aplicar una sola vez en Supabase SQL Editor o mediante Supabase CLI.
alter type public.app_role add value if not exists 'Oficios';
alter type public.app_role add value if not exists 'Constancias';
alter type public.app_role add value if not exists 'Materiales';
alter type public.app_role add value if not exists 'RedesSociales';
alter type public.app_role add value if not exists 'Inventario';
alter type public.app_role add value if not exists 'AsistenciaPersonal';
alter type public.app_role add value if not exists 'Expedientes';
alter type public.app_role add value if not exists 'Alumnos';
alter type public.app_role add value if not exists 'EquiposComputo';
alter type public.app_role add value if not exists 'Almacen';

create table if not exists public.registros_modulo (
 id uuid primary key default gen_random_uuid(),
 modulo text not null check (modulo in ('oficios','constancias','materiales','redes','inventario','asistencia','expedientes','alumnos','equipos','almacen')),
 titulo text not null,
 estado text not null default 'Pendiente',
 datos jsonb not null default '{}'::jsonb,
 creado_por uuid not null references auth.users(id) on delete restrict default auth.uid(),
 actualizado_por uuid references auth.users(id) on delete set null,
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now()
);
create index if not exists registros_modulo_modulo_fecha_idx on public.registros_modulo(modulo, created_at desc);
create index if not exists registros_modulo_datos_gin_idx on public.registros_modulo using gin(datos);
alter table public.registros_modulo enable row level security;

create table if not exists public.auditoria_eventos (
 id bigint generated always as identity primary key,
 usuario_id uuid references auth.users(id) on delete set null,
 accion text not null,
 modulo text not null,
 registro_id uuid,
 detalle jsonb not null default '{}'::jsonb,
 created_at timestamptz not null default now()
);
alter table public.auditoria_eventos enable row level security;

create or replace function public.sigace_modulo_permitido(p_modulo text)
returns boolean language sql stable security definer set search_path = ''
as $$
 select exists (
  select 1 from public.perfiles p
  where p.id_usuario=(select auth.uid()) and p.activo=true
  and (
   p.rol::text='Administrador'
   or p.rol::text='Operativo'
   or (p_modulo='oficios' and p.rol::text='Oficios')
   or (p_modulo='constancias' and p.rol::text='Constancias')
   or (p_modulo='materiales' and p.rol::text='Materiales')
   or (p_modulo='redes' and p.rol::text='RedesSociales')
   or (p_modulo='inventario' and p.rol::text='Inventario')
   or (p_modulo='asistencia' and p.rol::text='AsistenciaPersonal')
   or (p_modulo='expedientes' and p.rol::text='Expedientes')
   or (p_modulo='alumnos' and p.rol::text='Alumnos')
   or (p_modulo='equipos' and p.rol::text='EquiposComputo')
   or (p_modulo='almacen' and p.rol::text='Almacen')
  )
 )
$$;
revoke all on function public.sigace_modulo_permitido(text) from public, anon;
grant execute on function public.sigace_modulo_permitido(text) to authenticated;

drop policy if exists "module users read permitted records" on public.registros_modulo;
create policy "module users read permitted records" on public.registros_modulo for select to authenticated
using (public.sigace_modulo_permitido(modulo));
drop policy if exists "module users create permitted records" on public.registros_modulo;
create policy "module users create permitted records" on public.registros_modulo for insert to authenticated
with check (public.sigace_modulo_permitido(modulo) and creado_por=(select auth.uid()));
drop policy if exists "module users update permitted records" on public.registros_modulo;
create policy "module users update permitted records" on public.registros_modulo for update to authenticated
using (public.sigace_modulo_permitido(modulo)) with check (public.sigace_modulo_permitido(modulo));
drop policy if exists "admins delete module records" on public.registros_modulo;
create policy "admins delete module records" on public.registros_modulo for delete to authenticated
using (exists(select 1 from public.perfiles p where p.id_usuario=(select auth.uid()) and p.activo=true and p.rol::text='Administrador'));

drop policy if exists "users read own audit events" on public.auditoria_eventos;
create policy "users read own audit events" on public.auditoria_eventos for select to authenticated
using (usuario_id=(select auth.uid()) or exists(select 1 from public.perfiles p where p.id_usuario=(select auth.uid()) and p.activo=true and p.rol::text='Administrador'));
drop policy if exists "users create audit events" on public.auditoria_eventos;
create policy "users create audit events" on public.auditoria_eventos for insert to authenticated
with check (usuario_id=(select auth.uid()));
grant select, insert, update, delete on public.registros_modulo to authenticated;
grant select, insert on public.auditoria_eventos to authenticated;
grant usage, select on sequence public.auditoria_eventos_id_seq to authenticated;

create or replace function public.sigace_touch_updated_at()
returns trigger language plpgsql set search_path = ''
as $$ begin new.updated_at=now(); new.actualizado_por=auth.uid(); return new; end $$;
drop trigger if exists registros_modulo_touch on public.registros_modulo;
create trigger registros_modulo_touch before update on public.registros_modulo
for each row execute function public.sigace_touch_updated_at();
