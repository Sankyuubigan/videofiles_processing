@echo off
echo [Build] Сборка VideoCompressor.exe в папку release/...
pyinstaller --clean --onefile --windowed --distpath=release --workpath=build --specpath=. --add-data "info.md;." --name=VideoCompressor --hidden-import=PySide6.QtCore --hidden-import=PySide6.QtGui --hidden-import=PySide6.QtWidgets --hidden-import=requests --hidden-import=urllib3 --hidden-import=certifi --exclude-module=PySide6.QtWebEngineWidgets --exclude-module=PySide6.QtWebEngineCore --exclude-module=yt_dlp main.py
echo [Build] Готово! exe находится в release\VideoCompressor.exe
pause
