@echo off
cd /d "%~dp0"
py -3.11 -m venv .venv
if errorlevel 1 exit /b 1
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 exit /b 1
.venv\Scripts\python.exe -m unittest discover -s tests
if errorlevel 1 exit /b 1
.venv\Scripts\python.exe pipeline.py download
if errorlevel 1 exit /b 1
.venv\Scripts\python.exe pipeline.py prepare
if errorlevel 1 exit /b 1
.venv\Scripts\python.exe pipeline.py train
if errorlevel 1 exit /b 1
echo Ready. Run run_demo.bat
pause
