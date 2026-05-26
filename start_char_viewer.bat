@echo off
cd /d "%~dp0"
echo Starting Character Viewer...
start /b python char_viewer.py
timeout /t 2 /nobreak >nul
start "" "http://127.0.0.1:5001/"
pause
