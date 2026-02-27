import os
import sys
import subprocess
import shutil
import logging
import importlib.util
from settings_manager import get_yt_dlp_path

logger = logging.getLogger(__name__)

def get_yt_dlp_dir():
    return get_yt_dlp_path()

def get_yt_dlp_bin_dir():
    yt_path = get_yt_dlp_dir()
    return os.path.join(yt_path, "bin")

def is_yt_dlp_installed():
    yt_path = get_yt_dlp_dir()
    bin_path = get_yt_dlp_bin_dir()
    yt_dlp_exe = os.path.join(bin_path, "yt-dlp.exe" if os.name == "nt" else "yt-dlp")
    exists = os.path.exists(yt_dlp_exe)
    logger.info(f"Проверка yt-dlp: путь={yt_dlp_exe}, существует={exists}")
    return exists

def get_installed_version():
    yt_path = get_yt_dlp_dir()
    bin_path = get_yt_dlp_bin_dir()
    yt_dlp_exe = os.path.join(bin_path, "yt-dlp.exe" if os.name == "nt" else "yt-dlp")
    
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

def get_python_executable():
    if getattr(sys, 'frozen', False):
        python_exe = shutil.which('python')
        if python_exe:
            return python_exe
        if os.name == 'nt':
            python_exe = os.path.join(sys.prefix, 'python.exe')
            if os.path.exists(python_exe):
                return python_exe
        return sys.executable
    return sys.executable

def install_or_update_yt_dlp(callback=None):
    yt_path = get_yt_dlp_dir()
    os.makedirs(yt_path, exist_ok=True)
    
    if callback:
        callback("Создание папки для yt-dlp...")
    
    pip_path = get_python_executable()
    logger.info(f"Используем Python: {pip_path}")
    
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
    bin_path = get_yt_dlp_bin_dir()
    if bin_path not in sys.path:
        sys.path.insert(0, bin_path)

def get_yt_dlp_exe_path():
    yt_path = get_yt_dlp_dir()
    bin_path = get_yt_dlp_bin_dir()
    return os.path.join(bin_path, "yt-dlp.exe" if os.name == "nt" else "yt-dlp")

def get_deno_path():
    if os.name == "nt":
        return os.path.join(os.getcwd(), "deno", "deno.exe")
    return os.path.join(os.getcwd(), "deno", "deno")

def is_deno_installed():
    deno_path = get_deno_path()
    exists = os.path.exists(deno_path)
    if exists:
        try:
            result = subprocess.run(
                [deno_path, "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                logger.info(f"Deno found: {result.stdout.strip()}")
                return True
        except Exception as e:
            logger.warning(f"Deno found but failed to run: {e}")
    logger.info(f"Deno not found at: {deno_path}")
    return False

def install_deno(callback=None):
    import urllib.request
    import zipfile
    import io
    
    deno_dir = os.path.join(os.getcwd(), "deno")
    os.makedirs(deno_dir, exist_ok=True)
    
    deno_path = get_deno_path()
    
    if callback:
        callback("Скачивание Deno...")
    
    try:
        if os.name == "nt":
            url = "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip"
        else:
            import platform
            system = platform.system().lower()
            arch = platform.machine().lower()
            if system == "darwin":
                url = f"https://github.com/denoland/deno/releases/latest/download/deno-{arch}-apple-darwin.zip"
            else:
                url = f"https://github.com/denoland/deno/releases/latest/download/deno-{arch}-unknown-linux-gnu.zip"
        
        logger.info(f"Downloading deno from: {url}")
        
        def reporthook(block_num, block_size, total_size):
            if callback and total_size > 0:
                percent = min(100, int(block_num * block_size * 100 / total_size))
                callback(f"Скачивание Deno... {percent}%")
        
        temp_zip = os.path.join(deno_dir, "deno.zip")
        urllib.request.urlretrieve(url, temp_zip, reporthook)
        
        if callback:
            callback("Распаковка Deno...")
        
        with zipfile.ZipFile(temp_zip, 'r') as z:
            z.extractall(deno_dir)
        
        os.remove(temp_zip)
        
        os.chmod(deno_path, 0o755)
        
        result = subprocess.run(
            [deno_path, "--version"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if callback:
            callback(f"Deno установлен: {result.stdout.strip()}")
        
        logger.info(f"Deno installed successfully: {result.stdout.strip()}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to install deno: {e}")
        if callback:
            callback(f"Ошибка установки Deno: {str(e)}")
        return False

def ensure_deno_installed(callback=None):
    if not is_deno_installed():
        if callback:
            callback("Deno не найден. Установка...")
        return install_deno(callback)
    return True
