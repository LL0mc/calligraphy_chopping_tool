@echo off
cd /d "%~dp0"
echo Starting Review Server...
start "Review Server" python review_server.py
timeout /t 2 /nobreak >nul
start "" "http://127.0.0.1:5000/"
