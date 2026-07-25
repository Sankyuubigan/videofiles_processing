from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, 
                               QLabel, QLineEdit, QPushButton, QMessageBox, 
                               QProgressBar, QTextEdit, QRadioButton, QButtonGroup, 
                               QComboBox, QApplication, QFileDialog)
from PySide6.QtCore import Qt
import os
import logging
from settings_manager import load_settings, save_settings
from yt_dlp_manager import is_yt_dlp_installed, install_or_update_yt_dlp, get_yt_dlp_path
from youtube_worker import YoutubeDownloadWorker

class DownloadTab(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.load_settings_to_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        auth_group = QGroupBox("Авторизация (необходима для видео 18+ и закрытых видео)")
        auth_layout = QVBoxLayout()
        self.auth_group_btn = QButtonGroup(self)
        
        self.auth_none_radio = QRadioButton("Без авторизации (Только для открытых видео)")
        self.auth_group_btn.addButton(self.auth_none_radio)
        auth_layout.addWidget(self.auth_none_radio)
        
        browser_layout = QHBoxLayout()
        self.auth_browser_radio = QRadioButton("Использовать профиль браузера:")
        self.auth_group_btn.addButton(self.auth_browser_radio)
        self.browser_combo = QComboBox()
        self.browser_combo.addItems(["chrome", "edge", "firefox", "brave", "opera", "vivaldi", "safari", "chromium"])
        browser_layout.addWidget(self.auth_browser_radio)
        browser_layout.addWidget(self.browser_combo)
        browser_layout.addStretch()
        auth_layout.addLayout(browser_layout)
        
        file_layout = QHBoxLayout()
        self.auth_file_radio = QRadioButton("Из файла cookies.txt:")
        self.auth_group_btn.addButton(self.auth_file_radio)
        self.cookies_file_input = QLineEdit()
        self.cookies_file_input.setPlaceholderText("Путь к файлу cookies.txt")
        browse_cookies_btn = QPushButton("Обзор")
        browse_cookies_btn.clicked.connect(self.browse_cookies_file)
        file_layout.addWidget(self.auth_file_radio)
        file_layout.addWidget(self.cookies_file_input)
        file_layout.addWidget(browse_cookies_btn)
        auth_layout.addLayout(file_layout)
        
        help_label = QLabel('ℹ️ <b>Для нестандартных браузеров (Thorium, Яндекс и др.):</b> Установите расширение "Get cookies.txt LOCALLY", выгрузите файл <i>cookies.txt</i> и выберите его в пункте выше.')
        help_label.setStyleSheet("color: #aaaaaa; font-size: 11px;")
        help_label.setWordWrap(True)
        auth_layout.addWidget(help_label)
        auth_group.setLayout(auth_layout)
        layout.addWidget(auth_group)
        
        url_layout = QHBoxLayout()
        url_layout.addWidget(QLabel("URL видео:"))
        self.youtube_url_input = QLineEdit()
        self.youtube_url_input.setPlaceholderText("https://www.youtube.com/watch?v=...")
        url_layout.addWidget(self.youtube_url_input)
        layout.addLayout(url_layout)
        
        settings_layout = QHBoxLayout()
        settings_layout.addWidget(QLabel("Формат:"))
        self.download_format_combo = QComboBox()
        self.download_format_combo.addItems(["MP4 (Без конвертации)", "Лучший (Любой формат)", "Только Аудио (MP3)"])
        settings_layout.addWidget(self.download_format_combo)
        settings_layout.addWidget(QLabel("Качество:"))
        self.download_res_combo = QComboBox()
        self.download_res_combo.addItems(["Максимальное", "1080p", "720p", "480p", "360p"])
        settings_layout.addWidget(self.download_res_combo)
        settings_layout.addStretch()
        layout.addLayout(settings_layout)
        
        path_layout = QHBoxLayout()
        path_layout.addWidget(QLabel("Сохранить в:"))
        self.download_path_input = QLineEdit()
        path_layout.addWidget(self.download_path_input)
        download_browse_btn = QPushButton("Обзор")
        download_browse_btn.clicked.connect(self.browse_download_path)
        path_layout.addWidget(download_browse_btn)
        layout.addLayout(path_layout)
        
        self.download_btn = QPushButton("Скачать")
        self.download_btn.setMinimumHeight(40)
        self.download_btn.clicked.connect(self.start_youtube_download)
        layout.addWidget(self.download_btn)
        
        self.download_progress_bar = QProgressBar()
        layout.addWidget(self.download_progress_bar)
        
        self.download_status_label = QLabel("Ожидание...")
        self.download_status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.download_status_label)
        
        layout.addWidget(QLabel("Лог:"))
        self.download_log = QTextEdit()
        self.download_log.setReadOnly(True)
        self.download_log.setStyleSheet("background-color: #1e1e1e; color: #00ff00; font-family: Consolas;")
        layout.addWidget(self.download_log)

    def load_settings_to_ui(self):
        settings = load_settings()
        dl_path = settings.get("download_path", "")
        if not dl_path or not os.path.exists(dl_path): dl_path = os.getcwd()
        self.download_path_input.setText(dl_path)
        
        auth_mode = settings.get("auth_mode", "none")
        if auth_mode == "browser": self.auth_browser_radio.setChecked(True)
        elif auth_mode == "file": self.auth_file_radio.setChecked(True)
        else: self.auth_none_radio.setChecked(True)
            
        self.browser_combo.setCurrentText(settings.get("auth_browser", "chrome"))
        self.cookies_file_input.setText(settings.get("cookies_file", ""))
        self.download_format_combo.setCurrentIndex(settings.get("download_format", 0))
        self.download_res_combo.setCurrentIndex(settings.get("download_quality", 0))

    def save_current_settings(self):
        settings = load_settings()
        settings["download_path"] = self.download_path_input.text().strip()
        if self.auth_browser_radio.isChecked(): settings["auth_mode"] = "browser"
        elif self.auth_file_radio.isChecked(): settings["auth_mode"] = "file"
        else: settings["auth_mode"] = "none"
        settings["auth_browser"] = self.browser_combo.currentText()
        settings["cookies_file"] = self.cookies_file_input.text().strip()
        settings["download_format"] = self.download_format_combo.currentIndex()
        settings["download_quality"] = self.download_res_combo.currentIndex()
        save_settings(settings)

    def browse_cookies_file(self):
        file, _ = QFileDialog.getOpenFileName(self, "Выберите файл cookies.txt", "", "Text Files (*.txt);;All Files (*)")
        if file:
            self.cookies_file_input.setText(file)
            self.auth_file_radio.setChecked(True)

    def browse_download_path(self):
        folder = QFileDialog.getExistingDirectory(self, "Выберите папку для сохранения", self.download_path_input.text())
        if folder: self.download_path_input.setText(folder)
    
    def start_youtube_download(self):
        url = self.youtube_url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "Ошибка", "Введите URL видео!")
            return
            
        self.save_current_settings()
        
        if not is_yt_dlp_installed():
            if QMessageBox.question(self, "yt-dlp не установлен", "Установить yt-dlp сейчас?", QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
                success, msg = install_or_update_yt_dlp()
                if not success:
                    QMessageBox.critical(self, "Ошибка", f"Не удалось установить yt-dlp:\n{msg}")
                    return
            else: return
        
        auth_mode = 'none'
        browser_name = cookies_file = None
        if self.auth_browser_radio.isChecked():
            auth_mode = 'browser'
            browser_name = self.browser_combo.currentText()
        elif self.auth_file_radio.isChecked():
            auth_mode = 'file'
            cookies_file = self.cookies_file_input.text().strip()
            if not cookies_file or not os.path.exists(cookies_file):
                QMessageBox.warning(self, "Ошибка", "Укажите правильный путь к файлу cookies.txt!")
                return
        
        format_idx = self.download_format_combo.currentIndex()
        format_type = 'mp4' if format_idx == 0 else ('best' if format_idx == 1 else 'mp3')
        res_text = self.download_res_combo.currentText()
        resolution = None if res_text == "Максимальное" else res_text.replace("p", "")
        
        self.download_btn.setEnabled(False)
        self.youtube_url_input.setEnabled(False)
        self.download_progress_bar.setValue(0)
        self.download_log.clear()
        
        self.append_download_log(f"Путь к yt-dlp: {get_yt_dlp_path()}")
        self.append_download_log(f"Формат: {format_type.upper()}, Качество: {res_text}")
        
        self.download_worker = YoutubeDownloadWorker(url, self.download_path_input.text(), format_type, resolution, auth_mode, browser_name, cookies_file)
        self.download_worker.progress_signal.connect(self.download_status_label.setText)
        self.download_worker.percent_signal.connect(self.download_progress_bar.setValue)
        self.download_worker.log_signal.connect(self.append_download_log)
        self.download_worker.finished_signal.connect(self.on_download_finished)
        self.download_worker.error_signal.connect(self.on_download_error)
        self.download_worker.start()
    
    def append_download_log(self, msg):
        self.download_log.append(msg)
        logging.info(f"[YouTube DL] {msg}")
        sb = self.download_log.verticalScrollBar()
        sb.setValue(sb.maximum())
    
    def on_download_finished(self):
        self.download_status_label.setText("Готово! Видео скачано.")
        self.download_log.append("\n--- УСПЕШНО ЗАВЕРШЕНО ---")
        QApplication.beep() # Звуковой сигнал об успешном скачивании
        self.download_btn.setEnabled(True)
        self.youtube_url_input.setEnabled(True)
    
    def on_download_error(self, err_msg):
        self.download_status_label.setText("Ошибка")
        self.download_log.append(f"\n--- ОШИБКА ---\n{err_msg}")
        self.download_btn.setEnabled(True)
        self.youtube_url_input.setEnabled(True)