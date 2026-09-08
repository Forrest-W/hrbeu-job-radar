@echo off
chcp 65001 >nul
cd /d "%~dp0"
call update-latest.bat
if errorlevel 1 (
  echo.
  echo 刷新失败，请检查网络后重试。
  pause
  exit /b 1
)
start "" index.html
