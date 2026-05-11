@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File ".\zotero-plugin\scripts\build-xpi.ps1"
pause
