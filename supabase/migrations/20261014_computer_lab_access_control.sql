-- Aplicar en el proyecto Supabase existente. Idempotente.
create extension if not exists pgcrypto;
create table if not exists public.cc_credenciales (
 id uuid primary key default gen_random_uuid(),
 id_alumno uuid not null unique references public.alumnos(id_alumno) on delete cascade,
 password_hash text,
 qr_token_hash text unique,
 activo boolean not null default true,
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now(),
 constraint cc_credenciales_medio_check check (password_hash is not null or qr_token_hash is not null)
);
create table if not exists public.cc_equipos (
 id uuid primary key default gen_random_uuid(), codigo text not null unique, nombre text not null,
 ubicacion text not null default 'Centro de cómputo', sistema_operativo text, agente_version text,
 estado text not null default 'libre' check (estado in ('libre','en_uso','fuera_servicio','sin_conexion')),
 ultima_conexion timestamptz, telemetria jsonb not null default '{}'::jsonb, habilitado boolean not null default true,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
alter table public.cc_equipos add column if not exists agent_key_hash text;
create table if not exists public.cc_sesiones (
 id uuid primary key default gen_random_uuid(), id_alumno uuid not null references public.alumnos(id_alumno),
 id_equipo uuid not null references public.cc_equipos(id), hora_inicio timestamptz not null default now(), hora_fin timestamptz,
 estado text not null default 'activa' check (estado in ('activa','cerrada','cerrada_por_inactividad','cerrada_remotamente')),
 metodo_acceso text not null check (metodo_acceso in ('matricula_password','qr')),
 alertas_hardware jsonb not null default '[]'::jsonb, created_at timestamptz not null default now()
);
create unique index if not exists cc_unica_sesion_activa_equipo on public.cc_sesiones(id_equipo) where hora_fin is null;
create index if not exists cc_sesiones_hora_inicio_idx on public.cc_sesiones(hora_inicio desc);
create index if not exists cc_sesiones_alumno_idx on public.cc_sesiones(id_alumno, hora_inicio desc);
create table if not exists public.cc_incidentes (
 id uuid primary key default gen_random_uuid(), id_equipo uuid references public.cc_equipos(id), id_alumno uuid references public.alumnos(id_alumno),
 id_sesion uuid references public.cc_sesiones(id), categoria text not null, descripcion text not null,
 prioridad text not null default 'media' check (prioridad in ('baja','media','alta','critica')),
 estado text not null default 'abierto' check (estado in ('abierto','en_atencion','resuelto','descartado')),
 telemetria jsonb not null default '{}'::jsonb, atendido_por uuid references public.perfiles(id_usuario),
 created_at timestamptz not null default now(), resolved_at timestamptz
);
create table if not exists public.cc_comandos (
 id uuid primary key default gen_random_uuid(), id_equipo uuid not null references public.cc_equipos(id) on delete cascade,
 comando text not null check (comando in ('bloquear','cerrar_sesion','actualizar_estado')), parametros jsonb not null default '{}'::jsonb,
 solicitado_por uuid references public.perfiles(id_usuario), solicitado_at timestamptz not null default now(), ejecutado_at timestamptz, resultado jsonb
);
alter table public.cc_credenciales enable row level security;
alter table public.cc_equipos enable row level security;
alter table public.cc_sesiones enable row level security;
alter table public.cc_incidentes enable row level security;
alter table public.cc_comandos enable row level security;
revoke all on public.cc_credenciales, public.cc_equipos, public.cc_sesiones, public.cc_incidentes, public.cc_comandos from anon, authenticated;
grant all on public.cc_credenciales, public.cc_equipos, public.cc_sesiones, public.cc_incidentes, public.cc_comandos to service_role;
