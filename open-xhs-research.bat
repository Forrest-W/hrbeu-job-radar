@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv-xhs\Scripts\pythonw.exe" (
  echo Please install the local environment described in XHS_RESEARCH.md first.
  pause
  exit /b 1
)
start "" ".venv-xhs\Scripts\pythonw.exe" "xhs_desktop.py"
