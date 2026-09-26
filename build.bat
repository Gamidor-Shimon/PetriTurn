@echo off
rem Builds the PetriTurn installer:  PetriTurn\PetriTurn-Setup-<version>.exe
rem One file: copy it to the customer PC and run it (Python is not needed there).
rem   1. PyInstaller -> dist\PetriTurn\petriturn.exe (robot) and petriturn_gui.exe (GUI)
rem   2. Inno Setup  -> the installer (installer\PetriTurn.iss)
cd /d "%~dp0"
rem PyInstaller's work folder can end up read-only, and then --clean fails: remove it first.
if exist build (attrib -r build\* /s /d >nul & rmdir /s /q build)
if exist dist\PetriTurn rmdir /s /q dist\PetriTurn
set PYI=.venv\Scripts\python -m PyInstaller --noconfirm --clean --onefile --distpath dist\PetriTurn --workpath build --specpath build

%PYI% --name petriturn --icon ..\host\assets\app.ico host\petriturn.py || goto :fail
%PYI% --windowed --name petriturn_gui --icon ..\host\assets\app.ico --add-data "..\host\assets;assets" host\petriturn_gui.py || goto :fail

set ISCC=
for %%P in ("%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" "%ProgramFiles%\Inno Setup 6\ISCC.exe" "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe") do if exist %%P set ISCC=%%P
if not defined ISCC (
    echo.
    echo Inno Setup 6 is not installed - get it from https://jrsoftware.org/isinfo.php
    goto :fail
)
%ISCC% /Q installer\PetriTurn.iss || goto :fail
echo.
echo Installer ready:
dir /b PetriTurn\PetriTurn-Setup-*.exe
exit /b 0

:fail
echo.
echo BUILD FAILED
exit /b 1
