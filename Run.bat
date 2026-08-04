@echo off
cd /d "%~dp0"
python pixelmorph.py
if errorlevel 1 pause
