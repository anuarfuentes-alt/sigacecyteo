# SIGACEcyTEO — Control de acceso a centros de cómputo

Primera iteración del backend de acceso para integrarse al repositorio y proyecto Supabase existentes. No crea un proyecto independiente.

## Componentes
- `backend/main.py`: API FastAPI para autenticación por matrícula/contraseña o QR, sesiones, telemetría e incidencias.
- `supabase/migrations/20261014_computer_lab_access_control.sql`: tablas del módulo.
- Cliente de escritorio: debe ejecutarse como agente de kiosco con instalación y políticas del sistema operativo. La API no pretende reemplazar GPO/AppLocker ni el bloqueo seguro del sistema operativo.

## Configuración backend
Python 3.11+ recomendado.

```bash
cd backend
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
```

Variables requeridas:
- `SUPABASE_URL`: URL del proyecto Supabase actual.
- `SUPABASE_SERVICE_ROLE_KEY`: secreto de servidor exclusivamente; nunca usar en el navegador ni distribuir al agente.
- `IDLE_TIMEOUT_SECONDS`: tiempo de inactividad (por defecto 600).
- `CORS_ORIGINS`: orígenes exactos, separados por coma, si el panel web necesita acceder a la API.

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

## Preparación de datos
1. Aplicar la migración en el proyecto Supabase actual.
2. Registrar cada equipo en `public.cc_equipos` con código único y un `agent_key_hash` igual a SHA-256 de una clave aleatoria robusta. La clave en texto claro se entrega solo al agente de ese equipo por un canal seguro.
3. Asociar credenciales a alumnos existentes en `public.cc_credenciales`. Guardar contraseñas con bcrypt desde un proceso administrativo seguro; jamás guardar contraseñas en claro. Para QR, guardar SHA-256 del token aleatorio, no el token en claro.
4. Confirmar las políticas de acceso y crear una ruta administrativa protegida para alta/baja de equipos y alumnos antes del piloto.

## Endpoints iniciales
- `GET /health`
- `POST /api/v1/login`
- `POST /api/v1/sessions/end`
- `POST /api/v1/incidents`
- `POST /api/v1/telemetry`
- `WS /api/v1/ws/{equipo_codigo}?agent_key=...`

Las solicitudes de agente requieren `X-Agent-Key` y, excepto login, `X-Equipo-Codigo`.

## Importante antes del despliegue escolar
Este backend es una base de implementación, no una certificación de seguridad ni un agente de kiosco completo. Falta construir y probar el instalador/servicio de Windows y Linux, captura de inactividad, cifrado local con claves gestionadas por el sistema operativo, reconexión y sincronización offline, interfaz de bloqueo/QR, panel de administración en vivo, exportación PDF/XLSX y pruebas de carga/seguridad. El agente no debe intentar deshabilitar Ctrl+Alt+Supr, evadir controles de seguridad ni bloquear la recuperación administrativa del sistema; aplicar modo kiosco mediante Assigned Access/GPO/AppLocker o herramientas equivalentes autorizadas.
