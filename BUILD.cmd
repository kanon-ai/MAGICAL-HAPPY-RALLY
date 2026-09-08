@echo off
setlocal
cd /d "%~dp0"
python tools\build.py %*
if errorlevel 1 (
  echo Build failed. See the message above.
  exit /b 1
)
echo Cartridge: outputs\MAGICAL_HAPPY_RALLY-v0.5.rom
