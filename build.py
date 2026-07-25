import os
import sys
import subprocess
import shutil
import logging
from pathlib import Path

# Fix Windows console encoding for emoji output
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    print(f"[DEBUG] Windows console encoding fixed to UTF-8 (platform: {sys.platform})")
    logging.debug(f"[Build] Console encoding зафиксирована как UTF-8 для Windows")

def build_exe():
    """Сборка exe файла с помощью PyInstaller"""
    logging.info("[Build] Запуск процесса сборки exe")
    
    # Проверяем наличие main.py
    if not os.path.exists("main.py"):
        logging.error("[Build] Файл main.py не найден в текущей директории")
        print("ОШИБКА: Файл main.py не найден")
        return False
    logging.debug(f"[Build] main.py найден (размер: {os.path.getsize('main.py')} байт)")
    
    # Проверяем установку PyInstaller
    try:
        import PyInstaller
        logging.info(f"[Build] PyInstaller найден (версия: {PyInstaller.__version__})")
        print(f"PyInstaller версия: {PyInstaller.__version__}")
    except ImportError:
        logging.warning("[Build] PyInstaller не найден, установка...")
        print("Установка PyInstaller...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
            logging.info("[Build] PyInstaller успешно установлен")
        except subprocess.CalledProcessError as e:
            logging.error(f"[Build] Ошибка установки PyInstaller: {e}")
            print(f"ОШИБКА: Не удалось установить PyInstaller: {e}")
            return False
    
    # Создаем spec файл с нужными настройками
    spec_content = '''
# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'PySide6.QtCore', 'PySide6.QtGui', 'PySide6.QtWidgets',
        'requests', 'urllib3', 'certifi',
        'optparse'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # === QtWebEngine (Chromium) — ~100-130 МБ, не нужен ===
        'PySide6.QtWebEngineWidgets', 'PySide6.QtWebEngineCore',
        'PySide6.QtWebChannel', 'PySide6.QtWebEngine',
        # === yt-dlp — скачивается при первом запуске, не включаем в сборку ===
        'yt_dlp', 'yt_dlp.utils', 'yt_dlp.extractor', 'yt_dlp.postprocessor',
        'Cryptodome', 'websockets', 'mutagen', 'brotli', 'curl_cffi',
        # === Неиспользуемые модули PySide6/Qt6 — экономия ~50-80 МБ ===
        'PySide6.Qt3DCore', 'PySide6.Qt3DRender', 'PySide6.Qt3DInput',
        'PySide6.Qt3DLogic', 'PySide6.Qt3DExtras', 'PySide6.Qt3DAnimation',
        'PySide6.Qt3DQuickCore', 'PySide6.Qt3DQuickRender', 'PySide6.Qt3DQuickInput',
        'PySide6.Qt3DQuickExtras', 'PySide6.Qt3DQuickAnimation', 'PySide6.Qt3DQuickLogic',
        'PySide6.Qt3DQuickScene3D',
        'PySide6.QtCharts', 'PySide6.QtChartsQml',
        'PySide6.QtDataVisualization',
        'PySide6.QtRemoteObjects', 'PySide6.QtRemoteObjectsQml',
        'PySide6.QtScxml',
        'PySide6.QtStateMachine',
        'PySide6.QtTest',
        'PySide6.QtQuick3D', 'PySide6.QtQuick3DHelpers', 'PySide6.QtQuick3DHelpersImpl',
        'PySide6.QtQuick3DRuntimeRender', 'PySide6.QtQuick3DAssetImport',
        'PySide6.QtSensors',
        'PySide6.QtSql',
        'PySide6.QtSpatialAudio',
        'PySide6.QtLabsWavefrontMesh', 'PySide6.QtLabsSharedImage',
        'PySide6.QtQuickVectorImageGenerator',
        'PySide6.QtSerialPort',
        'PySide6.QtMultimedia', 'PySide6.QtMultimediaWidgets',
        'PySide6.QtPdf', 'PySide6.QtPdfWidgets',
        'PySide6.QtPositioning',
        'PySide6.QtTextToSpeech',
        'PySide6.QtWebView',
        'PySide6.QtVirtualKeyboard',
        'PySide6.QtNetworkAuth',
        'PySide6.QtConcurrent',
        'PySide6.QtOpenGLWidgets',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='VideoCompressor',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
'''
    
    # Записываем spec файл
    spec_path = 'VideoCompressor.spec'
    with open(spec_path, 'w', encoding='utf-8') as f:
        f.write(spec_content)
    logging.info(f"[Build] Spec файл записан: {spec_path}")
    
    print("Начинаю сборку exe файла...")
    print("Это может занять несколько минут...")
    logging.info("[Build] Запуск PyInstaller...")
    
    # Запускаем сборку
    try:
        subprocess.check_call([sys.executable, "-m", "PyInstaller", "--clean", spec_path])
        logging.info("[Build] PyInstaller завершил работу")
        
        # Проверяем результат
        exe_path = Path("dist/VideoCompressor.exe")
        if exe_path.exists():
            exe_size = exe_path.stat().st_size
            logging.info(f"[Build] EXE создан: {exe_path.absolute()} ({exe_size / (1024*1024):.1f} МБ)")
            print(f"\n✅ Сборка успешно завершена!")
            print(f"📁 Исполняемый файл находится: {exe_path.absolute()}")
            
            # Создаем папку для релиза
            release_dir = Path("release")
            release_dir.mkdir(exist_ok=True)
            
            # Копируем exe в папку релиза
            release_exe = release_dir / "VideoCompressor.exe"
            shutil.copy2(exe_path, release_exe)
            logging.info(f"[Build] EXE скопирован в release: {release_exe.absolute()}")
            
            # Удаляем папку dist после успешного копирования
            dist_dir = Path("dist")
            if dist_dir.exists():
                shutil.rmtree(dist_dir)
                logging.debug("[Build] Папка dist удалена")
                print(f"🗑️  Папка dist удалена")
            
            print(f"📦 Готовый к распространению файл: {release_exe.absolute()}")
            print("\nℹ️  Примечание:")
            print("   - Все зависимости Python включены в exe файл")
            print("   - FFmpeg будет загружен автоматически при первом запуске (если не найден)")
            print("   - yt-dlp устанавливается при первом запуске (вкладка Настройки)")
            print("   - Для работы YouTube Downloader нажмите 'Установить/Обновить yt-dlp'")
            
            return True
        else:
            logging.error("[Build] Ошибка: exe файл не был создан после сборки")
            print("❌ Ошибка: exe файл не был создан")
            return False
            
    except subprocess.CalledProcessError as e:
        logging.error(f"[Build] Ошибка PyInstaller: {e}", exc_info=True)
        print(f"❌ Ошибка при сборке: {e}")
        return False
    except Exception as e:
        logging.error(f"[Build] Непредвиденная ошибка сборки: {e}", exc_info=True)
        print(f"❌ Непредвиденная ошибка: {e}")
        return False

if __name__ == "__main__":
    print("=== Сборщик VideoCompressor ===\n")
    success = build_exe()
    if success:
        input("\nНажмите Enter для выхода...")
    else:
        input("\nСборка завершилась с ошибками. Нажмите Enter для выхода...")
        sys.exit(1)