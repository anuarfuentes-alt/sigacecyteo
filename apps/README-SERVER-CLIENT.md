# SIGACEcyTEO — aplicaciones de servidor y cliente

Esta carpeta agrega **dos aplicaciones separadas** al repositorio existente:

- `apps/server`: API central FastAPI, panel web de encargado, PostgreSQL, bitácora, incidencias, telemetría, códigos QR de un solo uso, comandos remotos por WebSocket y exportación CSV/Excel/PDF.
- `apps/client`: aplicación de escritorio para cada computadora Windows del laboratorio, con acceso por matrícula/contraseña, lectura QR opcional, reporte de fallas, telemetría, cierre automático por inactividad, comandos remotos y cola offline cifrada.

No se creó un proyecto GitHub ni un proyecto Supabase nuevos. Esta implementación es independiente del demostrador anterior `demo/computer_lab_demo.py`; puedes conservar la demo que presentaste.

## Estado y límites importantes

El código es una **base funcional para instalación piloto**, no debe anunciarse como producción certificada hasta completar pruebas de instalación, seguridad y carga.

- El servidor usa PostgreSQL si `DATABASE_URL` apunta a PostgreSQL. Para pruebas rápidas permite SQLite, pero SQLite no se recomienda para una instalación real multiusuario.
- La contraseña se almacena como hash PBKDF2-HMAC-SHA256 con sal; no se guarda en texto plano.
- El QR emitido por el panel es de un solo uso y vence en 90 segundos.
- El cliente reporta hostname, IP, sistema operativo y uso de CPU/RAM/disco si `psutil` está disponible.
- El modo offline permite entrar solo a una persona que inició sesión en línea previamente en ese cliente; almacena credenciales cacheadas y cola local cifradas con Fernet. En Windows, la clave de Fernet se protege usando DPAPI para el usuario actual; no copies el archivo de datos a otra cuenta o PC. El primer acceso necesita conexión al servidor. La credencial se mantiene en memoria solo durante la sesión offline para reintentar la autenticación; no se escribe la contraseña en disco.
- La cola se sincroniza al recuperar conectividad y autenticar nuevamente. Los eventos de incidente incluyen identificadores para reducir duplicados.
- Los comandos “Cerrar sesión” y “Bloquear app” actúan sobre la sesión/interfaz de SIGACEcyTEO. **No son un bloqueo seguro de Windows**. Para impedir salir a otras aplicaciones se debe desplegar Windows Assigned Access/modo quiosco y una cuenta de laboratorio restringida.
- El servicio se configura con HTTP en la LAN para facilitar el piloto. Para operar con matrículas reales en una red compartida, configura HTTPS/WSS, limita la red/firewall, gestiona secretos, backups y actualizaciones.
- La tabla de base de datos se crea al iniciar con SQLAlchemy. Antes de producción, hay que formalizar migraciones, backups y pruebas de restauración.
- La lectura QR requiere cámara y el extra `opencv-python` instalado en el cliente.
- El servidor requiere que su administrador inicial se configure en `.env`. No hay contraseña administrativa predeterminada segura.

## A. Instalar el servidor central en Windows 11

### 1. Preparar PostgreSQL (recomendado)

Instala PostgreSQL en la laptop que será servidor. En pgAdmin o psql, crea usuario y base de datos, cambiando la contraseña de ejemplo:

```sql
CREATE USER sigacecyteo WITH PASSWORD 'CAMBIA_ESTA_CLAVE_DB';
CREATE DATABASE sigacecyteo OWNER sigacecyteo;
```

Si ya tienes un servidor PostgreSQL administrado, crea ahí una base y usuario equivalentes y usa su dirección segura.

### 2. Preparar Python y la configuración

Instala Python 3.11 o posterior para Windows. Abre `apps\\server` y copia `.env.example` como `.env`. Edita `.env`:

- Cambia `SIGA_ADMIN_PASSWORD` por una contraseña única y larga.
- Cambia `CAMBIAR_CLAVE_DB` en `DATABASE_URL` por la contraseña PostgreSQL.
- Mantén `SIGA_SEED_DEMO=false` en una instalación real.
- Para la prueba de laboratorio puedes usar `SIGA_SEED_DEMO=true`, que crea `2026001 / cecyte123` y `2026002 / cecyte123`. Cámbialas antes de introducir datos reales.

Si necesitas primero una prueba sin PostgreSQL, solo en el `.env` de prueba cambia `DATABASE_URL` a:

```text
DATABASE_URL=sqlite:///./sigacecyteo_dev.db
```

SQLite es para prueba local; usa PostgreSQL para la instalación central del plantel.

### 3. Arrancar el servidor

Doble clic en `apps\\server\\start_server.bat`. El script crea un entorno virtual, instala dependencias y arranca el servicio en puerto 8080.

Desde el navegador del servidor abre:

