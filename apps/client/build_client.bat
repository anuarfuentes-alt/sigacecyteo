@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe py -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-qr.txt
pyinstaller --noconfirm --clean --onefile --windowed --name SIGACEcyTEOCliente client.py
echo.
echo Aplicacion generada en: apps\client\dist\SIGACEcyTEOCliente.exe
pause
