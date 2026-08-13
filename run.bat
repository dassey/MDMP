@echo off
REM Start the MDMP harness. Requires only Python 3.9+.
cd /d "%~dp0"
where python >nul 2>nul && (python serve.py %* & goto :eof)
where py >nul 2>nul && (py -3 serve.py %* & goto :eof)
echo Python 3.9 or newer is required and was not found on PATH.
pause
