import os
import sys
import subprocess
import shutil
from pathlib import Path

def build_exe():
    """Сборка exe файла с помощью PyInstaller"""
    
    # Проверяем наличие ffmpeg.exe и ffprobe.exe
    required_files = ["ffmpeg.exe", "ffprobe.exe"]
    missing_files = [f for f in required_files if not os.path.exists(f)]
    
    if missing_files:
        print(f"ОШИБКА: Отсутствуют необходимые файлы: {', '.join(missing_files)}")
        print("Убедитесь, что ffmpeg.exe и ffprobe.exe находятся в корневой папке проекта")
        return False
    
    # Проверяем наличие main.py
    if not os.path.exists("main.py"):
        print("ОШИБКА: Файл main.py не найден")
        return False
    
    # Проверяем установку PyInstaller
    try:
        import PyInstaller
    except ImportError:
        print("Установка PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
    
    # Создаем spec файл с нужными настройками
    spec_content = '''
# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('ffmpeg.exe', '.'), ('ffprobe.exe', '.')],
    hiddenimports=['PySide6.QtCore', 'PySide6.QtGui', 'PySide6.QtWidgets'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    upx_exclude=[],
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
    with open('VideoCompressor.spec', 'w', encoding='utf-8') as f:
        f.write(spec_content)
    
    print("Начинаю сборку exe файла...")
    print("Это может занять несколько минут...")
    
    # Запускаем сборку
    try:
        subprocess.check_call([sys.executable, "-m", "PyInstaller", "--clean", "VideoCompressor.spec"])
        
        # Проверяем результат
        exe_path = Path("dist/VideoCompressor.exe")
        if exe_path.exists():
            print(f"\n✅ Сборка успешно завершена!")
            print(f"📁 Исполняемый файл находится: {exe_path.absolute()}")
            
            # Создаем папку для релиза
            release_dir = Path("release")
            release_dir.mkdir(exist_ok=True)
            
            # Копируем exe в папку релиза
            release_exe = release_dir / "VideoCompressor.exe"
            shutil.copy2(exe_path, release_exe)
            
            # Удаляем папку dist после успешного копирования
            dist_dir = Path("dist")
            if dist_dir.exists():
                shutil.rmtree(dist_dir)
                print(f"🗑️  Папка dist удалена")
            
            print(f"📦 Готовый к распространению файл: {release_exe.absolute()}")
            print("\nℹ️  Примечание:")
            print("   - Все зависимости включены в exe файл")
            print("   - FFmpeg встроен в приложение")
            print("   - Дополнительная установка не требуется")
            
            return True
        else:
            print("❌ Ошибка: exe файл не был создан")
            return False
            
    except subprocess.CalledProcessError as e:
        print(f"❌ Ошибка при сборке: {e}")
        return False
    except Exception as e:
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