@echo off
cd /d "%~dp0"
set "DEV_MEMORY_DASHBOARD_REGISTRY=%~dp0.dev-memory\.runtime\dashboard-projects.json"
python memory.py dashboard
if errorlevel 1 pause
