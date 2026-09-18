@echo off
cd /d "%~dp0\..\.."
set "PYTHONPATH=%CD%\src"
set "FOODLENS_PYTHON=.venv\Scripts\python.exe"
if exist instance\deploy-venv\Scripts\python.exe set "FOODLENS_PYTHON=instance\deploy-venv\Scripts\python.exe"
if not exist "%FOODLENS_PYTHON%" goto fail
echo Open http://127.0.0.1:5001 in your browser after server starts.
"%FOODLENS_PYTHON%" -m scripts.serve --mode local
pause
exit /b 0
:fail
echo Run setup_web.bat first.
pause
exit /b 1
