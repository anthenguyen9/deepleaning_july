@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe goto fail
echo Open http://127.0.0.1:5000 in your browser after server starts.
.venv\Scripts\python.exe webapp.py
pause
exit /b 0
:fail
echo Run setup_web.bat first.
pause
exit /b 1
