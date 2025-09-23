import os
import requests
import zipfile
import tempfile
import shutil
from pathlib import Path
from PySide6.QtWidgets import QMessageBox


class FFmpegDownloader:
    def __init__(self):
        self.ffmpeg_url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
        
    def check_and_download(self) -> bool:
        """Проверяет наличие FFmpeg и скачивает при необходимости."""
        if os.path.exists("ffmpeg.exe") and os.path.exists("ffprobe.exe"):
            return True
            
        reply = QMessageBox.question(
            None, "FFmpeg не найден",
            "FFmpeg не найден. Скачать автоматически?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            return self.download_ffmpeg()
        return False
        
    def download_ffmpeg(self) -> bool:
        """Скачивает и распаковывает FFmpeg."""
        try:
            response = requests.get(self.ffmpeg_url, stream=True)
            response.raise_for_status()
            
            with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp_file:
                for chunk in response.iter_content(chunk_size=8192):
                    tmp_file.write(chunk)
                tmp_path = tmp_file.name
            
            with zipfile.ZipFile(tmp_path, 'r') as zip_ref:
                for file_info in zip_ref.filelist:
                    if file_info.filename.endswith('ffmpeg.exe'):
                        zip_ref.extract(file_info)
                        extracted = file_info.filename
                        if os.path.exists(extracted):
                            shutil.move(extracted, 'ffmpeg.exe')
                    elif file_info.filename.endswith('ffprobe.exe'):
                        zip_ref.extract(file_info)
                        extracted = file_info.filename
                        if os.path.exists(extracted):
                            shutil.move(extracted, 'ffprobe.exe')
            
            os.unlink(tmp_path)
            
            # Удаляем остатки
            for item in os.listdir('.'):
                if os.path.isdir(item) and 'ffmpeg' in item.lower():
                    shutil.rmtree(item)
            
            return os.path.exists("ffmpeg.exe") and os.path.exists("ffprobe.exe")
            
        except Exception as e:
            QMessageBox.critical(None, "Ошибка", f"Не удалось скачать FFmpeg:\n{str(e)}")
            return False