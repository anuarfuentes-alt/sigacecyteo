#!/usr/bin/env python3
"""Demo local SIGACEcyTEO para exposición. No usar en producción."""
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from datetime import datetime, timezone
import sqlite3, json, os, secrets
HOST, PORT = "0.0.0.0", int(os.getenv("SIGA_PORT", "8080"))
DB = Path(__file__).with_name("demo.sqlite3")
USERS = {"2026001": "Alumno de demostración 1", "2026002": "Alumno de demostración 2"}
PASSWORD = "cecyte123"
ADMIN_TOKEN = "demo-admin-cambiar"
def now(): return datetime.now(timezone.utc).isoformat(timespec="seconds")
def db():
    c=sqlite3.connect(DB,timeout=10); c.row_factory=sqlite3.Row; return c
def init():
    with db() as c:
        c.executescript("""CREATE TABLE IF NOT EXISTS equipos(codigo TEXT PRIMARY KEY,estado TEXT NOT NULL DEFAULT 'Libre');
        CREATE TABLE IF NOT EXISTS sesiones(id INTEGER PRIMARY KEY AUTOINCREMENT,matricula TEXT,nombre TEXT,equipo TEXT,inicio TEXT,fin TEXT,estado TEXT);
        CREATE TABLE IF NOT EXISTS fallas(id INTEGER PRIMARY KEY AUTOINCREMENT,equipo TEXT,matricula TEXT,categoria TEXT,descripcion TEXT,hora TEXT,estado TEXT DEFAULT 'Abierta');
        CREATE TABLE IF NOT EXISTS comandos(id INTEGER PRIMARY KEY AUTOINCREMENT,equipo TEXT,comando TEXT,consumido INTEGER DEFAULT 0);""")
        for e in ("LAB-01","LAB-02"): c.execute("INSERT OR IGNORE INTO equipos(codigo) VALUES(?)",(e,))
