@echo off
setlocal
cd /d "%~dp0"
if not exist .env (
  copy .env.example .env >nul
  echo Se creo apps\server\.env.
  echo Edita ese archivo y cambia las claves de administrador y PostgreSQL antes de iniciar.
  notepad .env
  echo Cuando termines de guardar el archivo, regresa aqui y presiona una tecla.
  pause
)
if not exist .venv\Scripts\python.exe py -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m uvicorn server:app --host 0.0.0.0 --port 8080 --access-log
