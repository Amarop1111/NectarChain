@echo off
setlocal
cd /d %~dp0

echo [1/3] Installing core dependencies...
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo Dependency installation failed. Check Python and internet access.
  pause
  exit /b 1
)

echo [2/3] Loading synthetic demo data...
python seed_demo.py --reset
if errorlevel 1 (
  echo.
  echo Demo data loading failed.
  pause
  exit /b 1
)

echo [3/3] Starting Nectar Chain...
echo Open http://127.0.0.1:5000 in your browser.
echo Keep this window open.
python app.py
pause
