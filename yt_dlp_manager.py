import os
import sys
import platform
import subprocess
import logging
from settings_manager import get_yt_dlp_path

logger = logging.getLogger(__name__)

def _no_window_startupinfo():
    if platform.system() == "Windows":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE
        return si
    return None

_MIN_STANDALONE_SIZE = 1_000_000

def get_yt_dlp_dir():
    return get_yt_dlp_path()

def get_yt_dlp_bin_dir():
    return os.path.join(get_yt_dlp_dir(), "bin")

def get_yt_dlp_exe_path():
    exe_name = "yt-dlp.exe" if os.name == "nt" else "yt-dlp"
    return os.path.join(get_yt_dlp_bin_dir(), exe_name)

def is_yt_dlp_installed():
    exe = get_yt_dlp_exe_path()
    if not os.path.exists(exe):
        return False
    size = os.path.getsize(exe)
    ok = size > _MIN_STANDALONE_SIZE
    logger.info(f"Проверка yt-dlp: путь={exe}, размер={size}, standalone={ok}")
    return ok

def get_installed_version():
    exe = get_yt_dlp_exe_path()
    if not os.path.exists(exe):
        return None
    try:
        result = subprocess.run(
            [exe, "--version"],
            capture_output=True, text=True, timeout=30,
            startupinfo=_no_window_startupinfo()
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None

def _get_download_url():
    if os.name == "nt":
        return "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
    import platform
    system = platform.system().lower()
    arch = platform.machine().lower()
    if system == "darwin":
        return f"https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_macos"
    if arch in ("x86_64", "amd64"):
        return "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_linux"
    return f"https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_linux_{arch}"

def install_or_update_yt_dlp(callback=None):
    import requests as _requests

    bin_dir = get_yt_dlp_bin_dir()
    os.makedirs(bin_dir, exist_ok=True)
    exe = get_yt_dlp_exe_path()
    url = _get_download_url()

    if callback:
        callback(f"Скачивание yt-dlp с GitHub...")
        callback(f"URL: {url}")

    temp_file = exe + ".part"
    max_retries = 3
    try:
        for attempt in range(1, max_retries + 1):
            try:
                if callback and max_retries > 1:
                    callback(f"Скачивание yt-dlp... (попытка {attempt}/{max_retries})")

                r = _requests.get(url, stream=True, timeout=60, allow_redirects=True)
                r.raise_for_status()

                total = int(r.headers.get("content-length", 0))
                downloaded = 0
                with open(temp_file, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1024 * 256):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if callback and total > 0:
                                pct = min(100, int(downloaded * 100 / total))
                                callback(f"Скачивание yt-dlp... {pct}%")

                break
            except (_requests.ConnectionError, _requests.Timeout, _requests.HTTPError) as e:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                if attempt < max_retries:
                    if callback:
                        callback(f"Попытка {attempt} не удалась: {e}. Повтор...")
                    logger.warning(f"Попытка {attempt}/{max_retries} не удалась: {e}")
                    import time
                    time.sleep(2 * attempt)
                    continue
                raise

        if os.name != "nt":
            os.chmod(temp_file, 0o755)

        if os.path.exists(exe):
            os.remove(exe)
        os.rename(temp_file, exe)

        size = os.path.getsize(exe)
        if size < _MIN_STANDALONE_SIZE:
            msg = f"Скачанный файл слишком маленький ({size} байт). Возможно, неверная ссылка."
            if callback:
                callback(f"Ошибка: {msg}")
            if os.path.exists(exe):
                os.remove(exe)
            return False, msg

        ver = get_installed_version()
        if callback:
            callback(f"yt-dlp установлен! Версия: {ver or 'неизвестна'}")
        return True, "Успешно"

    except Exception as e:
        if os.path.exists(temp_file):
            os.remove(temp_file)
        msg = f"Ошибка скачивания: {e}"
        if callback:
            callback(f"Ошибка: {msg}")
        logger.error(f"Ошибка установки yt-dlp: {e}", exc_info=True)
        return False, msg

def ensure_yt_dlp_installed(callback=None):
    if not is_yt_dlp_installed():
        if callback:
            callback("yt-dlp не найден. Начинаем установку...")
        success, _ = install_or_update_yt_dlp(callback)
        return success
    return True

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
                timeout=10,
                startupinfo=_no_window_startupinfo()
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
            timeout=10,
            startupinfo=_no_window_startupinfo()
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
