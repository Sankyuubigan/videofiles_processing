import sys
import os
import shutil
import subprocess
import re
from pathlib import Path
from PySide6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, 
                               QWidget, QPushButton, QLabel, QFileDialog, 
                               QProgressBar, QTextEdit, QSpinBox, QGroupBox, QMessageBox)
from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtGui import QFont
import time
import uuid
import yt_dlp

class WorkerThread(QThread):
    progress_updated = Signal(int, str)
    finished = Signal(str)
    error_occurred = Signal(str)
    debug_info = Signal(str)
    
    def __init__(self, video_path, video_link, volume_ratio):
        super().__init__()
        self.video_path = video_path
        self.video_link = video_link
        self.volume_ratio = volume_ratio
        self.is_downloading = False

    def clean_console_output(self, text):
        """Удаляет ANSI-коды и исправляет кодировку"""
        if not text:
            return ""
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        text = ansi_escape.sub('', text)
        return text.strip()

    def normalize_url(self, url):
        """Приводит ссылку к стандартному виду youtube.com"""
        try:
            if 'youtu.be/' in url:
                # Извлекаем ID из короткой ссылки
                video_id = url.split('youtu.be/')[1].split('?')[0]
                return f"https://www.youtube.com/watch?v={video_id}"
            elif 'youtube.com/shorts/' in url:
                video_id = url.split('shorts/')[1].split('?')[0]
                return f"https://www.youtube.com/watch?v={video_id}"
        except:
            pass
        return url

    def is_file_locked(self, filepath):
        try:
            with open(filepath, 'a') as f:
                pass
            return False
        except IOError:
            return True

    def wait_for_file_unlock(self, filepath, timeout=10):
        self.debug_info.emit(f"Ожидание разблокировки файла: {filepath}")
        for i in range(timeout):
            if not self.is_file_locked(filepath):
                self.debug_info.emit(f"Файл разблокирован через {i} секунд")
                return True
            time.sleep(1)
        return False

    def find_vot_cli(self):
        self.debug_info.emit("Поиск vot-cli в системе...")
        
        possible_cmds = [
            ['vot-cli'],
            [sys.executable, '-m', 'vot_cli'],
        ]
        
        for cmd in possible_cmds:
            try:
                result = subprocess.run(cmd + ['--version'], capture_output=True, encoding='utf-8', errors='replace', timeout=5)
                if result.returncode == 0:
                    self.debug_info.emit(f"Найден vot-cli: {cmd}")
                    return cmd
            except:
                continue

        npm_global = Path(os.environ.get('APPDATA', '')) / 'npm'
        search_paths = [npm_global]
        
        try:
            res = subprocess.run(['where', 'vot-cli'], capture_output=True, encoding='utf-8', errors='replace')
            if res.returncode == 0:
                search_paths.insert(0, Path(res.stdout.split('\n')[0]).parent)
        except:
            pass

        for path in search_paths:
            if not path.exists(): continue
            for ext in ['.cmd', '.bat', '.exe', '']:
                f = path / f"vot-cli{ext}"
                if f.exists():
                    self.debug_info.emit(f"Найден файл: {f}")
                    if ext in ['.cmd', '.bat']:
                        return ['cmd', '/c', str(f)]
                    return [str(f)]
        
        return None

    def download_progress_hook(self, d):
        if d['status'] == 'downloading':
            try:
                p = d.get('_percent_str', '0%').replace('%','')
                speed = d.get('_speed_str', 'N/A')
                self.progress_updated.emit(int(float(p)), f"Скачивание: {p}% ({speed})")
            except:
                pass
        elif d['status'] == 'finished':
            self.progress_updated.emit(100, "Скачивание завершено, обработка...")

    def run(self):
        temp_dir = None
        working_video_path = None
        
        try:
            temp_dir = Path('./temp').resolve()
            temp_audio_dir = temp_dir / 'audio'
            temp_download_dir = temp_dir / 'video_dl'
            
            self.progress_updated.emit(0, "Подготовка рабочих директорий...")
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
            
            temp_dir.mkdir(parents=True, exist_ok=True)
            temp_audio_dir.mkdir(exist_ok=True)
            temp_download_dir.mkdir(exist_ok=True)

            # Нормализация ссылки перед использованием
            original_link = self.video_link
            self.video_link = self.normalize_url(self.video_link)
            if original_link != self.video_link:
                self.debug_info.emit(f"Ссылка преобразована: {original_link} -> {self.video_link}")
            
            # --- ЛОГИКА ПОЛУЧЕНИЯ ВИДЕО ---
            if self.video_path is not None:
                self.progress_updated.emit(10, "Копирование локального видеофайла...")
                unique_id = str(uuid.uuid4())[:8]
                safe_filename = f"original_video_{unique_id}.mp4"
                working_video_path = Path.cwd() / safe_filename
                
                self.debug_info.emit(f"Копирование {self.video_path} -> {working_video_path}")
                
                if self.is_file_locked(self.video_path):
                    if not self.wait_for_file_unlock(self.video_path):
                        raise Exception("Файл заблокирован")
                
                shutil.copy2(self.video_path, working_video_path)
                
            else:
                self.progress_updated.emit(5, "Инициализация скачивания с YouTube...")
                self.debug_info.emit(f"Скачивание видео: {self.video_link}")
                
                ydl_opts = {
                    'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                    'outtmpl': str(temp_download_dir / 'downloaded_video.%(ext)s'),
                    'progress_hooks': [self.download_progress_hook],
                    'noplaylist': True,
                    'quiet': True,
                    'no_warnings': True,
                    'merge_output_format': 'mp4'
                }
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([self.video_link])
                
                files = list(temp_download_dir.glob('*'))
                if not files:
                    raise Exception("Ошибка: Видео не скачалось")
                
                downloaded_file = files[0]
                self.debug_info.emit(f"Видео скачано: {downloaded_file}")
                
                unique_id = str(uuid.uuid4())[:8]
                working_video_path = Path.cwd() / f"downloaded_{unique_id}{downloaded_file.suffix}"
                shutil.move(str(downloaded_file), str(working_video_path))

            self.debug_info.emit(f"Рабочий файл: {working_video_path}")

            # --- ЛОГИКА ПЕРЕВОДА (VOT-CLI) ---
            self.progress_updated.emit(30, "Поиск vot-cli...")
            vot_cmd = self.find_vot_cli()
            
            if not vot_cmd:
                raise Exception("vot-cli не найден! Установите его через npm install -g vot-cli")
            
            self.progress_updated.emit(40, "Запрос перевода (vot-cli)...")
            
            abs_audio_path = str(temp_audio_dir)
            
            cmd = vot_cmd + [self.video_link, '--output', abs_audio_path]
            self.debug_info.emit(f"CMD: {' '.join(cmd)}")
            
            # Небольшая пауза перед запросом к API
            time.sleep(1)
            
            result = subprocess.run(cmd, capture_output=True, encoding='utf-8', errors='replace', timeout=300)
            
            clean_stdout = self.clean_console_output(result.stdout)
            clean_stderr = self.clean_console_output(result.stderr)
            
            if clean_stdout:
                self.debug_info.emit(f"VOT STDOUT:\n{clean_stdout}")
            if clean_stderr:
                self.debug_info.emit(f"VOT STDERR:\n{clean_stderr}")
            
            if result.returncode != 0:
                raise Exception(f"Ошибка vot-cli: {clean_stderr if clean_stderr else clean_stdout}")
            
            audio_files = list(temp_audio_dir.glob('*'))
            if not audio_files:
                error_msg = clean_stdout if clean_stdout else clean_stderr
                
                # Формируем расширенное объяснение ошибки
                reason = "Неизвестная ошибка"
                if "Failed to request" in error_msg or "Возникла ошибка" in error_msg:
                    reason = """
Яндекс отклонил запрос на перевод. Возможные причины:
1. ВАШ IP ЗАБЛОКИРОВАН: Яндекс часто банит запросы с VPN или хостингов. Попробуйте сменить IP.
2. ВИДЕО 18+: Яндекс не переводит видео с возрастными ограничениями.
3. НЕТ РЕЧИ: В видео отсутствует распознаваемая речь.
4. ОШИБКА API: Временный сбой на серверах Яндекса.
"""
                
                raise Exception(f"vot-cli отработал, но перевод не получен.\n{reason}\n\nТехнический ответ:\n{error_msg}")
            
            audio_path = str(audio_files[0])
            self.debug_info.emit(f"Аудио перевода получено: {audio_path}")
            
            # --- СВЕДЕНИЕ (FFMPEG) ---
            self.progress_updated.emit(70, "Сведение видео и дорожек (ffmpeg)...")
            output_filename = f"translated_{int(time.time())}.mp4"
            
            try:
                subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
            except:
                raise Exception("ffmpeg не найден в системе")
            
            ffmpeg_cmd = [
                'ffmpeg',
                '-i', str(working_video_path),
                '-i', audio_path,
                '-c:v', 'copy',
                '-filter_complex', 
                f'[0:a] volume={self.volume_ratio} [orig_low]; [orig_low][1:a] amix=inputs=2:duration=longest [mixed_out]',
                '-map', '0:v',
                '-map', '[mixed_out]',
                '-map', '0:a',
                '-metadata:s:a:0', 'title=Translated / Перевод',
                '-metadata:s:a:1', 'title=Original / Оригинал',
                '-disposition:a:0', 'default',
                '-y', output_filename
            ]
            
            self.debug_info.emit(f"FFMPEG: {' '.join(ffmpeg_cmd)}")
            subprocess.run(ffmpeg_cmd, check=True, capture_output=True, encoding='utf-8', errors='replace', timeout=300)
            
            # --- ОЧИСТКА ---
            self.progress_updated.emit(90, "Очистка...")
            if working_video_path.exists():
                try: working_video_path.unlink()
                except: pass
            
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
            
            self.progress_updated.emit(100, "Готово!")
            self.finished.emit(output_filename)
            
        except Exception as e:
            self.error_occurred.emit(self.clean_console_output(str(e)))
        finally:
            if temp_dir and temp_dir.exists():
                try: shutil.rmtree(temp_dir)
                except: pass

class VideoTranslatorGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.video_path = None
        self.initUI()
    
    def initUI(self):
        self.setWindowTitle("Video Translator & Downloader")
        self.setGeometry(100, 100, 800, 750)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # Настройки
        settings_group = QGroupBox("Источник и Настройки")
        settings_layout = QVBoxLayout()
        
        self.link_label = QLabel("YouTube ссылка (для скачивания и перевода):")
        self.link_edit = QTextEdit()
        self.link_edit.setMaximumHeight(50)
        self.link_edit.setPlaceholderText("Вставьте ссылку сюда...")
        
        file_layout = QHBoxLayout()
        self.file_label = QLabel("Локальный файл: Не выбран (будет скачано по ссылке)")
        self.file_label.setStyleSheet("color: gray;")
        self.select_file_btn = QPushButton("Выбрать файл")
        self.select_file_btn.clicked.connect(self.select_file)
        self.clear_file_btn = QPushButton("✕")
        self.clear_file_btn.setFixedWidth(30)
        self.clear_file_btn.clicked.connect(self.clear_file)
        self.clear_file_btn.setEnabled(False)
        
        file_layout.addWidget(self.file_label)
        file_layout.addWidget(self.select_file_btn)
        file_layout.addWidget(self.clear_file_btn)
        
        vol_layout = QHBoxLayout()
        vol_layout.addWidget(QLabel("Громкость оригинала (на дорожке перевода):"))
        self.volume_spinbox = QSpinBox()
        self.volume_spinbox.setRange(0, 100)
        self.volume_spinbox.setValue(20)
        self.volume_spinbox.setSuffix("%")
        vol_layout.addWidget(self.volume_spinbox)
        vol_layout.addStretch()
        
        settings_layout.addWidget(self.link_label)
        settings_layout.addWidget(self.link_edit)
        settings_layout.addLayout(file_layout)
        settings_layout.addLayout(vol_layout)
        settings_group.setLayout(settings_layout)
        
        self.progress_bar = QProgressBar()
        self.status_label = QLabel("Введите ссылку или выберите файл")
        self.status_label.setAlignment(Qt.AlignCenter)
        
        self.start_btn = QPushButton("ЗАПУСК")
        self.start_btn.setMinimumHeight(40)
        self.start_btn.clicked.connect(self.start_processing)
        
        install_layout = QHBoxLayout()
        self.install_btn = QPushButton("Установить/Обновить vot-cli")
        self.install_btn.clicked.connect(self.install_deps)
        install_layout.addWidget(self.install_btn)
        
        log_group = QGroupBox("Лог")
        log_layout = QVBoxLayout()
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        log_layout.addWidget(self.log_text)
        log_group.setLayout(log_layout)
        
        layout.addWidget(settings_group)
        layout.addWidget(self.status_label)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.start_btn)
        layout.addLayout(install_layout)
        layout.addWidget(log_group)
        
        self.worker_thread = None

    def select_file(self):
        f, _ = QFileDialog.getOpenFileName(self, "Видеофайл", "", "Video (*.mp4 *.mkv *.avi *.webm)")
        if f:
            self.video_path = Path(f)
            self.file_label.setText(f"Файл: {self.video_path.name}")
            self.file_label.setStyleSheet("color: black; font-weight: bold;")
            self.clear_file_btn.setEnabled(True)
            self.log_message(f"Выбран локальный файл: {f}")

    def clear_file(self):
        self.video_path = None
        self.file_label.setText("Локальный файл: Не выбран (будет скачано по ссылке)")
        self.file_label.setStyleSheet("color: gray;")
        self.clear_file_btn.setEnabled(False)

    def install_deps(self):
        self.log_message("Обновление vot-cli...")
        try:
            command = 'start "" cmd /c "npm install -g vot-cli@latest && echo. && echo SUCCESS! Closing in 3 seconds... && timeout /t 3"'
            subprocess.Popen(command, shell=True)
            QMessageBox.information(self, "Инфо", "Запущен процесс обновления.\nОкно закроется автоматически через 3 секунды после завершения.")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))

    def log_message(self, msg):
        self.log_text.append(msg)
        sb = self.log_text.verticalScrollBar()
        sb.setValue(sb.maximum())

    def start_processing(self):
        link = self.link_edit.toPlainText().strip()
        
        if not link and not self.video_path:
            QMessageBox.warning(self, "Ошибка", "Укажите ссылку на YouTube или выберите файл!")
            return
            
        if not link and self.video_path:
            QMessageBox.warning(self, "Ошибка", "Для перевода (vot-cli) ОБЯЗАТЕЛЬНО нужна ссылка на YouTube,\nдаже если вы выбрали локальный файл!")
            return

        vol = self.volume_spinbox.value() / 100.0
        
        mode = "СКАЧИВАНИЕ + ПЕРЕВОД" if self.video_path is None else "ЛОКАЛЬНЫЙ ФАЙЛ + ПЕРЕВОД"
        self.log_message(f"--- ЗАПУСК: {mode} ---")
        
        self.start_btn.setEnabled(False)
        self.select_file_btn.setEnabled(False)
        self.progress_bar.setValue(0)
        
        self.worker_thread = WorkerThread(self.video_path, link, vol)
        self.worker_thread.progress_updated.connect(lambda v, m: (self.progress_bar.setValue(v), self.status_label.setText(m)))
        self.worker_thread.debug_info.connect(self.log_message)
        self.worker_thread.error_occurred.connect(self.on_error)
        self.worker_thread.finished.connect(self.on_finished)
        self.worker_thread.start()

    def on_finished(self, filename):
        self.status_label.setText("Готово!")
        self.log_message(f"Успешно сохранено: {filename}")
        QMessageBox.information(self, "Успех", f"Видео готово:\n{filename}\n\nАудиодорожки:\n1. Перевод\n2. Оригинал")
        self.reset_ui()

    def on_error(self, err):
        self.status_label.setText("Ошибка")
        self.log_message(f"ОШИБКА: {err}")
        QMessageBox.critical(self, "Ошибка", err)
        self.reset_ui()

    def reset_ui(self):
        self.start_btn.setEnabled(True)
        self.select_file_btn.setEnabled(True)

    def closeEvent(self, event):
        if self.worker_thread and self.worker_thread.isRunning():
            self.worker_thread.terminate()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = VideoTranslatorGUI()
    w.show()
    sys.exit(app.exec())