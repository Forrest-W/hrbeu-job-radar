@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist logs mkdir logs
echo [%date% %time%] 开始增量更新>> logs\latest-update.log
python -X utf8 scrape_hrbeu.py --output index.html >> logs\latest-update.log 2>&1
if errorlevel 1 (
  echo [%date% %time%] 增量更新失败>> logs\latest-update.log
  exit /b 1
)
echo [%date% %time%] 增量更新完成>> logs\latest-update.log
exit /b 0
