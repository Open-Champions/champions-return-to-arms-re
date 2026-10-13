@echo off
rem online.bat - start the native build of Champions: Return to Arms and go online by itself.
rem Drag your own disc image (.iso) of SLUS-20973 v2.00 onto this file, or run:
rem     online.bat "C:\path\to\image.iso"                 to the lobby's list of games
rem     online.bat "C:\path\to\image.iso" host            open a game; its code appears in the window's title
rem     online.bat "C:\path\to\image.iso" join CODE       join the game with that code
rem The lobby server's address is the first line of server.txt in this folder (see that file).
rem The log of the run is written to rta-data\rta_app-log.txt beside this file.
cd /d "%~dp0"
if "%~1"=="" (
  echo Drag your disc image of Champions: Return to Arms ^(.iso^) onto online.bat
  pause
  exit /b 1
)
set MODE=--online
if /i "%~2"=="host" set MODE=--host %3
if /i "%~2"=="join" set MODE=--join %3
if "%~2"=="" (
  echo.
  echo   1  go to the lobby's list of games
  echo   2  open a game of your own ^(you get a code for your friend^)
  echo   3  join a friend's game ^(you need the code^)
  echo.
  set /p CHOICE=Type 1, 2 or 3 and press Enter:
)
if "%~2"=="" if "%CHOICE%"=="2" set MODE=--host
if "%~2"=="" if "%CHOICE%"=="3" (
  set /p CODE=The game's code:
)
if "%~2"=="" if "%CHOICE%"=="3" set MODE=--join %CODE%
rta_app.exe --disc "%~1" %MODE%
if errorlevel 1 (
  echo rta_app.exe ended with an error. The log is in rta-data\rta_app-log.txt
  pause
)
