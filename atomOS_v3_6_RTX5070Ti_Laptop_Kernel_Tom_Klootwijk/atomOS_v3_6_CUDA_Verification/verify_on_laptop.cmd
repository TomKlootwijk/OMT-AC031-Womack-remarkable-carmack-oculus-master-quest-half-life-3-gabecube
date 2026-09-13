@echo off
setlocal
cd /d "%~dp0"
python tools\validate.py --gpu --sanitizer %*
exit /b %ERRORLEVEL%
