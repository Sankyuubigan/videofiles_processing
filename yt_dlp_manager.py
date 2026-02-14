import os
import sys
import subprocess
import shutil
from settings_manager import get_yt_dlp_path

def get_yt_dlp_dir():
    return get_yt_dlp_path()

def is_yt_dlp_installed():
    yt_path = get_yt_dlp_dir()
    yt_dlp_exe = os.path.join(yt_path, "yt-dlp.exe" if os.name == "nt" else "yt-dlp")
    return os.path.exists(yt_dlp_exe)

def get_installed_version():
    yt_path = get_yt_dlp_dir()
    yt_dlp_exe = os.path.join(yt_path, "yt-dlp.exe" if os.name == "nt" else "yt-dlp")
    
    if not os.path.exists(yt_dlp_exe):
        return None
    
    try:
        result = subprocess.run(
            [yt_dlp_exe, "--version"],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None

def install_or_update_yt_dlp(callback=None):
    yt_path = get_yt_dlp_dir()
    os.makedirs(yt_path, exist_ok=True)
    
    if callback:
        callback("Создание папки для yt-dlp...")
    
    pip_path = sys.executable
    
    cmd = [
        pip_path, "-m", "pip", "install",
        "--upgrade",
        "--target", yt_path,
        "--pre", "yt-dlp[default]"
    ]
    
    if callback:
        callback(f"Установка yt-dlp в {yt_path}...")
        callback(f"Команда: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600
        )
        
        if result.returncode != 0:
            error_msg = result.stderr or "Неизвестная ошибка"
            if callback:
                callback(f"Ошибка: {error_msg}")
            return False, error_msg
        
        if callback:
            callback(" yt-dlp успешно установлен!")
        
        return True, "Успешно"
        
    except subprocess.TimeoutExpired:
        if callback:
            callback("Ошибка: Превышен таймаут установки")
        return False, "Таймаут"
    except Exception as e:
        if callback:
            callback(f"Ошибка: {str(e)}")
        return False, str(e)

def ensure_yt_dlp_installed(callback=None):
    if not is_yt_dlp_installed():
        if callback:
            callback("yt-dlp не найден. Начинаем установку...")
        success, msg = install_or_update_yt_dlp(callback)
        return success
    return True

def add_yt_dlp_to_path():
    yt_path = get_yt_dlp_dir()
    if yt_path not in sys.path:
        sys.path.insert(0, yt_path)

def get_yt_dlp_exe_path():
    yt_path = get_yt_dlp_dir()
    return os.path.join(yt_path, "yt-dlp.exe" if os.name == "nt" else "yt-dlp")
