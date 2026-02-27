from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, QLineEdit, QPushButton, QMessageBox, QApplication, QFileDialog
from PySide6.QtCore import QTimer
import os
from settings_manager import load_settings, save_settings, get_actual_ffmpeg_path
from yt_dlp_manager import is_yt_dlp_installed, get_installed_version, is_deno_installed, ensure_deno_installed, install_or_update_yt_dlp

class SettingsTab(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.load_settings_to_tab()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        ffmpeg_group = QGroupBox("FFmpeg")
        ffmpeg_layout = QVBoxLayout()
        ffmpeg_path_layout = QHBoxLayout()
        ffmpeg_path_layout.addWidget(QLabel("Путь к FFmpeg:"))
        self.ffmpeg_path_input = QLineEdit()
        self.ffmpeg_path_input.setPlaceholderText("./ (папка с программой)")
        ffmpeg_path_layout.addWidget(self.ffmpeg_path_input)
        ffmpeg_browse_btn = QPushButton("Обзор")
        ffmpeg_browse_btn.clicked.connect(self.browse_ffmpeg_path)
        ffmpeg_path_layout.addWidget(ffmpeg_browse_btn)
        ffmpeg_layout.addLayout(ffmpeg_path_layout)
        self.ffmpeg_status_label = QLabel("Статус: не проверено")
        self.ffmpeg_status_label.setStyleSheet("color: gray;")
        ffmpeg_layout.addWidget(self.ffmpeg_status_label)
        ffmpeg_group.setLayout(ffmpeg_layout)
        layout.addWidget(ffmpeg_group)
        
        ytdlp_group = QGroupBox("yt-dlp")
        ytdlp_layout = QVBoxLayout()
        ytdlp_path_layout = QHBoxLayout()
        ytdlp_path_layout.addWidget(QLabel("Путь к yt-dlp:"))
        self.ytdlp_path_input = QLineEdit()
        self.ytdlp_path_input.setPlaceholderText("./yt_dlp")
        ytdlp_path_layout.addWidget(self.ytdlp_path_input)
        ytdlp_browse_btn = QPushButton("Обзор")
        ytdlp_browse_btn.clicked.connect(self.browse_ytdlp_path)
        ytdlp_path_layout.addWidget(ytdlp_browse_btn)
        ytdlp_layout.addLayout(ytdlp_path_layout)
        ytdlp_version_layout = QHBoxLayout()
        self.ytdlp_status_label = QLabel("Статус: не проверено")
        self.ytdlp_status_label.setStyleSheet("color: gray;")
        ytdlp_version_layout.addWidget(self.ytdlp_status_label)
        ytdlp_version_layout.addStretch()
        ytdlp_layout.addLayout(ytdlp_version_layout)
        ytdlp_update_btn = QPushButton("Установить/Обновить yt-dlp")
        ytdlp_update_btn.clicked.connect(self.update_ytdlp_from_settings)
        ytdlp_layout.addWidget(ytdlp_update_btn)
        ytdlp_group.setLayout(ytdlp_layout)
        layout.addWidget(ytdlp_group)
        
        deno_group = QGroupBox("Deno (JavaScript runtime для YouTube)")
        deno_layout = QVBoxLayout()
        deno_version_layout = QHBoxLayout()
        self.deno_status_label = QLabel("Статус: не проверено")
        self.deno_status_label.setStyleSheet("color: gray;")
        deno_version_layout.addWidget(self.deno_status_label)
        deno_version_layout.addStretch()
        deno_layout.addLayout(deno_version_layout)
        deno_group.setLayout(deno_layout)
        layout.addWidget(deno_group)
        
        layout.addStretch()
        save_btn = QPushButton("Сохранить настройки")
        save_btn.clicked.connect(self.save_settings_from_tab)
        layout.addWidget(save_btn)

    def load_settings_to_tab(self):
        settings = load_settings()
        self.ffmpeg_path_input.setText(settings.get("ffmpeg_path", "./"))
        self.ytdlp_path_input.setText(settings.get("yt_dlp_path", "./yt_dlp"))
        self.check_ffmpeg_status()
        self.check_ytdlp_status()
    
    def browse_ffmpeg_path(self):
        folder = QFileDialog.getExistingDirectory(self, "Выберите папку с FFmpeg")
        if folder: self.ffmpeg_path_input.setText(folder)
    
    def browse_ytdlp_path(self):
        folder = QFileDialog.getExistingDirectory(self, "Выберите папку для yt-dlp")
        if folder: self.ytdlp_path_input.setText(folder)
    
    def save_settings_from_tab(self):
        settings = load_settings()
        settings["ffmpeg_path"] = self.ffmpeg_path_input.text().strip() or "./"
        settings["yt_dlp_path"] = self.ytdlp_path_input.text().strip() or "./yt_dlp"
        save_settings(settings)
        self.check_ffmpeg_status()
        self.check_ytdlp_status()
        QMessageBox.information(self, "Сохранено", "Настройки сохранены!")
    
    def check_ffmpeg_status(self):
        ffmpeg_path = get_actual_ffmpeg_path()
        if os.path.exists(ffmpeg_path):
            self.ffmpeg_status_label.setText(f"Статус: найден ({ffmpeg_path})")
            self.ffmpeg_status_label.setStyleSheet("color: green;")
        else:
            self.ffmpeg_status_label.setText("Статус: не найден")
            self.ffmpeg_status_label.setStyleSheet("color: red;")
    
    def check_ytdlp_status(self):
        if is_yt_dlp_installed():
            version = get_installed_version()
            self.ytdlp_status_label.setText(f"Статус: установлен (версия {version})")
            self.ytdlp_status_label.setStyleSheet("color: green;")
        else:
            self.ytdlp_status_label.setText("Статус: не установлен")
            self.ytdlp_status_label.setStyleSheet("color: red;")
        
        if is_deno_installed():
            self.deno_status_label.setText("Статус: установлен")
            self.deno_status_label.setStyleSheet("color: green;")
        else:
            self.deno_status_label.setText("Статус: не установлен (будет установлен автоматически)")
            self.deno_status_label.setStyleSheet("color: orange;")
            QTimer.singleShot(1000, lambda: self._install_deno_background())
    
    def _install_deno_background(self):
        def callback(msg):
            self.deno_status_label.setText(f"Статус: {msg}")
            QApplication.processEvents()
        if ensure_deno_installed(callback):
            self.deno_status_label.setText("Статус: установлен")
            self.deno_status_label.setStyleSheet("color: green;")
        else:
            self.deno_status_label.setText("Статус: ошибка установки")
            self.deno_status_label.setStyleSheet("color: red;")
    
    def update_ytdlp_from_settings(self):
        self.ytdlp_status_label.setText("Статус: установка/обновление...")
        self.ytdlp_status_label.setStyleSheet("color: orange;")
        
        def log_callback(msg):
            self.ytdlp_status_label.setText(f"Статус: {msg}")
            QApplication.processEvents()
        
        success, msg = install_or_update_yt_dlp(callback=log_callback)
        if success:
            version = get_installed_version()
            self.ytdlp_status_label.setText(f"Статус: установлен (версия {version})")
            self.ytdlp_status_label.setStyleSheet("color: green;")
            QMessageBox.information(self, "Успех", f"yt-dlp успешно установлен/обновлен!\nВерсия: {version}")
        else:
            self.ytdlp_status_label.setText(f"Статус: ошибка - {msg}")
            self.ytdlp_status_label.setStyleSheet("color: red;")
            QMessageBox.warning(self, "Ошибка", f"Не удалось установить yt-dlp:\n{msg}")