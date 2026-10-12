@echo off
rem play.bat - start the native build of Champions: Return to Arms.
rem Drag your own disc image (.iso) of SLUS-20973 v2.00 onto this file, or run:  play.bat "C:\path\to\image.iso"
rem The log of the run is written to rta-data\rta_app-log.txt beside this file.
cd /d "%~dp0"
if "%~1"=="" (
  echo Drag your disc image of Champions: Return to Arms ^(.iso^) onto play.bat
  pause
  exit /b 1
)
rta_app.exe --disc "%~1" %2 %3 %4 %5 %6 %7 %8 %9
if errorlevel 1 (
  echo rta_app.exe ended with an error. The log is in rta-data\rta_app-log.txt
  pause
)
