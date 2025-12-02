import sys
import os
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, 
                               QLineEdit, QPushButton, QLabel, 
                               QProgressBar, QMessageBox, QFileDialog, QTextEdit)
from PySide6.QtCore import Qt, QThread, Signal
import yt_dlp

class DownloadThread(QThread):
    progress_signal = Signal(str)   # Статус в строку состояния
    percent_signal = Signal(int)    # Процент для бара
    finished_signal = Signal()      # Готово
    error_signal = Signal(str)      # Ошибка
    log_signal = Signal(str)        # <--- Новый сигнал для логов

    def __init__(self, url, path):
        super().__init__()
        self.url = url
        self.path = path

    def run(self):
        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': os.path.join(self.path, '%(title)s.%(ext)s'),
            'progress_hooks': [self.progress_hook],
            'noplaylist': True,
            'socket_timeout': 60,
            'retries': 20,
            'fragment_retries': 20,
            'ignoreerrors': True,
            # Отключаем стандартный вывод в консоль, чтобы не мусорить, 
            # мы всё равно будем ловить инфу сами
            'quiet': True, 
            'no_warnings': True,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                self.log_signal.emit("--- Анализ видео и получение прямых ссылок ---")
                
                # 1. Сначала получаем информацию без скачивания
                info = ydl.extract_info(self.url, download=False)
                
                title = info.get('title', 'Video')
                self.log_signal.emit(f"Название: {title}")

                # 2. Пытаемся найти прямые ссылки
                # YouTube часто отдает видео и звук отдельно (requested_formats)
                if 'requested_formats' in info:
                    for f in info['requested_formats']:
                        ftype = "ВИДЕО" if f.get('vcodec') != 'none' else "АУДИО"
                        note = f.get('format_note', 'unknown')
                        direct_url = f.get('url', 'нет ссылки')
                        
                        self.log_signal.emit(f"\n[{ftype}] Качество: {note}")
                        self.log_signal.emit(f"SOURCE URL: {direct_url}")
                
                # Если файл один (например, старое видео или 720p без склейки)
                elif 'url' in info:
                    self.log_signal.emit(f"\n[ФАЙЛ] Прямая ссылка:")
                    self.log_signal.emit(f"SOURCE URL: {info['url']}")

                self.log_signal.emit("\n--- Начало загрузки ---")

                # 3. Начинаем скачивание
                ydl.download([self.url])
            
            self.finished_signal.emit()

        except Exception as e:
            self.error_signal.emit(str(e))

    def progress_hook(self, d):
        if d['status'] == 'downloading':
            try:
                total = d.get('total_bytes') or d.get('total_bytes_estimate')
                downloaded = d.get('downloaded_bytes', 0)
                
                if total:
                    percent = int(downloaded / total * 100)
                    self.percent_signal.emit(percent)
                    
                    speed = d.get('speed', 0)
                    if speed:
                        speed_mb = speed / 1024 / 1024
                        self.progress_signal.emit(f"Скачивание: {percent}% ({speed_mb:.1f} MB/s)")
                    else:
                        self.progress_signal.emit(f"Скачивание: {percent}%")
            except Exception:
                pass
        elif d['status'] == 'finished':
            self.percent_signal.emit(100)
            self.progress_signal.emit("Обработка (ffmpeg)...")
            self.log_signal.emit("Загрузка завершена. Идет склейка (если нужно)...")

class YoutubeDownloaderApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("YouTube Downloader (With Logger)")
        self.resize(700, 500) # Сделал окно побольше
        
        layout = QVBoxLayout()
        
        # Ввод
        self.label = QLabel("Вставьте ссылку на видео:")
        layout.addWidget(self.label)
        
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://www.youtube.com/watch?v=...")
        layout.addWidget(self.url_input)

        # Папка
        self.path_btn = QPushButton("Выбрать папку для сохранения")
        self.path_btn.clicked.connect(self.choose_folder)
        layout.addWidget(self.path_btn)
        
        self.save_path = os.getcwd()
        self.path_label = QLabel(f"Сохранить в: {self.save_path}")
        self.path_label.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(self.path_label)

        # Кнопка
        self.download_btn = QPushButton("Скачать")
        self.download_btn.setMinimumHeight(40)
        self.download_btn.clicked.connect(self.start_download)
        layout.addWidget(self.download_btn)

        # Прогресс
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("Ожидание...")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)

        # --- ОКНО ЛОГОВ ---
        self.log_label = QLabel("Лог скачивания (прямые ссылки):")
        layout.addWidget(self.log_label)

        self.log_window = QTextEdit()
        self.log_window.setReadOnly(True)
        self.log_window.setStyleSheet("background-color: #1e1e1e; color: #00ff00; font-family: Consolas;")
        layout.addWidget(self.log_window)
        # ------------------

        self.setLayout(layout)

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Выберите папку")
        if folder:
            self.save_path = folder
            self.path_label.setText(f"Сохранить в: {self.save_path}")

    def log_message(self, msg):
        self.log_window.append(msg)
        # Автопрокрутка вниз
        sb = self.log_window.verticalScrollBar()
        sb.setValue(sb.maximum())

    def start_download(self):
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "Ошибка", "Пожалуйста, введите ссылку!")
            return

        self.download_btn.setEnabled(False)
        self.url_input.setEnabled(False)
        self.progress_bar.setValue(0)
        self.status_label.setText("Получение ссылок...")
        self.log_window.clear() # Очистить старые логи

        self.worker = DownloadThread(url, self.save_path)
        self.worker.percent_signal.connect(self.progress_bar.setValue)
        self.worker.progress_signal.connect(self.status_label.setText)
        self.worker.finished_signal.connect(self.on_finished)
        self.worker.error_signal.connect(self.on_error)
        self.worker.log_signal.connect(self.log_message) # Подключаем логи
        self.worker.start()

    def on_finished(self):
        self.status_label.setText("Готово!")
        self.log_message("\n--- УСПЕШНО ЗАВЕРШЕНО ---")
        QMessageBox.information(self, "Успех", "Видео успешно скачано!")
        self.reset_ui()

    def on_error(self, err_msg):
        self.status_label.setText("Ошибка.")
        self.log_message(f"\n--- ОШИБКА ---\n{err_msg}")
        if "timed out" in err_msg:
             QMessageBox.warning(self, "Таймаут", "Соединение разорвано. Попробуйте еще раз.")
        else:
            QMessageBox.critical(self, "Ошибка", "Смотрите детали в окне логов.")
        self.reset_ui()

    def reset_ui(self):
        self.download_btn.setEnabled(True)
        self.url_input.setEnabled(True)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = YoutubeDownloaderApp()
    window.show()
    sys.exit(app.exec())