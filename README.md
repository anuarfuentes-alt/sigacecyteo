# SIGACEcyTEO

Aplicación React + Vite para gestión escolar conectada con Supabase.

## Ejecutar localmente
1. Instala Node.js 20 o superior.
2. Copia `.env.example` a `.env.local` y configura `VITE_SUPABASE_URL` y `VITE_SUPABASE_ANON_KEY` con los valores publicables de tu proyecto Supabase.
3. Ejecuta `npm install` y `npm run dev`.
4. Para validar producción: `npm run build`.

## Autenticación y roles
El login usa Supabase Auth. Cada usuario debe tener una fila en `public.perfiles` con `id_usuario` igual al UUID de Auth, un `rol` ('Administrador' u 'Operativo') y `activo=true`. No se crea un administrador automáticamente; asigna el primer rol desde un proceso administrativo seguro.

## Supabase
La aplicación consulta `alumnos`, `documentos_emitidos`, `plantillas` y `perfiles`. Las políticas RLS son obligatorias. El cliente solo debe usar la clave publicable (anon/publishable), nunca una service_role key.

La migración de referencia está en `supabase/migrations/20261013190000_role_security_and_atomic_document_folios.sql`. Esta migración aplica políticas de rol y un RPC transaccional para reservar folios. Antes de volver a ejecutarla en otra base de datos, verifica que los tipos, columnas y restricciones coincidan con el esquema actual. La migración fue aplicada en el proyecto Supabase conectado durante la preparación.

La Edge Function fuente se encuentra en `supabase/functions/emitir-pdf/index.ts`. Valida JWT y rol, invoca el RPC `emitir_documento` y devuelve un PDF básico. El formato es una plantilla de arranque, no un formato oficial certificado. Configura el secreto `APP_ORIGIN` con el dominio exacto de producción para restringir CORS.

## Despliegue en Vercel
Importa el repositorio desde Vercel y selecciona el framework Vite, directorio raíz `.`, comando de build `npm run build` y directorio de salida `dist`. Configura las variables de entorno anteriores en Preview y Production y despliega. Aún deben realizarse pruebas de permisos, formatos institucionales, citatorios masivos y reinicio de folios según la normativa del plantel antes del uso oficial.
