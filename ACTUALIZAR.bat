@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Actualizar Voxia
if not exist ".venv\Scripts\python.exe" ( echo Primero ejecuta INSTALAR.bat & pause & exit /b 1 )
set "ZIP=%~1"
if "%ZIP%"=="" (
  echo Elige el .zip de la version nueva...
  for /f "usebackq delims=" %%F in (`powershell -NoProfile -Command "Add-Type -AssemblyName System.Windows.Forms; $d = New-Object System.Windows.Forms.OpenFileDialog; $d.Filter = 'Voxia (*.zip)|*.zip'; $d.Title = 'Elige el .zip nuevo de Voxia'; if ($d.ShowDialog() -eq 'OK') { $d.FileName }"`) do set "ZIP=%%F"
)
if "%ZIP%"=="" ( echo No elegiste ningun archivo. & pause & exit /b 1 )
echo Cierra Voxia antes de seguir.
pause
".venv\Scripts\python.exe" -m bot.actualizar "%ZIP%"
echo.
pause
