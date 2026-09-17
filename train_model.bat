@echo off
cd /d "%~dp0"
.venv\Scripts\python.exe pipeline.py download
if errorlevel 1 goto fail
.venv\Scripts\python.exe pipeline.py prepare
if errorlevel 1 goto fail
.venv\Scripts\python.exe pipeline.py train
if errorlevel 1 goto fail
echo Training complete. Restart web to activate the model.
pause
exit /b 0
:fail
echo Training failed. Review the error above.
pause
exit /b 1
