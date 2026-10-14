import asyncio, hashlib, os, secrets
from datetime import datetime, timezone
from typing import Optional
import bcrypt
from fastapi import FastAPI, HTTPException, Header, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from supabase import create_client, Client

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_ROLE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
IDLE_TIMEOUT_SECONDS = int(os.getenv("IDLE_TIMEOUT_SECONDS", "600"))
supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
app = FastAPI(title="SIGACEcyTEO Computer Lab API", version="0.1.0")
# La API no necesita CORS abierto: configurar orígenes explícitos en despliegue.
origins = [x.strip() for x in os.getenv("CORS_ORIGINS", "").split(",") if x.strip()]
if origins:
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["GET","POST"], allow_headers=["Authorization","Content-Type","X-Agent-Key"])

class LoginRequest(BaseModel):
    matricula: Optional[str] = None
    password: Optional[str] = None
    qr_token: Optional[str] = None
    equipo_codigo: str = Field(min_length=1, max_length=80)
    telemetria: dict = Field(default_factory=dict)

class EndSessionRequest(BaseModel):
    sesion_id: str
    motivo: str = "cerrada"

class IncidentRequest(BaseModel):
    categoria: str = Field(min_length=1, max_length=80)
    descripcion: str = Field(min_length=3, max_length=2000)
    sesion_id: Optional[str] = None
    prioridad: str = "media"
    telemetria: dict = Field(default_factory=dict)

class TelemetryRequest(BaseModel):
    telemetria: dict = Field(default_factory=dict)
    agente_version: Optional[str] = None
    sistema_operativo: Optional[str] = None

def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()

def require_agent(agent_key: str, codigo: str):
    result = supabase.table("cc_equipos").select("*").eq("codigo", codigo).eq("habilitado", True).limit(1).execute()
    if not result.data:
        raise HTTPException(401, "Equipo no registrado o deshabilitado")
    equipo = result.data[0]
    stored = equipo.get("agent_key_hash")
    if not stored or not secrets.compare_digest(stored, digest(agent_key)):
        raise HTTPException(401, "Agente no autorizado")
    return equipo

def safe_student(alumno: dict) -> dict:
    return {"id_alumno": alumno["id_alumno"], "matricula": alumno["matricula"],
            "nombre": " ".join(filter(None, [alumno.get("nombre"), alumno.get("apellidos")]))}

@app.get("/health")
def health():
    return {"status": "ok", "service": "sigacecyteo-computer-lab", "time": datetime.now(timezone.utc).isoformat()}

@app.post("/api/v1/login")
def login(body: LoginRequest, x_agent_key: str = Header(default="")):
    equipo = require_agent(x_agent_key, body.equipo_codigo)
    if bool(body.qr_token) == bool(body.matricula and body.password):
        raise HTTPException(400, "Proporciona matrícula/contraseña o QR, no ambos")
    if body.qr_token:
        cred = supabase.table("cc_credenciales").select("id_alumno,qr_token_hash,activo").eq("qr_token_hash", digest(body.qr_token)).eq("activo", True).limit(1).execute()
        metodo = "qr"
    else:
        alumno = supabase.table("alumnos").select("id_alumno,matricula,nombre,apellidos,estatus").eq("matricula", body.matricula.strip()).eq("estatus", "Activo").limit(1).execute()
        if not alumno.data:
            raise HTTPException(401, "Credenciales no válidas")
        cred = supabase.table("cc_credenciales").select("id_alumno,password_hash,activo").eq("id_alumno", alumno.data[0]["id_alumno"]).eq("activo", True).limit(1).execute()
        if not cred.data or not cred.data[0].get("password_hash"):
            raise HTTPException(401, "Credenciales no válidas")
        try:
            valid = bcrypt.checkpw(body.password.encode(), cred.data[0]["password_hash"].encode())
        except (ValueError, TypeError):
            valid = False
        if not valid:
            raise HTTPException(401, "Credenciales no válidas")
        metodo = "matricula_password"
    if not cred.data:
        raise HTTPException(401, "Credencial QR no válida")
    id_alumno = cred.data[0]["id_alumno"]
    active = supabase.table("cc_sesiones").select("id").eq("id_equipo", equipo["id"]).is_("hora_fin", "null").limit(1).execute()
    if active.data:
        raise HTTPException(409, "El equipo ya tiene una sesión activa")
    # Evita sesiones concurrentes para la misma matrícula en dos equipos.
    other = supabase.table("cc_sesiones").select("id").eq("id_alumno", id_alumno).is_("hora_fin", "null").limit(1).execute()
    if other.data:
        raise HTTPException(409, "El alumno ya tiene una sesión activa")
    created = supabase.table("cc_sesiones").insert({"id_alumno": id_alumno, "id_equipo": equipo["id"], "metodo_acceso": metodo, "alertas_hardware": body.telemetria.get("alertas", [])}).execute()
    if not created.data:
        raise HTTPException(500, "No se pudo registrar la sesión")
    supabase.table("cc_equipos").update({"estado":"en_uso","ultima_conexion":datetime.now(timezone.utc).isoformat(),"telemetria":body.telemetria}).eq("id",equipo["id"]).execute()
    return {"ok": True, "sesion": created.data[0], "equipo": equipo["codigo"], "inactividad_segundos": IDLE_TIMEOUT_SECONDS}

