@echo off
rem Builds the customer package into dist\PetriPlatter:
rem   platter.exe      robot command line
rem   platter_gui.exe  program editor / manual control
rem   platter.ini      settings (port, baud rate, timeouts) - read by both
rem   README.md, WIRING.md
rem Copy the whole dist\PetriPlatter folder to the customer PC. Python is not needed there.
cd /d "%~dp0"
set PYI=.venv\Scripts\pyinstaller --noconfirm --clean --onefile --distpath dist\PetriPlatter --workpath build --specpath build

%PYI% --name platter --icon ..\host\assets\app.ico host\platter.py || goto :fail
%PYI% --windowed --name platter_gui --icon ..\host\assets\app.ico --add-data "..\host\assets;assets" host\platter_gui.py || goto :fail

copy /y host\platter.ini dist\PetriPlatter\platter.ini >nul || goto :fail
copy /y README.md dist\PetriPlatter\README.md >nul || goto :fail
copy /y WIRING.md dist\PetriPlatter\WIRING.md >nul || goto :fail
echo.
echo Package ready: %~dp0dist\PetriPlatter
exit /b 0

:fail
echo.
echo BUILD FAILED
exit /b 1
