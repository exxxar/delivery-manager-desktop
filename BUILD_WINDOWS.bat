@echo off
py -3.11 -m venv .venv
call .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm --clean --windowed --name CourierDesktop --add-data "assets;assets" --collect-all PySide6.QtWebEngineCore --collect-all PySide6.QtWebEngineWidgets --collect-all PySide6.QtWebChannel main.py
pause
