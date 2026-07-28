import os
import sys
import json

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

SETTINGS_FILE = os.path.join(BASE_DIR, "settings.json")

DEFAULT_SETTINGS = {
    "ffmpeg_path": "./",
    "yt_dlp_path": "./yt_dlp",
    "download_path": "",
    "auth_mode": "none",
    "auth_browser": "chrome",
    "cookies_file": "",
    "download_format": 0,
    "download_quality": 0,
    "vmaf_subsample": 5,
    "chunk_count": 5,
    "chunk_duration": 2
}

_settings_cache = None

def load_settings():
    global _settings_cache
    if _settings_cache is not None:
        return _settings_cache
    
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                _settings_cache = json.load(f)
                for k, v in DEFAULT_SETTINGS.items():
                    if k not in _settings_cache:
                        _settings_cache[k] = v
        except (json.JSONDecodeError, IOError):
            _settings_cache = DEFAULT_SETTINGS.copy()
    else:
        _settings_cache = DEFAULT_SETTINGS.copy()
    
    return _settings_cache

def save_settings(settings):
    global _settings_cache
    with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(settings, f, indent=4, ensure_ascii=False)
    _settings_cache = settings

def get_ffmpeg_path():
    settings = load_settings()
    return settings.get("ffmpeg_path", DEFAULT_SETTINGS["ffmpeg_path"])

def get_ffprobe_path():
    settings = load_settings()
    base_path = settings.get("ffmpeg_path", DEFAULT_SETTINGS["ffmpeg_path"])
    if base_path == "./" or base_path == ".":
        base_path = BASE_DIR
    else:
        base_path = os.path.abspath(base_path)
    
    ext = ".exe" if os.name == "nt" else ""
    return os.path.join(base_path, f"ffprobe{ext}")

def get_actual_ffmpeg_path():
    settings = load_settings()
    base_path = settings.get("ffmpeg_path", DEFAULT_SETTINGS["ffmpeg_path"])
    if base_path == "./" or base_path == ".":
        base_path = BASE_DIR
    else:
        base_path = os.path.abspath(base_path)
    
    ext = ".exe" if os.name == "nt" else ""
    return os.path.join(base_path, f"ffmpeg{ext}")

def get_yt_dlp_path():
    settings = load_settings()
    yt_path = settings.get("yt_dlp_path", DEFAULT_SETTINGS["yt_dlp_path"])
    if yt_path == "./yt_dlp" or yt_path == "./yt_dlp/" or yt_path == "yt_dlp":
        return os.path.join(BASE_DIR, "yt_dlp")
    if os.path.isabs(yt_path):
        return yt_path
    return os.path.join(BASE_DIR, yt_path)

def get_user_data_dir():
    user_data_path = os.path.join(BASE_DIR, "user_data")
    os.makedirs(user_data_path, exist_ok=True)
    return user_data_path

def get_cookies_path():
    return os.path.join(get_user_data_dir(), "cookies_youtube.txt")

def is_authenticated():
    cookies_path = get_cookies_path()
    if os.path.exists(cookies_path):
        return os.path.getsize(cookies_path) > 0
    return False