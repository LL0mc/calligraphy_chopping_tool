@echo off
cd /d "%~dp0"
echo Starting Character Viewer...
start "Char Viewer" python char_viewer.py
timeout /t 2 /nobreak >nul
start "" "http://127.0.0.1:5001/"