PAGE = r"""<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SIGACEcyTEO Demo</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#f2f5fa;color:#182b45;font:16px Segoe UI,Arial}header{background:#12345b;color:white;padding:22px 5%;display:flex;justify-content:space-between;flex-wrap:wrap}main{max-width:1100px;margin:24px auto;padding:0 16px}.warn{padding:13px;background:#fff3cf;border:1px solid #ebd18a;border-radius:10px;margin-bottom:18px}.tabs,.row{display:flex;gap:9px;flex-wrap:wrap;align-items:center;margin-bottom:14px}button,select,input,textarea{font:inherit;padding:11px;border:1px solid #ccd6e5;border-radius:8px}button{cursor:pointer;background:#e4ebf5;color:#17385f;border:0;font-weight:650}.on{background:#175cd3;color:white}.danger{background:#b42318;color:white}.card{background:white;border:1px solid #e0e7f0;border-radius:13px;padding:17px;margin-bottom:14px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px}.kpi{font-size:30px;font-weight:800}.muted{font-size:13px;color:#66768b}h2{font-size:20px;margin-top:0}label{display:block;font-weight:650;font-size:13px;margin:12px 0 5px}input,select,textarea{width:100%;background:white}.form{max-width:500px;margin:auto}.tag{display:inline-block;background:#e1f5e8;color:#17643a;border-radius:20px;padding:4px 9px;font-size:12px;font-weight:750}.busy{background:#fff0d6;color:#815000}.table{overflow:auto}table{width:100%;border-collapse:collapse;font-size:13px}td,th{text-align:left;padding:10px;border-bottom:1px solid #e6ebf2;white-space:nowrap}.hidden{display:none!important}.flash{margin-top:12px;padding:10px;background:#e1f5e8;border-radius:8px}.hero{text-align:center;padding:12px}.hero b{font-size:38px}.foot{text-align:center;color:#77869a;font-size:12px;padding:18px}
</style><header><div><b style="font-size:23px">SIGACEcyTEO</b><div class="muted" style="color:#c8d9ed">Control de acceso y bitácora · demostrador local</div></div><b>CECyTEO · Centro de cómputo</b></header><main>
<div class="warn"><b>Modo demostración:</b> datos ficticios en SQLite local. El bloqueo remoto es una simulación visual, no bloquea Windows/Linux. No usar datos personales reales.</div>
<div class="tabs"><button class="on" onclick="view('admin',this)">Panel encargado</button><button onclick="view('client',this)">Equipo alumno</button><button onclick="view('guide',this)">Guion de presentación</button></div>
<section id="admin"><div class="grid" id="kpis"></div><div class="card"><h2>Equipos del laboratorio</h2><div class="grid" id="equipos"></div></div><div class="card"><h2>Incidencias</h2><div class="table"><table><thead><tr><th>Hora</th><th>Equipo</th><th>Alumno</th><th>Falla</th><th>Estado</th><th></th></tr></thead><tbody id="fallas"></tbody></table></div></div><div class="card"><h2>Bitácora de sesiones</h2><div class="table"><table><thead><tr><th>ID</th><th>Matrícula</th><th>Alumno</th><th>Equipo</th><th>Inicio</th><th>Fin</th><th>Estado</th></tr></thead><tbody id="sesiones"></tbody></table></div><button onclick="csv()">Exportar bitácora CSV</button></div></section>
<section id="client" class="hidden"><div class="card form"><div class="hero"><b>🖥️</b><h2>Acceso al centro de cómputo</h2><div class="muted">Interfaz de prueba del alumno</div></div><div id="login"><label>Equipo</label><select id="equipo"><option>LAB-01</option><option>LAB-02</option></select><label>Matrícula</label><input id="mat" value="2026001"><label>Contraseña de prueba</label><input id="pass" type="password" value="cecyte123"><button class="on" style="width:100%;margin-top:14px" onclick="login()">Iniciar sesión</button><p class="muted">Demo: 2026001 o 2026002 / cecyte123</p></div><div id="activa" class="hidden"><div class="flash">Sesión activa</div><h3 id="bienvenida"></h3><p class="muted" id="detalle"></p><label>Tipo de falla</label><select id="categoria"><option>Teclado dañado</option><option>Mouse descompuesto</option><option>Sin acceso a internet</option><option>Falla de monitor</option><option>Problema de software</option></select><label>Descripción</label><textarea id="descripcion" rows="3" placeholder="Describe el problema"></textarea><button class="on" onclick="reportar()">Reportar falla</button> <button class="danger" onclick="logout()">Cerrar sesión</button></div><div id="msg"></div></div></section>
<section id="guide" class="hidden card"><h2>Guion de 3 a 5 minutos</h2><ol><li>Enseña el panel en la laptop servidor.</li><li>En la laptop 2 abre la IP del servidor, entra a Equipo alumno e inicia sesión en LAB-01.</li><li>Vuelve al panel: LAB-01 cambia a En uso y aparece la bitácora.</li><li>Reporta “Sin acceso a internet” y muestra la incidencia en vivo.</li><li>En el panel prueba cerrar sesión remotamente y exporta CSV.</li><li>En la laptop 3 repite el acceso en LAB-02; usa una sesión distinta, cerrando primero la anterior.</li><li>Explica como siguiente fase el QR real, el agente de kiosco y el modo offline cifrado.</li></ol><div class="warn">Todas las laptops deben estar en la misma Wi-Fi. En otras laptops abre http://IP-DEL-SERVIDOR:8080. En Windows ejecuta ipconfig para ver la IPv4 del Wi-Fi.</div></section>
<div class="foot">Prototipo académico · no es aún una solución productiva</div></main>
<script>
let sid=null,eq='LAB-01';const $=x=>document.getElementById(x),token='demo-admin-cambiar';
function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
async function req(p,b){let r=await fetch(p,{method:b?'POST':'GET',headers:{'Content-Type':'application/json','X-Admin-Token':token},body:b?JSON.stringify(b):undefined}),d=await r.json();if(!r.ok)throw Error(d.error||'Error');return d}
function view(v,b){['admin','client','guide'].forEach(x=>$(x).classList.toggle('hidden',x!==v));document.querySelectorAll('.tabs button').forEach(x=>x.classList.remove('on'));b.classList.add('on');if(v==='admin')refresh()}
async function refresh(){try{let d=await req('/api/state');$('kpis').innerHTML=[['Equipos',d.equipos.length],['Sesiones activas',d.sesiones.filter(x=>!x.fin).length],['Equipos libres',d.equipos.filter(x=>x.estado==='Libre').length],['Fallas abiertas',d.fallas.filter(x=>x.estado==='Abierta').length]].map(x=>'<div class="card"><div class="muted">'+x[0]+'</div><div class="kpi">'+x[1]+'</div></div>').join('');$('equipos').innerHTML=d.equipos.map(e=>`<div class="card"><div class="row"><b>${esc(e.codigo)}</b><span class="tag ${e.estado==='En uso'?'busy':''}">${esc(e.estado)}</span></div><button data-equipo="${esc(e.codigo)}" data-comando="cerrar">Cerrar sesión</button> <button data-equipo="${esc(e.codigo)}" data-comando="bloquear">Bloquear demo</button></div>`).join('');document.querySelectorAll('#equipos button[data-comando]').forEach(btn=>btn.onclick=()=>remote(btn.dataset.equipo,btn.dataset.comando));$('fallas').innerHTML=d.fallas.map(f=>'<tr><td>'+new Date(f.hora).toLocaleTimeString()+'</td><td>'+esc(f.equipo)+'</td><td>'+esc(f.matricula)+'</td><td>'+esc(f.categoria+': '+f.descripcion)+'</td><td>'+esc(f.estado)+'</td><td>'+(f.estado==='Abierta'?'<button onclick="resolver('+f.id+')">Resolver</button>':'')+'</td></tr>').join('')||'<tr><td colspan="6">Sin incidencias</td></tr>';$('sesiones').innerHTML=d.sesiones.map(s=>'<tr><td>'+s.id+'</td><td>'+esc(s.matricula)+'</td><td>'+esc(s.nombre)+'</td><td>'+esc(s.equipo)+'</td><td>'+new Date(s.inicio).toLocaleString()+'</td><td>'+(s.fin?new Date(s.fin).toLocaleString():'—')+'</td><td>'+esc(s.estado)+'</td></tr>').join('')||'<tr><td colspan="7">Sin sesiones</td></tr>'}catch(e){console.error(e)}}
async function login(){eq=$('equipo').value;try{let d=await req('/api/login',{equipo:eq,matricula:$('mat').value,password:$('pass').value});sid=d.id;$('login').classList.add('hidden');$('activa').classList.remove('hidden');$('bienvenida').textContent='Bienvenido, alumno de demostración';$('detalle').textContent='Sesión #'+sid+' · '+eq+' · '+new Date(d.inicio).toLocaleTimeString();$('msg').textContent='';refresh()}catch(e){msg(e.message,true)}}
async function logout(){if(!sid)return;try{await req('/api/logout',{id:sid});sid=null;$('activa').classList.add('hidden');$('login').classList.remove('hidden');msg('Sesión cerrada correctamente');refresh()}catch(e){msg(e.message,true)}}
async function reportar(){try{await req('/api/falla',{equipo:eq,matricula:$('mat').value, categoria:$('categoria').value,descripcion:$('descripcion').value});$('descripcion').value='';msg('Reporte enviado al encargado');refresh()}catch(e){msg(e.message,true)}}
async function remote(e,c){if(!confirm('¿Confirmar '+c+' de '+e+'?'))return;try{await req('/api/remote',{equipo:e,comando:c});refresh()}catch(x){alert(x.message)}}
async function resolver(id){await req('/api/resolver',{id});refresh()}
function msg(s,err=false){$('msg').innerHTML='<div class="flash" style="'+(err?'background:#ffe7e5;color:#a11c14':'')+'">'+esc(s)+'</div>'}
function csv(){req('/api/state').then(d=>{let rows=[['ID','Matricula','Alumno','Equipo','Inicio','Fin','Estado'],...d.sesiones.map(s=>[s.id,s.matricula,s.nombre,s.equipo,s.inicio,s.fin||'',s.estado])];let text=rows.map(r=>r.map(v=>'"'+String(v).replace(/"/g,'""')+'"').join(',')).join('\\r\\n'),a=document.createElement('a');a.href=URL.createObjectURL(new Blob(['\\ufeff'+text],{type:'text/csv;charset=utf-8'}));a.download='bitacora-sigacecyteo-demo.csv';a.click()})}
async function commands(){if(!sid)return;try{let d=await req('/api/commands',{equipo:eq});for(let c of d.comandos){if(c.comando==='cerrar'){sid=null;$('activa').classList.add('hidden');$('login').classList.remove('hidden');msg('El encargado cerró la sesión remotamente')}else msg('Bloqueo de demostración solicitado por el encargado')}}catch(e){}}
setInterval(()=>{if(!$('admin').classList.contains('hidden'))refresh();commands()},2000);refresh();
</script></html>"""
class H(BaseHTTPRequestHandler):
 def log_message(self,*a): pass
 def out(self,n,d):
  x=json.dumps(d,ensure_ascii=False).encode();self.send_response(n);self.send_header("Content-Type","application/json; charset=utf-8");self.send_header("Content-Length",str(len(x)));self.send_header("Cache-Control","no-store");self.end_headers();self.wfile.write(x)
 def body(self):
  n=int(self.headers.get("Content-Length",0))
  if n>20000: raise ValueError()
  return json.loads(self.rfile.read(n) or b"{}")
 def do_GET(self):
  if self.path=="/":
   x=PAGE.encode();self.send_response(200);self.send_header("Content-Type","text/html; charset=utf-8");self.send_header("Content-Length",str(len(x)));self.end_headers();self.wfile.write(x);return
  if self.path=="/api/state":
   with db() as c:
    self.out(200,{"equipos":[dict(x) for x in c.execute("SELECT * FROM equipos")],"sesiones":[dict(x) for x in c.execute("SELECT * FROM sesiones ORDER BY id DESC")],"fallas":[dict(x) for x in c.execute("SELECT * FROM fallas ORDER BY id DESC")]});return
  self.out(404,{"error":"No encontrado"})
 def do_POST(self):
  try: b=self.body()
  except: self.out(400,{"error":"Solicitud no válida"});return
  p=self.path
  if p in ("/api/remote","/api/resolver") and not secrets.compare_digest(self.headers.get("X-Admin-Token",""),ADMIN_TOKEN):self.out(403,{"error":"Acción administrativa no autorizada"});return
  with db() as c:
   if p=="/api/login":
    matricula=b.get("matricula","")
    if matricula not in USERS or b.get("password")!=PASSWORD:self.out(401,{"error":"Matrícula o contraseña incorrectas"});return
    e=c.execute("SELECT estado FROM equipos WHERE codigo=?",(b.get("equipo"),)).fetchone()
    if not e:self.out(400,{"error":"Equipo no registrado"});return
    if e["estado"]!="Libre":self.out(409,{"error":"Equipo ocupado; cierra la sesión anterior"});return
    if c.execute("SELECT id FROM sesiones WHERE matricula=? AND fin IS NULL",(matricula,)).fetchone():self.out(409,{"error":"Esta matrícula ya tiene una sesión activa."});return
    t=now();cur=c.execute("INSERT INTO sesiones(matricula,nombre,equipo,inicio,estado) VALUES(?,?,?,?,?)",(matricula,USERS[matricula],b["equipo"],t,"Activa"));c.execute("UPDATE equipos SET estado='En uso' WHERE codigo=?",(b["equipo"],));self.out(200,{"id":cur.lastrowid,"inicio":t});return
   if p=="/api/logout":
    s=c.execute("SELECT equipo FROM sesiones WHERE id=? AND fin IS NULL",(b.get("id"),)).fetchone()
    if not s:self.out(404,{"error":"Sesión activa no encontrada"});return
    c.execute("UPDATE sesiones SET fin=?,estado='Cerrada' WHERE id=?",(now(),b["id"]));c.execute("UPDATE equipos SET estado='Libre' WHERE codigo=?",(s["equipo"],));self.out(200,{"ok":True});return
   if p=="/api/falla":
    desc=(b.get("descripcion") or "").strip()
    if len(desc)<3:self.out(400,{"error":"Describe la falla"});return
    c.execute("INSERT INTO fallas(equipo,matricula,categoria,descripcion,hora) VALUES(?,?,?,?,?)",(b.get("equipo"),b.get("matricula"),b.get("categoria"),desc,now()));self.out(200,{"ok":True});return
   if p=="/api/remote":
    eq,cmd=b.get("equipo"),b.get("comando")
    if cmd not in ("cerrar","bloquear"):self.out(400,{"error":"Comando no válido"});return
    c.execute("INSERT INTO comandos(equipo,comando) VALUES(?,?)",(eq,cmd))
    if cmd=="cerrar":c.execute("UPDATE sesiones SET fin=?,estado='Cerrada remotamente' WHERE equipo=? AND fin IS NULL",(now(),eq));c.execute("UPDATE equipos SET estado='Libre' WHERE codigo=?",(eq,))
    self.out(200,{"ok":True});return
   if p=="/api/commands":
    cs=[dict(x) for x in c.execute("SELECT id,comando FROM comandos WHERE equipo=? AND consumido=0",(b.get("equipo"),))]
    c.executemany("UPDATE comandos SET consumido=1 WHERE id=?",[(x["id"],) for x in cs]);self.out(200,{"comandos":cs});return
   if p=="/api/resolver":
    c.execute("UPDATE fallas SET estado='Resuelta' WHERE id=?",(b.get("id"),));self.out(200,{"ok":True});return
  self.out(404,{"error":"No encontrado"})
if __name__=="__main__":
 init();print(f"SIGACEcyTEO demo en http://0.0.0.0:{PORT} | matrículas 2026001 y 2026002 | contraseña {PASSWORD}");ThreadingHTTPServer((HOST,PORT),H).serve_forever()
