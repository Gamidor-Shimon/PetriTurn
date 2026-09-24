@echo off
rem Starts the PetriPlatter Control Center with the project's own Python (.venv), which has PySide6.
rem Double-clicking host\platter_gui.py uses the system Python instead, where PySide6 is not installed.
start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0host\platter_gui.py"
