@echo off
cd /d "%~dp0\..\.."
set "PYTHONPATH=%CD%\src"
.venv\Scripts\python.exe -m streamlit run src\app.py --server.address 127.0.0.1
