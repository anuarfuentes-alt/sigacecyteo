# SIGACEcyTEO — demostración de 3 laptops

## Qué necesitas
- Python 3.10+ instalado en la laptop servidor.
- Las tres laptops en la misma red Wi-Fi.
- No requiere pip, Supabase ni conexión a Internet para la demostración.

## Laptop 1: servidor
Desde la raíz del repositorio:
```powershell
python demo/computer_lab_demo.py
```
En Linux:
```bash
python3 demo/computer_lab_demo.py
```
En esa laptop abre http://127.0.0.1:8080.

## Laptop 2 y 3: equipos cliente
En la laptop servidor ejecuta `ipconfig` en Windows y localiza la IPv4 del adaptador Wi-Fi. En Linux ejecuta `hostname -I`. Desde las otras laptops abre `http://IP-DEL-SERVIDOR:8080` sustituyendo por la IP real, por ejemplo `http://192.168.1.20:8080`. Si Windows Firewall pregunta, permite Python únicamente en redes privadas. No abras el puerto a Internet.

Credenciales ficticias: matrículas `2026001` y `2026002`; contraseña para ambas: `cecyte123`. Usa una matrícula por laptop para mostrar dos sesiones simultáneas: laptop 2 con 2026001/LAB-01 y laptop 3 con 2026002/LAB-02.

## Guion sugerido
1. Panel encargado en laptop 1.
2. Login en LAB-01 desde laptop 2 y muestra el cambio de estado y la bitácora.
3. Reporta una falla desde el cliente y muestra la incidencia en el panel.
4. Demuestra el cierre remoto y exporta el CSV que puede abrir Excel.
5. En laptop 3 prueba LAB-02; para la demo, la misma matrícula no puede tener dos sesiones activas, así que cierra primero la sesión anterior.

## Alcance y seguridad
Esto es una demo educativa independiente del backend de producción y guarda datos ficticios en `demo/demo.sqlite3`. El bloqueo es una simulación de interfaz: no bloquea realmente el sistema operativo. El panel utiliza un token administrativo fijo para simplificar la presentación. No introducir información real ni exponer este servidor a Internet. QR/cámara, agente nativo, bloqueo seguro, WebSocket productivo, modo offline cifrado, permisos y PDF/XLSX siguen pendientes.
