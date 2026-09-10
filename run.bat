@echo off
echo ============================================================
echo   QBASWING MY SERVER
echo   "Toda informacion al alcance de tus manos"
echo ============================================================
cd /d "%~dp0"

if not exist venv (
    echo Creando entorno virtual...
    python -m venv venv
)

call venv\Scripts\activate.bat
pip install -r requirements.txt --quiet
python app.py
pause
