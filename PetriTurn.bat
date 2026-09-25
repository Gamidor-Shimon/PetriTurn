@echo off
rem Starts the PetriTurn Control Center with the project's own Python (.venv), which has PySide6.
rem Double-clicking host\petriturn_gui.py uses the system Python instead, where PySide6 is not installed.
start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0host\petriturn_gui.py"
