@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv" ( echo Primero ejecuta INSTALAR.bat & pause & exit /b 1 )
call .venv\Scripts\activate.bat
python obtener_token.py
