@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe goto fail
echo FoodLens incremental pipeline
echo.
.venv\Scripts\python.exe data_pipeline.py status
echo.
echo Vi du:
echo   .venv\Scripts\python.exe data_pipeline.py ingest-restaurants --area "Hai Chau, Da Nang" --cuisine "mon Viet" --limit 20
echo   .venv\Scripts\python.exe data_pipeline.py ingest-seeds --max-seeds 5 --per-seed-limit 20
echo   .venv\Scripts\python.exe data_pipeline.py ingest-reviews --max-restaurants 20 --pages 1
echo   .venv\Scripts\python.exe data_pipeline.py analyze-pending --limit 1000
echo   .venv\Scripts\python.exe data_pipeline.py compute-trends
echo   .venv\Scripts\python.exe data_pipeline.py build-index
echo   .venv\Scripts\python.exe data_pipeline.py data-report
pause
exit /b 0
:fail
echo Chua co .venv. Hay chay setup_web.bat truoc.
pause
exit /b 1
