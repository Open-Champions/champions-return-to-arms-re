@echo off
rem install-windows.bat - build the native Champions: Return to Arms from your own disc (see install-windows.ps1).
rem Double-click it.  It runs install-windows.ps1 with PowerShell for this one time (no setting is changed).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-windows.ps1" %*
set RESULT=%ERRORLEVEL%
echo.
pause
exit /b %RESULT%
