from PySide6.QtCore import QThread, Signal
import os
import sys
import logging
import traceback
from settings_manager import get_yt_dlp_path, get_actual_ffmpeg_path
from yt_dlp_manager import get_yt_dlp_bin_dir, get_deno_path

class YoutubeDownloadWorker(QThread):
    progress_signal = Signal(str)
    percent_signal = Signal(int)
    finished_signal = Signal()
    error_signal = Signal(str)
    log_signal = Signal(str)
    
    def __init__(self, url, path, format_type='mp4', resolution=None, auth_mode='none', browser_name=None, cookies_file=None):
        super().__init__()
        self.url = url
        self.path = path
        self.format_type = format_type
        self.resolution = resolution
        self.auth_mode = auth_mode
        self.browser_name = browser_name
        self.cookies_file = cookies_file
    
    def run(self):
        yt_path = get_yt_dlp_path()
        bin_path = get_yt_dlp_bin_dir()
        if yt_path not in sys.path: sys.path.insert(0, yt_path)
        if bin_path not in sys.path: sys.path.insert(0, bin_path)
        
        try:
            import yt_dlp
        except ImportError:
            self.error_signal.emit("Модуль yt_dlp не найден. Обновите его в настройках.")
            return

        deno_path = get_deno_path()
        deno_dir = os.path.dirname(deno_path)
        if os.path.exists(deno_path) and deno_dir not in os.environ.get("PATH", ""):
            os.environ["PATH"] = deno_dir + os.pathsep + os.environ.get("PATH", "")
            self.log_signal.emit(f"[INFO] Deno добавлен в PATH для обхода блокировок YouTube")
        
        res_str = f"[height<={self.resolution}]" if self.resolution else ""
        
        if self.format_type == 'mp4':
            format_str = f'bestvideo[ext=mp4]{res_str}+bestaudio[ext=m4a]/best[ext=mp4]{res_str}/best{res_str}/best'
            merge_format = 'mp4'
        elif self.format_type == 'mp3':
            format_str = 'bestaudio/best'
            merge_format = None
        else:
            format_str = f'bestvideo{res_str}+bestaudio/best{res_str}/best'
            merge_format = 'mkv'
            
        outtmpl = os.path.join(self.path, '%(title)s.%(ext)s')
        
        ydl_opts = {
            'format': format_str,
            'outtmpl': outtmpl,
            'progress_hooks':[self.progress_hook],
            'noplaylist': True,
            'socket_timeout': 60,
            'retries': 10,
            'ignoreerrors': False,
            'quiet': True,
            'no_warnings': True,
            'verbose': False,
            'ffmpeg_location': get_actual_ffmpeg_path(),
        }
        
        if merge_format: ydl_opts['merge_output_format'] = merge_format
        if self.format_type == 'mp3':
            ydl_opts['postprocessors'] =[{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}]
            
        if self.auth_mode == 'browser' and self.browser_name:
            ydl_opts['cookiesfrombrowser'] = (self.browser_name,)
            self.log_signal.emit(f"[INFO] Используются cookies из браузера: {self.browser_name}")
        elif self.auth_mode == 'file' and self.cookies_file:
            ydl_opts['cookiefile'] = self.cookies_file
            self.log_signal.emit(f"[INFO] Используются cookies из файла: {self.cookies_file}")
        else:
            self.log_signal.emit("[INFO] Скачивание без авторизации (анонимно)")
        
        if os.path.exists(deno_path):
            ydl_opts['js_runtimes'] = {'deno': {'exe': deno_path}}
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                self.log_signal.emit("--- Анализ видео ---")
                info = ydl.extract_info(self.url, download=False)
                if info is None:
                    self.error_signal.emit("Ошибка: не удалось получить информацию о видео (возрастное ограничение?)")
                    return
                self.log_signal.emit(f"Название: {info.get('title', 'Video')}")
                self.log_signal.emit("\n--- Начало загрузки ---")
                ydl.download([self.url])
            self.finished_signal.emit()
            
        except Exception as e:
            self.log_signal.emit(f"\n=== КРИТИЧЕСКАЯ ОШИБКА ===\nСообщение: {str(e)}")
            self.error_signal.emit(str(e))
    
    def progress_hook(self, d):
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate')
            downloaded = d.get('downloaded_bytes', 0)
            if total:
                percent = int(downloaded / total * 100)
                self.percent_signal.emit(percent)
                speed = d.get('speed', 0)
                if speed:
                    self.progress_signal.emit(f"Скачивание: {percent}% ({speed / 1024 / 1024:.1f} MB/s)")
                else:
                    self.progress_signal.emit(f"Скачивание: {percent}%")
        elif d['status'] == 'finished':
            self.percent_signal.emit(100)
            self.progress_signal.emit("Обработка (ffmpeg)...")
            self.log_signal.emit("Загрузка завершена. Идет склейка (если нужно)...")