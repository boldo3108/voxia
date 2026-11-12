@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ==========================================
echo   Instalando Voxia...
echo ==========================================
set PY=
py -3 --version >nul 2>&1 && set PY=py -3
if not defined PY python --version >nul 2>&1 && set PY=python
if not defined PY (
  echo [X] No encontre Python. Instalalo desde https://www.python.org/downloads/
  echo     y marca la casilla "Add python.exe to PATH" al instalar.
  pause & exit /b 1
)
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)"
if errorlevel 1 (
  echo [X] Necesitas Python 3.11 o mas nuevo. Descargalo de python.org
  pause & exit /b 1
)
if not exist ".venv" (
  echo Creando entorno virtual...
  %PY% -m venv .venv
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo [X] Algo fallo instalando las librerias. Revisa tu internet y prueba de nuevo.
  pause & exit /b 1
)
echo Creando el acceso directo "Voxia" en el escritorio...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$d='%~dp0'; $s=(New-Object -ComObject WScript.Shell).CreateShortcut([IO.Path]::Combine([Environment]::GetFolderPath('Desktop'),'Voxia.lnk')); $s.TargetPath=$d+'.venv\Scripts\pythonw.exe'; $s.Arguments='\"'+$d+'app.py\"'; $s.WorkingDirectory=$d; $s.IconLocation=$d+'recursos\voxia.ico'; $s.Save()" >nul 2>&1
echo.
echo [OK] Instalacion lista.
echo Siguiente paso: abre Voxia desde el escritorio (o con VOXIA.bat)
echo.
pause