@app.post("/api/v1/sessions/end")
def end_session(body: EndSessionRequest, x_agent_key: str = Header(default=""), x_equipo_codigo: str = Header(default="")):
    equipo = require_agent(x_agent_key, x_equipo_codigo)
    result = supabase.table("cc_sesiones").update({"hora_fin":datetime.now(timezone.utc).isoformat(),"estado":body.motivo if body.motivo in ("cerrada","cerrada_por_inactividad","cerrada_remotamente") else "cerrada"}).eq("id",body.sesion_id).eq("id_equipo",equipo["id"]).is_("hora_fin","null").execute()
    if not result.data:
        raise HTTPException(404, "Sesión activa no encontrada")
    supabase.table("cc_equipos").update({"estado":"libre"}).eq("id",equipo["id"]).execute()
    return {"ok":True}

@app.post("/api/v1/incidents")
def report_incident(body: IncidentRequest, x_agent_key: str = Header(default=""), x_equipo_codigo: str = Header(default="")):
    equipo = require_agent(x_agent_key, x_equipo_codigo)
    valid_priority = body.prioridad if body.prioridad in ("baja","media","alta","critica") else "media"
    row = {"id_equipo":equipo["id"],"categoria":body.categoria,"descripcion":body.descripcion,"prioridad":valid_priority,"telemetria":body.telemetria}
    if body.sesion_id:
        session = supabase.table("cc_sesiones").select("id,id_alumno").eq("id",body.sesion_id).eq("id_equipo",equipo["id"]).limit(1).execute()
        if session.data:
            row.update({"id_sesion":body.sesion_id,"id_alumno":session.data[0]["id_alumno"]})
    result = supabase.table("cc_incidentes").insert(row).execute()
    supabase.table("cc_equipos").update({"ultima_conexion":datetime.now(timezone.utc).isoformat(),"telemetria":body.telemetria}).eq("id",equipo["id"]).execute()
    return {"ok":True,"incidente":result.data[0] if result.data else None}

@app.post("/api/v1/telemetry")
def telemetry(body: TelemetryRequest, x_agent_key: str = Header(default=""), x_equipo_codigo: str = Header(default="")):
    equipo = require_agent(x_agent_key, x_equipo_codigo)
    supabase.table("cc_equipos").update({"ultima_conexion":datetime.now(timezone.utc).isoformat(),"telemetria":body.telemetria,"agente_version":body.agente_version,"sistema_operativo":body.sistema_operativo}).eq("id",equipo["id"]).execute()
    return {"ok":True}

@app.websocket("/api/v1/ws/{equipo_codigo}")
async def equipment_ws(websocket: WebSocket, equipo_codigo: str, x_agent_key: str = Header(default="")):
    try:
        equipo = require_agent(x_agent_key, equipo_codigo)
    except HTTPException:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    try:
        while True:
            # Los comandos son gestionados por el agente; consultar la cola no concede
            # acceso al panel administrativo ni permite ejecutar comandos arbitrarios.
            rows = supabase.table("cc_comandos").select("*").eq("id_equipo",equipo["id"]).is_("ejecutado_at","null").order("solicitado_at").limit(10).execute()
            for command in rows.data or []:
                await websocket.send_json({"id":command["id"],"comando":command["comando"],"parametros":command["parametros"]})
            try:
                message = await asyncio.wait_for(websocket.receive_json(), timeout=2.0)
                if message.get("type") == "ack" and message.get("id"):
                    supabase.table("cc_comandos").update({"ejecutado_at":datetime.now(timezone.utc).isoformat(),"resultado":message.get("resultado",{})}).eq("id",message["id"]).eq("id_equipo",equipo["id"]).execute()
            except asyncio.TimeoutError:
                # Revisa la cola cada dos segundos incluso cuando el agente no envía datos.
                continue
    except WebSocketDisconnect:
        pass
