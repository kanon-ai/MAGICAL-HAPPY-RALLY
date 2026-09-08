@echo off
setlocal
cd /d "%~dp0"
if not exist "outputs\MAGICAL_HAPPY_RALLY-v0.5.rom" (
  echo Build the cartridge with BUILD.cmd first.
  pause
  exit /b 1
)
node tools\emulator_host.mjs
if errorlevel 1 (
  echo Emulator could not start. See the message above.
  pause
  exit /b 1
)
