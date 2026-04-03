from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, QLineEdit, QPushButton, QMessageBox, QApplication, QFileDialog, QComboBox
from PySide6.QtCore import QTimer
import os
import sys
import json
import requests
import tempfile
import shutil
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

        # Настройки тестов сжатия
        test_group = QGroupBox("Настройки тестов сжатия (Chunk Test & VMAF)")
        test_layout = QVBoxLayout()
        
        vmaf_layout = QHBoxLayout()
        vmaf_layout.addWidget(QLabel("Пропуск кадров VMAF:"))
        self.vmaf_combo = QComboBox()
        self.vmaf_combo.addItem("Каждый кадр (очень медленно)", 1)
        self.vmaf_combo.addItem("Каждый 2-й кадр", 2)
        self.vmaf_combo.addItem("Каждый 5-й кадр (по умолчанию)", 5)
        self.vmaf_combo.addItem("Каждый 10-й кадр (быстро)", 10)
        self.vmaf_combo.addItem("Каждый 24-й кадр (очень быстро)", 24)
        vmaf_layout.addWidget(self.vmaf_combo)
        vmaf_layout.addStretch()
        
        chunk_layout = QHBoxLayout()
        chunk_layout.addWidget(QLabel("Точность Chunk Test:"))
        self.chunk_combo = QComboBox()
        self.chunk_combo.addItem("Быстрый (2 отрывка по 5 сек)", (2, 5))
        self.chunk_combo.addItem("Стандартный (3 отрывка по 10 сек) [По умолчанию]", (3, 10))
        self.chunk_combo.addItem("Точный (4 отрывка по 15 сек)", (4, 15))
        self.chunk_combo.addItem("Максимальный (5 отрывков по 20 сек)", (5, 20))
        chunk_layout.addWidget(self.chunk_combo)
        chunk_layout.addStretch()
        
        test_layout.addLayout(vmaf_layout)
        test_layout.addLayout(chunk_layout)
        test_group.setLayout(test_layout)
        layout.addWidget(test_group)

        # Program Update Group
        update_group = QGroupBox("Обновление программы")
        update_layout = QVBoxLayout()
        version_layout = QHBoxLayout()
        version_layout.addWidget(QLabel("Текущая версия:"))
        self.version_label = QLabel("Не определено")
        version_layout.addWidget(self.version_label)
        version_layout.addStretch()
        update_layout.addLayout(version_layout)
        self.update_status_label = QLabel("Статус: не проверялось")
        self.update_status_label.setStyleSheet("color: gray;")
        update_layout.addWidget(self.update_status_label)
        self.update_btn = QPushButton("Проверить обновления")
        self.update_btn.clicked.connect(self.check_for_updates)
        update_layout.addWidget(self.update_btn)
        update_group.setLayout(update_layout)
        layout.addWidget(update_group)

        layout.addStretch()
        save_btn = QPushButton("Сохранить настройки")
        save_btn.clicked.connect(self.save_settings_from_tab)
        layout.addWidget(save_btn)

        self.update_version_label()

    def load_settings_to_tab(self):
        settings = load_settings()
        self.ffmpeg_path_input.setText(settings.get("ffmpeg_path", "./"))
        self.ytdlp_path_input.setText(settings.get("yt_dlp_path", "./yt_dlp"))
        
        vmaf_val = settings.get("vmaf_subsample", 5)
        index = self.vmaf_combo.findData(vmaf_val)
        if index >= 0: self.vmaf_combo.setCurrentIndex(index)
        
        c_count = settings.get("chunk_count", 3)
        c_dur = settings.get("chunk_duration", 10)
        index = self.chunk_combo.findData((c_count, c_dur))
        if index >= 0: self.chunk_combo.setCurrentIndex(index)
        
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
        
        settings["vmaf_subsample"] = self.vmaf_combo.currentData()
        chunk_data = self.chunk_combo.currentData()
        settings["chunk_count"] = chunk_data[0]
        settings["chunk_duration"] = chunk_data[1]
        
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

    def update_version_label(self):
        try:
            if getattr(sys, 'frozen', False):
                path = sys.executable
            else:
                path = __file__
            timestamp = os.path.getmtime(path)
            from datetime import datetime
            dt = datetime.fromtimestamp(timestamp)
            version_str = dt.strftime("%y.%m.%d %H:%M")
            self.version_label.setText(version_str)
        except Exception as e:
            self.version_label.setText("Ошибка")

    def check_for_updates(self):
        self.update_btn.setEnabled(False)
        self.update_status_label.setText("Статус: проверка обновлений...")
        self.update_status_label.setStyleSheet("color: orange;")
        QApplication.processEvents()

        try:
            api_url = "https://api.github.com/repos/Sankyuubigan/videofiles_processing/releases/latest"
            response = requests.get(api_url, timeout=10)
            response.raise_for_status()
            release_data = response.json()

            published_at = release_data.get("published_at")
            if not published_at:
                raise ValueError("No publish date in release")
            from datetime import datetime
            release_dt = datetime.strptime(published_at, "%Y-%m-%dT%H:%M:%SZ")
            release_str = release_dt.strftime("%y.%m.%d %H:%M")

            current_str = self.version_label.text()
            if current_str == "Не определено" or current_str == "Ошибка":
                self.update_status_label.setText("Статус: не удалось определить текущую версию")
                self.update_status_label.setStyleSheet("color: red;")
                self.update_btn.setEnabled(True)
                return

            if release_str > current_str:
                self.update_status_label.setText(f"Доступно обновление: {release_str}")
                self.update_status_label.setStyleSheet("color: green;")
                assets = release_data.get("assets", [])
                exe_asset = None
                for asset in assets:
                    name = asset.get("name", "")
                    if name.lower().endswith(".exe") and "videocompressor" in name.lower():
                        exe_asset = asset
                        break
                if not exe_asset:
                    for asset in assets:
                        if asset.get("name", "").lower().endswith(".exe"):
                            exe_asset = asset
                            break
                if exe_asset:
                    download_url = exe_asset["browser_download_url"]
                    asset_name = exe_asset["name"]
                    self.update_status_label.setText(f"Статус: загрузка обновления...")
                    self.update_status_label.setStyleSheet("color: orange;")
                    QApplication.processEvents()
                    resp = requests.get(download_url, stream=True, timeout=30)
                    resp.raise_for_status()
                    if getattr(sys, 'frozen', False):
                        current_exe = sys.executable
                    else:
                        current_exe = os.path.abspath(sys.argv[0])
                    temp_dir = os.path.dirname(current_exe)
                    temp_path = os.path.join(temp_dir, f"update_{asset_name}")
                    with open(temp_path, "wb") as f:
                        for chunk in resp.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                    self.update_status_label.setText(f"Обновление загружено: {asset_name}\nЗамените текущий файл и перезапустите программу.")
                    self.update_status_label.setStyleSheet("color: green;")
                    QMessageBox.information(self, "Обновление загружено",
                                            f"Новая версия загружена как:\n{temp_path}\n\n"
                                            "Пожалуйста, закройте программу, замените текущий исполняемый файл на этот файл и запустите программу снова.")
                else:
                    self.update_status_label.setText("Статус: не найден exe-файл в релизе")
                    self.update_status_label.setStyleSheet("color: red;")
            else:
                self.update_status_label.setText(f"Статус: у вас последняя версия ({current_str})")
                self.update_status_label.setStyleSheet("color: green;")
        except Exception as e:
            self.update_status_label.setText(f"Статус: ошибка - {str(e)}")
            self.update_status_label.setStyleSheet("color: red;")
        finally:
            self.update_btn.setEnabled(True)