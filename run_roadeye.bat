@echo off
title RoadEye Server
echo ====================================================
echo           Starting RoadEye Platform (v2.0)
echo ====================================================
echo.
cd /d "%~dp0"
echo Server URL: http://localhost:8000
echo Opening browser...
start http://localhost:8000
echo.
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
pause
