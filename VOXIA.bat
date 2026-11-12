@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" ( echo Primero ejecuta INSTALAR.bat & pause & exit /b 1 )
".venv\Scripts\python.exe" -c "import webview, soundfile, numpy" >nul 2>&1
if errorlevel 1 ( echo Falta una libreria nueva. Ejecuta INSTALAR.bat otra vez. & pause & exit /b 1 )
start "" ".venv\Scripts\pythonw.exe" app.py
