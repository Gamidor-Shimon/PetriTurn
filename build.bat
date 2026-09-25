@echo off
rem Builds the customer package into dist\PetriTurn:
rem   petriturn.exe      robot command line
rem   petriturn_gui.exe  program editor / manual control
rem   petriturn.ini      settings (port, baud rate, timeouts) - read by both
rem   README.md, WIRING.md
rem Copy the whole dist\PetriTurn folder to the customer PC. Python is not needed there.
cd /d "%~dp0"
rem PyInstaller's work folder can end up read-only, and then --clean fails: remove it first.
if exist build (attrib -r build\* /s /d >nul & rmdir /s /q build)
set PYI=.venv\Scripts\python -m PyInstaller --noconfirm --clean --onefile --distpath dist\PetriTurn --workpath build --specpath build

%PYI% --name petriturn --icon ..\host\assets\app.ico host\petriturn.py || goto :fail
%PYI% --windowed --name petriturn_gui --icon ..\host\assets\app.ico --add-data "..\host\assets;assets" host\petriturn_gui.py || goto :fail

copy /y host\petriturn.ini dist\PetriTurn\petriturn.ini >nul || goto :fail
copy /y README.md dist\PetriTurn\README.md >nul || goto :fail
copy /y WIRING.md dist\PetriTurn\WIRING.md >nul || goto :fail
echo.
echo Package ready: %~dp0dist\PetriTurn
exit /b 0

:fail
echo.
echo BUILD FAILED
exit /b 1
