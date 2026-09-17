@echo off
cd /d "%~dp0"
if exist .venv\Scripts\python.exe goto install
if exist "%LocalAppData%\Programs\Python\Python311\python.exe" goto local311
python -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3,11) else 1)" >nul 2>nul
if not errorlevel 1 goto pythonpath
py -3.11 -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3,11) else 1)" >nul 2>nul
if errorlevel 1 goto fail
py -3.11 -m venv .venv
goto checkvenv
:local311
"%LocalAppData%\Programs\Python\Python311\python.exe" -m venv .venv
goto checkvenv
:pythonpath
python -m venv .venv
:checkvenv
if not exist .venv\Scripts\python.exe goto fail
:install
.venv\Scripts\python.exe -m pip install -r requirements_web.txt
if errorlevel 1 goto fail
.venv\Scripts\python.exe -m unittest discover -s tests
if errorlevel 1 goto fail
.venv\Scripts\python.exe configure_key.py
if errorlevel 1 goto fail
echo Setup complete. Run train_model.bat for ABSA, then run_web.bat.
pause
exit /b 0
:fail
echo Setup failed. Python 3.11 was not found or a command failed.
echo See README_WEB.md for the full python.exe path method.
pause
exit /b 1
