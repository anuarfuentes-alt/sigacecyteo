"""Aplicación de escritorio del alumno SIGACEcyTEO (Windows 10/11)."""
from __future__ import annotations
import base64, ctypes, hashlib, hmac, json, os, platform, queue, socket, threading, time, uuid
from ctypes import POINTER, Structure, byref, c_ubyte, c_void_p, string_at, wintypes
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, urlunparse, urlencode
import tkinter as tk
from tkinter import ttk, messagebox
import requests
from cryptography.fernet import Fernet, InvalidToken
import websocket

try:
    import psutil
except Exception:
    psutil = None

APP_NAME="SIGACEcyTEO Cliente"
IDLE_MINUTES=int(os.getenv("SIGA_IDLE_MINUTES","15"))
HTTP_TIMEOUT=5

def now_iso(): return datetime.now(timezone.utc).isoformat()
def pbkdf(password,salt): return hashlib.pbkdf2_hmac("sha256",password.encode(),salt,220000)

class DATA_BLOB(Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", POINTER(c_ubyte))]

def protect_key_windows(data: bytes) -> bytes:
    if os.name != "nt":
        return data
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.LocalFree.argtypes = [c_void_p]; kernel32.LocalFree.restype = c_void_p
    crypt32.CryptProtectData.argtypes = [POINTER(DATA_BLOB), wintypes.LPCWSTR, POINTER(DATA_BLOB), c_void_p, c_void_p, wintypes.DWORD, POINTER(DATA_BLOB)]
    crypt32.CryptProtectData.restype = wintypes.BOOL
    buf = (c_ubyte * len(data)).from_buffer_copy(data)
    src = DATA_BLOB(len(data), buf); dst = DATA_BLOB()
    if not crypt32.CryptProtectData(byref(src), "SIGACEcyTEO offline key", None, None, None, 0, byref(dst)):
        raise ctypes.WinError(ctypes.get_last_error())
    try: return b"DPAPI1" + string_at(dst.pbData, dst.cbData)
    finally: kernel32.LocalFree(dst.pbData)

def unprotect_key_windows(data: bytes) -> bytes:
    if os.name != "nt" or not data.startswith(b"DPAPI1"):
        return data
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.LocalFree.argtypes = [c_void_p]; kernel32.LocalFree.restype = c_void_p
    crypt32.CryptUnprotectData.argtypes = [POINTER(DATA_BLOB), POINTER(wintypes.LPWSTR), POINTER(DATA_BLOB), c_void_p, c_void_p, wintypes.DWORD, POINTER(DATA_BLOB)]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    raw = data[6:]; buf = (c_ubyte * len(raw)).from_buffer_copy(raw)
    src = DATA_BLOB(len(raw), buf); dst = DATA_BLOB(); desc = wintypes.LPWSTR()
    if not crypt32.CryptUnprotectData(byref(src), byref(desc), None, None, None, 0, byref(dst)):
        raise ctypes.WinError(ctypes.get_last_error())
    try: return string_at(dst.pbData, dst.cbData)
    finally:
        kernel32.LocalFree(dst.pbData)
        if desc: kernel32.LocalFree(desc)

class OfflineVault:
    """Cola cifrada con Fernet; en Windows la clave de Fernet se protege mediante DPAPI para el usuario actual."""
    def __init__(self):
        root=Path(os.getenv("LOCALAPPDATA") or Path.home()/".local"/"share")/"SIGACEcyTEO"
        root.mkdir(parents=True,exist_ok=True)
        self.keyfile=root/"offline.key"; self.datafile=root/"offline.vault"
        if not self.keyfile.exists():
            raw_key=Fernet.generate_key()
            protected=protect_key_windows(raw_key) if os.name=="nt" else raw_key
            self.keyfile.write_bytes(protected)
            try: os.chmod(self.keyfile,0o600)
            except OSError: pass
        stored_key=self.keyfile.read_bytes()
        self.fernet=Fernet(unprotect_key_windows(stored_key))
        self.lock=threading.Lock()
        if not self.datafile.exists(): self.save({"users":{},"events":[]})
    def load(self):
        with self.lock:
            try: return json.loads(self.fernet.decrypt(self.datafile.read_bytes()).decode("utf-8"))
            except (InvalidToken,ValueError,OSError): return {"users":{},"events":[]}
    def save(self,data):
        with self.lock:
            temp=self.datafile.with_suffix(".tmp")
            temp.write_bytes(self.fernet.encrypt(json.dumps(data,ensure_ascii=False).encode("utf-8")))
            temp.replace(self.datafile)
            try: os.chmod(self.datafile,0o600)
            except OSError: pass
    def cache_user(self,matricula,password,nombre):
        data=self.load(); salt=os.urandom(16)
        data["users"][matricula]={"nombre":nombre,"salt":salt.hex(),"digest":pbkdf(password,salt).hex()}
        self.save(data)
    def verify_user(self,matricula,password):
        item=self.load().get("users",{}).get(matricula)
        if not item: return None
        try:
            good=hmac.compare_digest(pbkdf(password,bytes.fromhex(item["salt"])).hex(),item["digest"])
            return item["nombre"] if good else None
        except Exception: return None
    def enqueue(self,event):
        data=self.load(); event.setdefault("event_id",str(uuid.uuid4())); data.setdefault("events",[]).append(event); self.save(data)
    def events(self): return list(self.load().get("events",[]))
    def clear_events(self): 
        data=self.load(); data["events"]=[]; self.save(data)

class ClientApp:
    def __init__(self,root):
        self.root=root; self.root.title(APP_NAME); self.root.geometry("700x640"); self.root.minsize(600,560)
        self.vault=OfflineVault(); self.token=None; self.student={}; self.computer_code="LAB-01"; self.offline_id=None; self.offline_mode=False
        self.server_url=os.getenv("SIGA_SERVER_URL","http://192.168.0.235:8080").rstrip("/")
        self.last_activity=time.monotonic(); self.ws_app=None; self.ws_thread=None; self.ws_stop=threading.Event(); self.ping_thread=None; self.worker_stop=threading.Event()
        self.locked=False; self.view="login"; self.frames={}
        self.root.bind_all("<KeyPress>",self.activity); self.root.bind_all("<Button>",self.activity); self.root.protocol("WM_DELETE_WINDOW",self.close)
        self.build_login(); self.root.after(1000,self.tick); self.start_workers()
    def activity(self,event=None): self.last_activity=time.monotonic()
    def make_header(self,parent,title,subtitle):
        ttk.Label(parent,text=title,font=("Segoe UI",20,"bold")).pack(anchor="w",pady=(8,2))
        ttk.Label(parent,text=subtitle,foreground="#536579",wraplength=600).pack(anchor="w",pady=(0,14))
    def build_login(self):
        f=ttk.Frame(self.root,padding=24); self.frames["login"]=f; f.pack(fill="both",expand=True)
        self.make_header(f,"SIGACEcyTEO","Control de acceso y bitácora del centro de cómputo")
        box=ttk.LabelFrame(f,text="Conexión",padding=12); box.pack(fill="x",pady=7)
        ttk.Label(box,text="Servidor (URL)").grid(row=0,column=0,sticky="w",padx=5,pady=5)
        self.url_var=tk.StringVar(value=self.server_url); ttk.Entry(box,textvariable=self.url_var,width=48).grid(row=0,column=1,sticky="ew",padx=5,pady=5)
        ttk.Label(box,text="Código de equipo").grid(row=1,column=0,sticky="w",padx=5,pady=5)
        self.code_var=tk.StringVar(value=os.getenv("SIGA_COMPUTER_CODE","LAB-01")); ttk.Entry(box,textvariable=self.code_var,width=20).grid(row=1,column=1,sticky="w",padx=5,pady=5)
        box.columnconfigure(1,weight=1)
        auth=ttk.LabelFrame(f,text="Acceso del alumno",padding=12); auth.pack(fill="x",pady=7)
        ttk.Label(auth,text="Matrícula").grid(row=0,column=0,sticky="w",padx=5,pady=5)
        self.mat_var=tk.StringVar(); ttk.Entry(auth,textvariable=self.mat_var).grid(row=0,column=1,sticky="ew",padx=5,pady=5)
        ttk.Label(auth,text="Contraseña").grid(row=1,column=0,sticky="w",padx=5,pady=5)
        self.pass_var=tk.StringVar(); ttk.Entry(auth,textvariable=self.pass_var,show="•").grid(row=1,column=1,sticky="ew",padx=5,pady=5)
        auth.columnconfigure(1,weight=1)
        actions=ttk.Frame(f); actions.pack(fill="x",pady=10)
        ttk.Button(actions,text="Iniciar sesión",command=self.login).pack(side="left",padx=4)
        ttk.Button(actions,text="Leer QR con cámara",command=self.scan_qr).pack(side="left",padx=4)
        self.login_status=ttk.Label(f,text="Se necesita acceso al servidor para el primer inicio de sesión.",wraplength=600); self.login_status.pack(anchor="w",pady=8)
        ttk.Label(f,text="Si ya iniciaste sesión antes en este equipo, puede validar credenciales guardadas y encriptadas cuando la red esté caída.",foreground="#536579",wraplength=600).pack(anchor="w",pady=4)
    def show_frame(self,name):
        for frame in self.frames.values(): frame.pack_forget()
        self.frames[name].pack(fill="both",expand=True); self.view=name
    def api(self,path,method="GET",payload=None,token=None,timeout=HTTP_TIMEOUT):
        base=self.server_url
        headers={}
        active_token=token if token is not None else self.token
        if active_token: headers["Authorization"]="Bearer "+active_token
        response=requests.request(method,base+path,json=payload,headers=headers,timeout=timeout)
        try: data=response.json()
        except ValueError: data={}
        if not response.ok: raise RuntimeError(data.get("detail") or data.get("error") or "Error HTTP "+str(response.status_code))
        return data
    def login(self):
        self.activity(); self.server_url=self.url_var.get().strip().rstrip("/")
        self.computer_code=self.code_var.get().strip().upper(); matricula=self.mat_var.get().strip(); password=self.pass_var.get()
        if not self.server_url.startswith(("http://","https://")): messagebox.showerror("Servidor","Escribe una URL completa, por ejemplo http://192.168.0.235:8080"); return
        if not self.computer_code or not matricula or not password: messagebox.showwarning("Datos faltantes","Completa código de equipo, matrícula y contraseña."); return
        try:
            data=self.api("/api/auth/login","POST",{"matricula":matricula,"password":password,"computer_code":self.computer_code},token=None)
            self.token=data["access_token"]; self.student={"matricula":data["matricula"],"nombre":data["nombre"],"session_id":data["session_id"]}
            self.offline_mode=False; self.offline_id="online-"+str(data["session_id"]); self._password_in_memory=None; self.vault.cache_user(matricula,password,data["nombre"]); self.pass_var.set("")
            self.sync_queue(); self.open_session()
        except requests.RequestException as e:
            cached_name=self.vault.verify_user(matricula,password)
            if cached_name:
                self._password_in_memory=password
                self.token=None; self.offline_mode=True; self.offline_id=str(uuid.uuid4())
                self.student={"matricula":matricula,"nombre":cached_name,"session_id":None}
                self.vault.enqueue({"type":"session_start","offline_id":self.offline_id,"computer_code":self.computer_code,"at":now_iso()})
                self.pass_var.set(""); self.open_session("Modo sin conexión: actividad cifrada localmente; se sincronizará al recuperar la red.")
            else:
                self.login_status.configure(text="No fue posible conectar y no hay credenciales offline válidas. "+str(e))
        except Exception as e:
            self.login_status.configure(text="El servidor rechazó el acceso o devolvió un error: "+str(e))
    def open_session(self,notice=None):
        f=ttk.Frame(self.root,padding=24); self.frames["session"]=f
        self.make_header(f,"Sesión del alumno","El equipo registra actividad, telemetría e incidencias.")
        self.who=ttk.Label(f,text="",font=("Segoe UI",13,"bold")); self.who.pack(anchor="w",pady=5)
        self.status=ttk.Label(f,text="",wraplength=600); self.status.pack(anchor="w",pady=5)
        incident=ttk.LabelFrame(f,text="Reportar una falla",padding=12); incident.pack(fill="x",pady=12)
        ttk.Label(incident,text="Tipo de problema").pack(anchor="w")
        self.category=tk.StringVar(value="Sin acceso a internet")
        ttk.Combobox(incident,textvariable=self.category,state="readonly",values=["Sin acceso a internet","Teclado dañado","Mouse descompuesto","Falla de monitor","Problema de software","Otro"],width=32).pack(anchor="w",pady=4)
        ttk.Label(incident,text="Descripción").pack(anchor="w")
        self.description=tk.Text(incident,height=4,wrap="word"); self.description.pack(fill="x",pady=4)
        ttk.Button(incident,text="Enviar reporte",command=self.report).pack(anchor="w",pady=5)
        buttons=ttk.Frame(f); buttons.pack(fill="x",pady=8)
        ttk.Button(buttons,text="Actualizar conexión",command=self.heartbeat).pack(side="left",padx=4)
        ttk.Button(buttons,text="Cerrar sesión",command=self.logout).pack(side="left",padx=4)
        self.notice=ttk.Label(f,text=notice or "",foreground="#8a5a00",wraplength=600); self.notice.pack(anchor="w",pady=8)
        self.who.configure(text=self.student["nombre"]+" · "+self.student["matricula"]+" · "+self.computer_code)
        self.status.configure(text=("SIN CONEXIÓN · Cola cifrada" if self.offline_mode else "Conectado al servidor central"))
        self.show_frame("session"); self.last_activity=time.monotonic()
        if self.token: self.connect_ws()
    def report(self):
        self.activity(); description=self.description.get("1.0","end").strip()
        if len(description)<3: messagebox.showwarning("Descripción","Describe la falla con al menos 3 caracteres."); return
        event={"type":"incident","offline_id":self.offline_id,"computer_code":self.computer_code,"category":self.category.get(),"description":description,"at":now_iso()}
        if self.token and not self.offline_mode:
            try:
                self.api("/api/client/incidents","POST",{"category":event["category"],"description":description})
                self.notice.configure(text="Reporte enviado al encargado.")
            except Exception:
                self.vault.enqueue(event); self.notice.configure(text="Red no disponible: reporte guardado en cola cifrada para sincronización.")
        else:
            self.vault.enqueue(event); self.notice.configure(text="Reporte guardado en cola cifrada para sincronización.")
        self.description.delete("1.0","end")
    def logout(self,remote=False):
        self.activity()
        if self.offline_mode:
            self.vault.enqueue({"type":"session_end","offline_id":self.offline_id,"computer_code":self.computer_code,"at":now_iso()})
        elif self.token:
            try: self.api("/api/client/logout","POST",{})
            except Exception:
                self.vault.enqueue({"type":"session_end","offline_id":self.offline_id,"computer_code":self.computer_code,"at":now_iso()})
        self.close_ws(); self.token=None; self.student={}; self.offline_id=None; self.offline_mode=False; self._password_in_memory=None; self.locked=False
        if hasattr(self,"lock_frame") and self.lock_frame: self.lock_frame.destroy(); self.lock_frame=None
        self.frames["session"].destroy(); self.frames.pop("session",None); self.show_frame("login")
        self.login_status.configure(text="Sesión cerrada."+(" Por instrucción del encargado." if remote else ""))
    def scan_qr(self):
        try: import cv2
        except ImportError:
            messagebox.showinfo("Lector QR","Instala opencv-python en el cliente para activar lectura por cámara: pip install opencv-python"); return
        cap=cv2.VideoCapture(0); detector=cv2.QRCodeDetector(); found=None
        try:
            while cap.isOpened():
                ok,frame=cap.read()
                if not ok: break
                value,points,_=detector.detectAndDecode(frame)
                cv2.imshow("SIGACEcyTEO - escanea QR (ESC para cancelar)",frame)
                if value and value.startswith("SIGACEcyTEO:"): found=value; break
                if cv2.waitKey(10)&0xFF==27: break
        finally: cap.release(); cv2.destroyAllWindows()
        if not found: return
        self.server_url=self.url_var.get().strip().rstrip("/"); self.computer_code=self.code_var.get().strip().upper()
        try:
            data=self.api("/api/auth/qr-login","POST",{"qr_token":found,"computer_code":self.computer_code},token=None)
            self.token=data["access_token"]; self.student={"matricula":data["matricula"],"nombre":data["nombre"],"session_id":data["session_id"]}
            self.offline_mode=False; self.offline_id="online-"+str(data["session_id"]); self.open_session(); self.sync_queue()
        except Exception as e: messagebox.showerror("Acceso QR",str(e))
    def telemetry(self):
        data={"hostname":socket.gethostname(),"os_name":platform.platform(),"cpu":None,"memory":None,"disk":None}
        if psutil:
            try:
                data.update({"cpu":psutil.cpu_percent(interval=None),"memory":psutil.virtual_memory().percent,"disk":psutil.disk_usage(os.getenv("SystemDrive","C:") + "\\" if os.name=="nt" else "/").percent})
            except Exception: pass
        return data
    def heartbeat(self):
        self.activity()
        if not self.token: self.try_reconnect(); return
        try:
            result=self.api("/api/client/heartbeat","POST",self.telemetry())
            self.status.configure(text="Conectado · estado del equipo: "+result.get("state","En uso"))
            self.sync_queue()
        except Exception as e:
            self.status.configure(text="Sin conexión con servidor; los reportes nuevos se guardarán cifrados.")
    def sync_queue(self):
        events=self.vault.events()
        if not self.token or not events: return
        try:
            data=self.api("/api/client/sync-offline","POST",{"events":events})
            self.vault.clear_events()
            self.notice.configure(text="Conexión recuperada. Eventos offline sincronizados: "+str(data.get("synced",0)))
        except Exception:
            pass
    def try_reconnect(self):
        if not self.offline_mode or not self.student: return
        # Requiere la contraseña durante la sesión offline para reautenticarse; nunca la escribe en disco.
        if not getattr(self,"_password_in_memory",None): return
        try:
            data=self.api("/api/auth/login","POST",{"matricula":self.student["matricula"],"password":self._password_in_memory,"computer_code":self.computer_code},token=None)
            # Cierra la sesión local offline antes de reproducir sus eventos históricos.
            self.vault.enqueue({"type":"session_end","offline_id":self.offline_id,"computer_code":self.computer_code,"at":now_iso()})
            self.token=data["access_token"]; self.offline_mode=False; self.student["session_id"]=data["session_id"]; self._password_in_memory=None
            self.root.after(0, lambda: self.status.configure(text="Conexión recuperada; sincronizando datos offline.") if self.view=="session" else None)
            self.root.after(0, self.connect_ws)
            self.sync_queue()
        except Exception: pass
    def start_workers(self):
        def loop():
            last=0
            while not self.worker_stop.wait(5):
                if self.token and time.time()-last>=15:
                    last=time.time()
                    try:
                        result=self.api("/api/client/heartbeat","POST",self.telemetry())
                        self.root.after(0,lambda s=result.get("state","En uso"): self.status.configure(text="Conectado · estado del equipo: "+s) if hasattr(self,"status") and self.view=="session" else None)
                        self.root.after(0,self.sync_queue)
                    except Exception:
                        self.root.after(0,lambda: self.status.configure(text="Sin conexión; se conserva cola cifrada.") if hasattr(self,"status") and self.view=="session" else None)
                if self.offline_mode:
                    self.root.after(0,self.try_reconnect)
        threading.Thread(target=loop,daemon=True).start()
    def connect_ws(self):
        self.close_ws()
        if not self.token: return
        base=self.url_var.get().strip().rstrip("/")
        u=urlparse(base); scheme="wss" if u.scheme=="https" else "ws"
        url=urlunparse((scheme,u.netloc,"/ws/client","",urlencode({"token":self.token}),""))
        self.ws_stop.clear()
        def on_open(ws): ws.send("cliente listo")
        def on_message(ws,message):
            try:
                command=json.loads(message)
                self.root.after(0,lambda c=command:self.handle_command(c))
            except Exception: pass
        def run():
            self.ws_app=websocket.WebSocketApp(url,on_open=on_open,on_message=on_message)
            self.ws_app.run_forever(ping_interval=15,ping_timeout=5)
        self.ws_thread=threading.Thread(target=run,daemon=True); self.ws_thread.start()
    def close_ws(self):
        self.ws_stop.set()
        try:
            if self.ws_app: self.ws_app.close()
        except Exception: pass
        self.ws_app=None
    def handle_command(self,cmd):
        name=cmd.get("command"); cid=cmd.get("command_id")
        try:
            if self.token: self.api("/api/client/command-ack","POST",{"command_id":cid})
        except Exception: pass
        if name=="logout":
            self.logout(remote=True)
        elif name=="lock":
            self.lock_screen()
        elif name=="unlock":
            self.unlock_screen()
    def lock_screen(self):
        if self.view!="session" or self.locked: return
        self.locked=True
        self.lock_frame=tk.Frame(self.root,bg="#102b4e"); self.lock_frame.place(relx=0,rely=0,relwidth=1,relheight=1)
        tk.Label(self.lock_frame,text="EQUIPO BLOQUEADO",font=("Segoe UI",28,"bold"),fg="white",bg="#102b4e").pack(pady=(140,20))
        tk.Label(self.lock_frame,text="El encargado del centro de cómputo restringió esta aplicación.",font=("Segoe UI",13),fg="white",bg="#102b4e").pack()
        tk.Label(self.lock_frame,text="El desbloqueo requiere una instrucción del panel del servidor.",font=("Segoe UI",11),fg="#d0dded",bg="#102b4e").pack(pady=15)
        self.lock_frame.lift()
    def unlock_screen(self):
        if self.locked and getattr(self,"lock_frame",None):
            self.lock_frame.destroy(); self.lock_frame=None; self.locked=False; self.notice.configure(text="Aplicación desbloqueada por el encargado.")
    def tick(self):
        if self.view=="session":
            if self.token and time.monotonic()-self.last_activity>IDLE_MINUTES*60:
                self.logout()
                self.login_status.configure(text="Sesión cerrada automáticamente por inactividad.")
        self.root.after(1000,self.tick)
    def close(self):
        if self.view=="session":
            if messagebox.askyesno("Salir","¿Cerrar la aplicación y la sesión actual?"): self.logout()
            else: return
        self.worker_stop.set(); self.close_ws(); self.root.destroy()

def main():
    root=tk.Tk()
    try: style=ttk.Style(); style.theme_use("clam")
    except Exception: pass
    ClientApp(root); root.mainloop()
if __name__=="__main__": main()