- Panel de encargado: `http://127.0.0.1:8080`
- Comprobación técnica: `http://127.0.0.1:8080/api/health`

El primer administrador se toma de `SIGA_ADMIN_USER` y `SIGA_ADMIN_PASSWORD`. Las tablas se crean en el primer arranque.

### 4. Permitir clientes por la LAN

En Windows, marca la red Wi-Fi como **Privada** solo si es tu router de confianza. Abre PowerShell como administrador y aplica una regla restringida a la subred local:

```powershell
New-NetFirewallRule -DisplayName "SIGACEcyTEO-8080-LAN" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8080 -Profile Private -RemoteAddress LocalSubnet
```

Ejecuta `ipconfig` y anota la IPv4 del adaptador Wi-Fi (por ejemplo `192.168.0.235`). No configures port-forwarding del router ni expongas el puerto a Internet.

## B. Preparar cada cliente Windows 10/11

Copia la carpeta `apps\\client` a cada PC de laboratorio o usa el ejecutable creado con el paso de compilación siguiente.

1. Instala Python 3.11 o posterior si ejecutarás el código fuente.
2. Desde `apps\\client`, ejecuta `run_client.bat` o `py client.py`.
3. En el formulario indica `http://IP-DEL-SERVIDOR:8080` y un código de equipo único, por ejemplo `LAB-01` o `LAB-02`.
4. Inicia sesión con una matrícula y contraseña existentes. El administrador puede dar de alta alumnos desde el panel.
5. Usa “Reportar falla” para enviar una incidencia al servidor.
6. La aplicación informa telemetría y revisa comandos durante la sesión. El cierre de sesión de SIGACEcyTEO por inactividad está configurado a 15 minutos; cambia la variable `SIGA_IDLE_MINUTES` antes de arrancar para otro valor. El bloqueo nativo de Windows está habilitado por defecto con `SIGA_NATIVE_WINDOWS_LOCK=true`. Para una prueba controlada en la que no quieras bloquear el sistema operativo, inicia desde PowerShell con `$env:SIGA_NATIVE_WINDOWS_LOCK="false"; py client.py` (o establece esa variable antes de ejecutar el EXE).

### QR con cámara

Instala el paquete opcional en el cliente:

```bat
python -m pip install -r requirements-qr.txt
```

En el panel del servidor, genera un QR para una matrícula activa. Es de un solo uso y dura 90 segundos. En el cliente usa “Leer QR con cámara”.

### Crear el ejecutable cliente

En Windows, entra a `apps\\client` y ejecuta `build_client.bat`. El ejecutable queda en:

```text
apps\\client\\dist\\SIGACEcyTEOCliente.exe
```

Distribuye el ejecutable y conserva los archivos de configuración/documentación. Haz una prueba piloto con una cuenta sin permisos administrativos antes de instalarlo en todas las máquinas. Windows puede mostrar una advertencia de SmartScreen porque el ejecutable no está firmado.

## C. Prueba de aceptación del plantel

1. Inicia el servidor y abre el panel de encargado.
2. En dos PCs clientes, inicia sesión con alumnos diferentes y equipos distintos.
3. Confirma que aparecen las dos sesiones, equipos y telemetría.
4. Envía una incidencia desde un cliente; resuélvela desde el panel.
5. Genera un QR temporal para un alumno de prueba y accede con cámara.
6. Envía “Cerrar sesión” y confirma que el cliente vuelve al formulario.
7. Envía “Bloquear app” y “Desbloquear app”; confirma que se restringe la interfaz de la aplicación. No prueba un bloqueo de Windows.
8. Exporta CSV, Excel y PDF y verifica su contenido.
9. Desconecta un cliente de la red, prueba un usuario previamente cacheado, crea un reporte y reconecta. Comprueba que sincroniza la cola offline.
10. Reinicia servidor y PostgreSQL y comprueba que la bitácora persiste y que se puede restaurar una copia de seguridad.

## D. Endurecimiento pendiente para producción

Antes de registrar datos personales reales, añadir/validar: HTTPS/WSS con certificado, control de sesiones persistente y revocación, limitación de intentos de login, política de contraseñas/recuperación, sincronización offline transaccional e idempotente probada, cifrado de clave offline con Windows DPAPI, auditoría inmutable, backups probados, migraciones versionadas, instalación y actualización firmadas, modo quiosco del sistema operativo, pruebas de desconexión/duplicados/carga, retención de datos y aviso de privacidad del plantel.

## Carpetas

- `apps/server/server.py` — servidor web y API.
- `apps/server/.env.example` — variables de entorno de referencia.
- `apps/server/start_server.bat` — instalación/arranque.
- `apps/client/client.py` — aplicación de escritorio.
- `apps/client/run_client.bat` — ejecución desde Python.
- `apps/client/build_client.bat` — compilación a EXE.
