import sys
import os
import logging
import json
from datetime import datetime
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                               QHBoxLayout, QPushButton, QLabel, QFileDialog,
                               QProgressBar, QTextEdit, QGroupBox,
                               QMessageBox, QComboBox, QCheckBox, QSlider,
                               QRadioButton, QButtonGroup,
                               QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
                               QTabWidget, QToolButton, QSpinBox, QLineEdit, QFrame)
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QUrl
from PySide6.QtGui import QFont, QDragEnterEvent, QDropEvent
from config import (OUTPUT_FORMATS, CODECS, DEFAULT_OUTPUT_FORMAT_KEY, DEFAULT_CODEC_KEY,
                    DEFAULT_USE_HARDWARE_ENCODING, TRIMMED_VIDEO_SUFFIX)
from video_processor import VideoProcessor
from ffmpeg_downloader import FFmpegDownloader
from dialogs import VideoInfoDialog
from threads import WorkerThread
from gui_logger import setup_logging
from settings_manager import load_settings, save_settings, get_actual_ffmpeg_path, get_ffprobe_path, get_yt_dlp_path, get_cookies_path
from yt_dlp_manager import (is_yt_dlp_installed, get_installed_version, 
                           install_or_update_yt_dlp, ensure_yt_dlp_installed,
                           add_yt_dlp_to_path, get_yt_dlp_bin_dir,
                           ensure_deno_installed, is_deno_installed, get_deno_path)


class MainWindow(QMainWindow):
    # Signal to be used by the logging handler
    log_signal = Signal(str)

    def __init__(self):
        super().__init__()
        self.processor = VideoProcessor()
        self.file_queue =[]  # Список кортежей (путь, информация_о_файле)
        self.current_file = None
        self.current_info = None
        self.compression_worker = None
        self.active_workers =[]
        self._cached_info = None
        self.processing_stopped = False  # Флаг для остановки всей очереди
        
        # Переменные для отслеживания общего прогресса
        self.batch_in_progress = False
        self.total_files_in_batch = 0
        self.completed_files_in_batch = 0
        
        # Путь для сохранения файлов
        self.output_directory = None
        
        # Переменная для отслеживания времени начала сжатия
        self.compression_start_time = None
        
        # Setup logging
        setup_logging(self.log_slot)
        
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Video Compressor")
        self.setGeometry(100, 100, 1200, 750)
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Создаем вкладки
        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)
        
        # Первая вкладка - Основная
        self.main_tab = QWidget()
        self.tab_widget.addTab(self.main_tab, "Редактор")
        main_tab_layout = QVBoxLayout(self.main_tab)
        
        # Вторая вкладка - Логи
        self.log_tab = QWidget()
        self.tab_widget.addTab(self.log_tab, "Логи")
        log_tab_layout = QVBoxLayout(self.log_tab)
        
        # Создаем текстовое поле для логов на второй вкладке
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        log_tab_layout.addWidget(self.log_text)

        # Третья вкладка - Настройки
        self.settings_tab = QWidget()
        self.tab_widget.addTab(self.settings_tab, "Настройки")
        self.create_settings_tab()

        # Четвертая вкладка - Скачать видео
        self.download_tab = QWidget()
        self.tab_widget.addTab(self.download_tab, "Скачать видео")
        self.create_download_tab()

        file_group = self.create_file_group()
        main_tab_layout.addWidget(file_group)

        # Группа с таблицей очереди
        queue_group = QGroupBox("Очередь файлов")
        queue_layout = QVBoxLayout()
        
        # Создаем таблицу для очереди файлов
        self.queue_table = QTableWidget()
        self.queue_table.setColumnCount(8)
        self.queue_table.setHorizontalHeaderLabels([
            "Имя файла", "Размер", "Длительность", "Статус VFR", 
            "Сложность", "Примерный размер", "Время сжатия", "Действия"
        ])
        self.queue_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for i in range(1, 8):
            self.queue_table.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeToContents)
        self.queue_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.queue_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.queue_table.setAlternatingRowColors(True)
        
        queue_layout.addWidget(self.queue_table)
        queue_group.setLayout(queue_layout)
        main_tab_layout.addWidget(queue_group)

        # Вкладки операций (Сжатие, Сокращение, Починка громкости)
        self.operations_tabs = QTabWidget()
        
        self.compression_tab = self.create_compression_tab()
        self.operations_tabs.addTab(self.compression_tab, "Сжатие видео")
        
        self.trim_tab = self.create_trim_tab()
        self.operations_tabs.addTab(self.trim_tab, "Сокращение")
        
        self.normalize_tab = self.create_normalize_tab()
        self.operations_tabs.addTab(self.normalize_tab, "Починка громкости")
        
        main_tab_layout.addWidget(self.operations_tabs)

        process_group = self.create_process_group()
        main_tab_layout.addWidget(process_group)

        self.on_format_changed()
        self.setAcceptDrops(True)

    def create_file_group(self):
        file_group = QGroupBox("1. Выбор видеофайла")
        file_layout = QVBoxLayout()
        file_select_layout = QHBoxLayout()
        self.file_label = QLabel("Перетащите файлы сюда или нажмите 'Выбрать'")
        self.file_label.setWordWrap(True)
        self.select_file_btn = QPushButton("Выбрать файл(ы)")
        self.select_file_btn.clicked.connect(self.select_files)
        
        self.output_dir_btn = QPushButton("Путь сохранения")
        self.output_dir_btn.clicked.connect(self.select_output_directory)
        self.output_dir_btn.setToolTip("Выбрать папку для сохранения сжатых файлов")
        self.output_dir_label = QLabel("Сохранять в папке с оригиналами")
        self.output_dir_label.setStyleSheet("color: gray; font-size: 10px;")
        
        file_select_layout.addWidget(self.select_file_btn)
        file_select_layout.addWidget(self.output_dir_btn)
        file_select_layout.addStretch()
        file_layout.addLayout(file_select_layout)
        
        output_path_layout = QHBoxLayout()
        output_path_layout.addWidget(QLabel("Путь сохранения:"))
        output_path_layout.addWidget(self.output_dir_label)
        output_path_layout.addStretch()
        file_layout.addLayout(output_path_layout)
        
        file_layout.addWidget(self.file_label)
        self.queue_label = QLabel("В очереди: 0 файлов")
        file_layout.addWidget(self.queue_label)
        file_group.setLayout(file_layout)
        return file_group

    def create_compression_tab(self):
        tab = QWidget()
        settings_layout = QVBoxLayout(tab)
        
        format_layout = QHBoxLayout()
        format_layout.addWidget(QLabel("Формат:"))
        self.format_combo = QComboBox()
        for ext, details in OUTPUT_FORMATS.items():
            self.format_combo.addItem(f".{ext.upper()}", ext)
        self.format_combo.setCurrentText(f".{DEFAULT_OUTPUT_FORMAT_KEY.upper()}")
        self.format_combo.currentTextChanged.connect(self.on_format_changed)
        format_layout.addWidget(self.format_combo)
        format_layout.addStretch()
        
        codec_layout = QHBoxLayout()
        codec_layout.addWidget(QLabel("Кодек:"))
        self.codec_combo = QComboBox()
        self.update_codec_options()
        self.codec_combo.currentTextChanged.connect(self.on_codec_changed)
        codec_layout.addWidget(self.codec_combo)
        codec_layout.addStretch()
        
        encoding_layout = QHBoxLayout()
        encoding_layout.addWidget(QLabel("Тип кодирования:"))
        self.encoding_group = QButtonGroup(self)
        self.hardware_radio = QRadioButton("Аппаратное (NVENC)")
        self.software_radio = QRadioButton("Программное (CPU)")
        self.encoding_group.addButton(self.hardware_radio)
        self.encoding_group.addButton(self.software_radio)
        if DEFAULT_USE_HARDWARE_ENCODING:
            self.hardware_radio.setChecked(True)
        else:
            self.software_radio.setChecked(True)
        self.hardware_radio.toggled.connect(self.on_encoding_changed)
        encoding_layout.addWidget(self.hardware_radio)
        encoding_layout.addWidget(self.software_radio)
        encoding_layout.addStretch()
        
        preset_layout = QHBoxLayout()
        preset_layout.addWidget(QLabel("Пресет:"))
        self.preset_combo = QComboBox()
        self.update_preset_options()
        self.preset_combo.currentTextChanged.connect(self.on_preset_changed)
        preset_layout.addWidget(self.preset_combo)
        preset_layout.addStretch()
        
        crf_layout = QHBoxLayout()
        self.crf_label = QLabel("CRF: ")
        self.crf_slider = QSlider(Qt.Horizontal)
        self.crf_slider.valueChanged.connect(self.on_crf_changed)
        crf_layout.addWidget(self.crf_label)
        crf_layout.addWidget(self.crf_slider)
        
        vfr_layout = QHBoxLayout()
        self.vfr_checkbox = QCheckBox("Принудительная починка VFR")
        self.vfr_status_label = QLabel("Статус VFR: Не определено")
        vfr_layout.addWidget(self.vfr_status_label)
        vfr_layout.addWidget(self.vfr_checkbox)
        vfr_layout.addStretch()
        
        settings_layout.addLayout(format_layout)
        settings_layout.addLayout(codec_layout)
        settings_layout.addLayout(encoding_layout)
        settings_layout.addLayout(preset_layout)
        settings_layout.addLayout(crf_layout)
        settings_layout.addLayout(vfr_layout)
        
        return tab

    def create_trim_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        seconds_layout = QHBoxLayout()
        seconds_layout.addWidget(QLabel("Количество секунд для удаления:"))
        self.trim_seconds_spin = QSpinBox()
        self.trim_seconds_spin.setRange(1, 3600)
        self.trim_seconds_spin.setValue(10)
        self.trim_seconds_spin.setSuffix(" сек")
        seconds_layout.addWidget(self.trim_seconds_spin)
        seconds_layout.addStretch()
        
        position_layout = QHBoxLayout()
        position_layout.addWidget(QLabel("Удалять с:"))
        self.trim_position_group = QButtonGroup(self)
        self.trim_from_end_radio = QRadioButton("Конца")
        self.trim_from_start_radio = QRadioButton("Начала")
        self.trim_position_group.addButton(self.trim_from_end_radio)
        self.trim_position_group.addButton(self.trim_from_start_radio)
        self.trim_from_end_radio.setChecked(True)
        
        position_layout.addWidget(self.trim_from_end_radio)
        position_layout.addWidget(self.trim_from_start_radio)
        position_layout.addStretch()
        
        info_label = QLabel("Примечание: Видео будет сохранено с суффиксом '_trimmed'.")
        info_label.setStyleSheet("color: gray; font-style: italic;")
        
        layout.addLayout(seconds_layout)
        layout.addLayout(position_layout)
        layout.addWidget(info_label)
        layout.addStretch()
        
        return tab

    def create_normalize_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        info_label = QLabel("Нормализует громкость аудио в два этапа:\n"
                            "1. Динамическая нормализация (dynaudnorm)\n"
                            "2. Нормализация громкости по стандарту (loudnorm)")
        info_label.setStyleSheet("color: gray;")
        
        output_label = QLabel("Видео будет сохранено с суффиксом '_volnorm'.")
        output_label.setStyleSheet("font-weight: bold;")
        
        layout.addWidget(info_label)
        layout.addWidget(output_label)
        layout.addStretch()
        
        return tab

    def create_process_group(self):
        process_group = QGroupBox("Запуск обработки")
        process_layout = QVBoxLayout()
        
        buttons_layout = QHBoxLayout()
        self.process_btn = QPushButton("Начать обработку")
        self.process_btn.clicked.connect(self.start_processing)
        self.process_btn.setEnabled(False)
        
        self.cancel_btn = QPushButton("Отменить")
        self.cancel_btn.clicked.connect(self.cancel_processing)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setVisible(False)
        
        buttons_layout.addWidget(self.process_btn)
        buttons_layout.addWidget(self.cancel_btn)
        buttons_layout.addStretch()
        
        process_layout.addLayout(buttons_layout)
        
        self.progress_bar = QProgressBar()
        self.status_label = QLabel("Готов к работе")
        process_layout.addWidget(self.progress_bar)
        process_layout.addWidget(self.status_label)
        process_group.setLayout(process_layout)
        return process_group

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        for url in urls:
            if url.isLocalFile():
                self.add_file_to_queue(url.toLocalFile())
        self.update_queue_label()

    def select_output_directory(self):
        directory = QFileDialog.getExistingDirectory(
            self, "Выберите папку для сохранения сжатых файлов",
            "" if not self.output_directory else self.output_directory
        )
        
        if directory:
            self.output_directory = directory
            self.output_dir_label.setText(directory)
            self.output_dir_label.setStyleSheet("color: green; font-size: 10px;")
            logging.info(f"Выбрана папка для сохранения: {directory}")
        else:
            self.output_directory = None
            self.output_dir_label.setText("Сохранять в папке с оригиналами")
            self.output_dir_label.setStyleSheet("color: gray; font-size: 10px;")

    def add_file_to_queue(self, file_path):
        if os.path.isfile(file_path):
            info = self.processor.get_video_info(file_path)
            if "error" not in info:
                info["is_video"] = info.get("width", 0) > 0 and info.get("height", 0) > 0
                
                complexity_score = info.get('complexity_score', 0)
                complexity_desc = info.get('complexity_desc', 'Не определено')
                logging.info(f"--- Анализ файла: {os.path.basename(file_path)} ---")
                logging.info(f"Сложность: {complexity_desc} ({complexity_score}/10)")
                if not info["is_video"]:
                    logging.info(f"Тип файла: Аудио")
                else:
                    logging.info(f"Тип файла: Видео")
                logging.info("------------------------------------")
                
                self.file_queue.append((file_path, info))
                self.update_queue_table()
                self.update_queue_label()
                logging.info(f"Файл добавлен в очередь: {file_path}")
                
                if len(self.file_queue) == 1 and self.current_file is None:
                    self.current_file, self.current_info = self.file_queue.pop(0)
                    self.set_current_file(self.current_file, self.current_info)
                    self.set_ui_enabled(True)

    def update_queue_table(self):
        all_files =[]
        if self.current_file:
            all_files.append((self.current_file, self.current_info))
        all_files.extend(self.file_queue)

        self.queue_table.setRowCount(len(all_files))
        
        crf_value = self.crf_slider.value()
        codec = self.current_codec()
        use_hardware = self.hardware_radio.isChecked()
        force_vfr_fix = self.vfr_checkbox.isChecked()
        preset = self.current_preset()
        
        for row, (file_path, info) in enumerate(all_files):
            file_name_item = QTableWidgetItem(os.path.basename(file_path))
            self.queue_table.setItem(row, 0, file_name_item)
            
            size_mb = info.get("size_mb", 0)
            size_item = QTableWidgetItem(f"{size_mb:.1f} МБ")
            self.queue_table.setItem(row, 1, size_item)
            
            duration = info.get("duration", 0)
            duration_formatted = self.processor.size_estimator.format_duration(duration)
            duration_item = QTableWidgetItem(duration_formatted)
            self.queue_table.setItem(row, 2, duration_item)
            
            needs_vfr = info.get("needs_vfr_fix", False)
            vfr_text = "Требуется" if needs_vfr else "Не требуется"
            vfr_item = QTableWidgetItem(vfr_text)
            if needs_vfr:
                vfr_item.setForeground(Qt.GlobalColor.red)
            else:
                vfr_item.setForeground(Qt.GlobalColor.darkGreen)
            self.queue_table.setItem(row, 3, vfr_item)
            
            complexity_desc = info.get('complexity_desc', 'Не определено')
            complexity_item = QTableWidgetItem(complexity_desc)
            self.queue_table.setItem(row, 4, complexity_item)
            
            complexity_score = info.get('complexity_score', 5)
            est_size = self.processor.estimated_size_mb(
                video_bitrate=info.get("video_bitrate", 0),
                audio_bitrate=info.get("audio_bitrate", 128000),
                duration=info["duration"],
                crf=crf_value,
                codec=codec,
                needs_vfr_fix=needs_vfr or force_vfr_fix,
                use_hardware=use_hardware,
                preset=preset,
                complexity_score=complexity_score,
                width=info.get("width", 1920),
                height=info.get("height", 1080)
            )
            est_item = QTableWidgetItem(f"{est_size:.1f} МБ")
            self.queue_table.setItem(row, 5, est_item)
            
            compression_time = self.processor.size_estimator.estimate_compression_time(
                duration=info["duration"],
                width=info.get("width", 1920),
                height=info.get("height", 1080),
                preset=preset,
                codec=codec,
                use_hardware=use_hardware
            )
            time_formatted = self.processor.size_estimator.format_duration(compression_time)
            time_item = QTableWidgetItem(time_formatted)
            self.queue_table.setItem(row, 6, time_item)
            
            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(2, 2, 2, 2)
            actions_layout.setSpacing(2)
            
            info_btn = QToolButton()
            info_btn.setText("ℹ")
            info_btn.setToolTip("Информация о файле")
            info_btn.setProperty("video_info", info)
            info_btn.clicked.connect(self.on_info_button_clicked)
            info_btn.setFixedSize(24, 24)
            
            delete_btn = QToolButton()
            delete_btn.setText("✕")
            delete_btn.setToolTip("Удалить из очереди")
            delete_btn.setProperty("file_path", file_path)
            delete_btn.clicked.connect(self.on_delete_button_clicked)
            delete_btn.setFixedSize(24, 24)
            
            actions_layout.addWidget(info_btn)
            actions_layout.addWidget(delete_btn)
            actions_layout.addStretch()
            
            self.queue_table.setCellWidget(row, 7, actions_widget)
        
        self.queue_table.viewport().update()

    def on_info_button_clicked(self):
        button = self.sender()
        if button:
            info = button.property("video_info")
            if info:
                self.show_info_dialog(info)

    def on_delete_button_clicked(self):
        button = self.sender()
        if button:
            file_path_to_delete = button.property("file_path")
            if file_path_to_delete:
                self.remove_from_queue(file_path_to_delete)

    def remove_from_queue(self, file_path_to_delete):
        file_removed = False
        
        if self.current_file == file_path_to_delete:
            logging.info(f"Текущий файл {os.path.basename(file_path_to_delete)} удален.")
            self.current_file = None
            self.current_info = None
            self._cached_info = None
            file_removed = True
            
            if self.file_queue:
                self.current_file, self.current_info = self.file_queue.pop(0)
                self.set_current_file(self.current_file, self.current_info)
            else:
                self.set_ui_enabled(True) 
                self.file_label.setText("Перетащите файлы сюда или нажмите 'Выбрать'")
                self.process_btn.setEnabled(False)
                self.vfr_status_label.setText("Статус VFR: Не определено")
                self.vfr_status_label.setStyleSheet("color: gray;")
        else:
            try:
                index = next(i for i, (path, _) in enumerate(self.file_queue) if path == file_path_to_delete)
                self.file_queue.pop(index)
                logging.info(f"Файл удален из очереди: {os.path.basename(file_path_to_delete)}")
                file_removed = True
            except StopIteration:
                logging.error(f"Не удалось найти файл для удаления: {file_path_to_delete}")

        if file_removed:
            self.update_queue_table()
            self.update_queue_label()

    def process_first_in_queue(self):
        if self.file_queue and self.current_file is None:
            self.current_file, self.current_info = self.file_queue.pop(0)
            self.update_queue_table()
            self.set_current_file(self.current_file, self.current_info)

    def update_queue_label(self):
        self.queue_label.setText(f"В очереди: {len(self.file_queue)} файлов")

    def select_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Выберите видеофайлы", "",
            "Video files (*.mp4 *.avi *.mkv *.mov *.webm)"
        )
        if files:
            for file in files:
                self.add_file_to_queue(file)

    def set_current_file(self, file_path, file_info):
        self.file_label.setText(f"Текущий файл: {os.path.basename(file_path)}")
        self.process_btn.setEnabled(True)
        self._cached_info = file_info
        self.check_vfr_status()
        
        is_video = file_info.get("is_video", True)
        compression_tab_index = 0
        self.operations_tabs.setTabEnabled(compression_tab_index, is_video)

    def current_codec(self):
        return self.codec_combo.currentData()

    def current_preset(self):
        return self.preset_combo.currentData()

    def update_codec_options(self):
        self.codec_combo.clear()
        current_format = self.format_combo.currentData()
        compatible_codecs = OUTPUT_FORMATS[current_format]["compatible_codecs"]
        
        for codec_key in compatible_codecs:
            codec_name = CODECS[codec_key]["name"]
            self.codec_combo.addItem(codec_name, codec_key)
        
        default_codec = OUTPUT_FORMATS[current_format]["default_codec"]
        index = self.codec_combo.findData(default_codec)
        if index >= 0:
            self.codec_combo.setCurrentIndex(index)

    def update_preset_options(self):
        self.preset_combo.clear()
        codec_key = self.codec_combo.currentData()
        
        if codec_key is None:
            return
            
        presets = CODECS[codec_key]["presets"]
        default_preset = CODECS[codec_key]["preset_default"]
        
        for preset in presets:
            self.preset_combo.addItem(preset, preset)
        
        index = self.preset_combo.findData(default_preset)
        if index >= 0:
            self.preset_combo.setCurrentIndex(index)

    def on_format_changed(self):
        self.update_codec_options()
        self.update_preset_options()
        
        codec_key = self.codec_combo.currentData()
        if codec_key is None:
            return
            
        codec_details = CODECS.get(codec_key, CODECS[DEFAULT_CODEC_KEY])
        self.crf_slider.setRange(codec_details["crf_min"], codec_details["crf_max"])
        self.crf_slider.setValue(codec_details["crf_default"])
        self.on_crf_changed(codec_details["crf_default"])
        self.update_queue_table()

    def on_codec_changed(self):
        codec_key = self.codec_combo.currentData()
        if codec_key is None:
            return
            
        self.update_preset_options()
        
        codec_details = CODECS.get(codec_key, CODECS[DEFAULT_CODEC_KEY])
        self.crf_slider.setRange(codec_details["crf_min"], codec_details["crf_max"])
        self.crf_slider.setValue(codec_details["crf_default"])
        self.on_crf_changed(codec_details["crf_default"])
        self.update_queue_table()

    def on_preset_changed(self):
        self.update_queue_table()

    def on_encoding_changed(self):
        self.update_queue_table()

    def on_crf_changed(self, value):
        if value == self.crf_slider.minimum():
            self.crf_label.setText("CRF: только VFR-fix (copy)")
        else:
            self.crf_label.setText(f"CRF: {value}")
        self.update_queue_table()

    def check_vfr_status(self):
        if self.current_file:
            needs_fix = self._cached_info.get('needs_vfr_fix', False) if self._cached_info else False
            if needs_fix:
                self.vfr_status_label.setText("Статус VFR: Рекомендуется!")
                self.vfr_status_label.setStyleSheet("color: orange;")
            else:
                self.vfr_status_label.setText("Статус VFR: Не требуется")
                self.vfr_status_label.setStyleSheet("color: green;")

    def show_info_dialog(self, info):
        dialog = VideoInfoDialog(info, self)
        dialog.exec()

    def start_processing(self):
        if not self.current_file:
            logging.warning("Предупреждение: Сначала выберите файл")
            return
        
        if not self.batch_in_progress:
            self.batch_in_progress = True
            self.total_files_in_batch = len(self.file_queue) + (1 if self.current_file else 0)
            self.completed_files_in_batch = 0
            logging.info(f"Начало обработки пакета из {self.total_files_in_batch} файла(ов).")
        
        self.processing_stopped = False
        self.compression_start_time = datetime.now()
        
        current_tab_index = self.operations_tabs.currentIndex()
        current_tab_text = self.operations_tabs.tabText(current_tab_index)
        
        is_video = self._cached_info.get("is_video", True) if self._cached_info else True
        if current_tab_text == "Сжатие видео" and not is_video:
            QMessageBox.warning(self, "Ошибка", "Сжатие видео недоступно для аудиофайлов!")
            return
        
        params = {"input_path": self.current_file, "output_dir": self.output_directory}
        worker_mode = ""

        if current_tab_text == "Сжатие видео":
            worker_mode = "compress"
            params.update({
                "output_format": self.format_combo.currentData(),
                "codec": self.codec_combo.currentData(),
                "crf_value": self.crf_slider.value(),
                "preset_value": self.preset_combo.currentData(),
                "force_vfr_fix": self.vfr_checkbox.isChecked(),
                "use_hardware": self.hardware_radio.isChecked(),
            })
            logging.info(f"Начало сжатия файла: {os.path.basename(self.current_file)}")
            
        elif current_tab_text == "Сокращение":
            worker_mode = "trim"
            params.update({
                "seconds": self.trim_seconds_spin.value(),
                "from_start": self.trim_from_start_radio.isChecked()
            })
            logging.info(f"Начало сокращения файла: {os.path.basename(self.current_file)}")

        elif current_tab_text == "Починка громкости":
            worker_mode = "normalize_audio"
            logging.info(f"Начало нормализации громкости файла: {os.path.basename(self.current_file)}")

        self.set_ui_enabled(False)
        self.run_processing_worker(worker_mode, **params)

    def cancel_processing(self):
        reply = QMessageBox.question(
            self, "Подтверждение отмены",
            "Вы уверены, что хотите отменить процесс и всю очередь?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.processing_stopped = True
            if self.compression_worker:
                logging.info("Отмена процесса и всей очереди...")
                self.status_label.setText("Отмена процесса...")
                self.compression_worker.stop()
                QTimer.singleShot(1000, self.on_canceled)

    def on_canceled(self):
        logging.info("Процесс обработки очереди отменен пользователем")
        self.status_label.setText("Отменено пользователем")
        self.progress_bar.setValue(0)
        
        self.batch_in_progress = False
        self.total_files_in_batch = 0
        self.completed_files_in_batch = 0
        
        self.current_file = None
        self.current_info = None
        self.set_ui_enabled(True)
        self.file_label.setText("Перетащите файлы сюда или нажмите 'Выбрать'")
        self.status_label.setText("Готов к работе")
        self.progress_bar.setValue(0)

    def run_processing_worker(self, mode, **kwargs):
        self.compression_worker = WorkerThread(self.processor, mode, **kwargs)
        self.compression_worker.progress_updated.connect(self.update_progress)
        self.compression_worker.finished.connect(self.on_finished)
        self.compression_worker.error_occurred.connect(self.on_error)
        self.compression_worker.finished.connect(self.on_compression_worker_finished)
        self.active_workers.append(self.compression_worker)
        self.compression_worker.start()

    def run_info_worker(self, input_path, callback_slot):
        worker = WorkerThread(self.processor, 'info', input_path=input_path)
        worker.info_ready.connect(callback_slot)
        worker.error_occurred.connect(self.on_error)
        worker.finished.connect(lambda: self.on_worker_finished(worker))
        self.active_workers.append(worker)
        worker.start()

    def on_worker_finished(self, worker):
        if worker in self.active_workers:
            self.active_workers.remove(worker)
        worker.deleteLater()

    def on_compression_worker_finished(self):
        worker = self.sender()
        self.on_worker_finished(worker)
        self.compression_worker = None

    def update_progress(self, value, message):
        if self.batch_in_progress and self.total_files_in_batch > 0:
            current_file_progress = value / 100.0
            total_progress_float = (self.completed_files_in_batch + current_file_progress) / self.total_files_in_batch
            total_progress_percent = int(total_progress_float * 100)
            
            self.progress_bar.setValue(total_progress_percent)
            
            current_file_name = os.path.basename(self.current_file) if self.current_file else "неизвестный файл"
            self.status_label.setText(f"Обработка: {current_file_name} ({value}%) | Общий прогресс: {total_progress_percent}%")
        else:
            self.progress_bar.setValue(value)
            self.status_label.setText(message)

    def _handle_file_completion(self):
        if self.batch_in_progress:
            self.completed_files_in_batch += 1
            logging.info(f"Файл обработан. Прогресс по пакету: {self.completed_files_in_batch}/{self.total_files_in_batch}")

    def on_finished(self, result):
        if self.compression_start_time:
            compression_time = datetime.now() - self.compression_start_time
            compression_time_str = str(compression_time).split('.')[0]
            logging.info(f"Обработка файла завершена. Затрачено времени: {compression_time_str}")
            self.compression_start_time = None

        logging.info(f"Готово: {result}")
        self._handle_file_completion()
        
        if not self.processing_stopped:
            self.process_next_file()
        else:
            self.on_canceled()

    def on_error(self, error):
        if self.compression_start_time:
            compression_time = datetime.now() - self.compression_start_time
            compression_time_str = str(compression_time).split('.')[0]
            logging.info(f"Обработка файла прервана ошибкой. Затрачено времени: {compression_time_str}")
            self.compression_start_time = None

        logging.error(f"ОШИБКА: {error}")
        self.status_label.setText("Ошибка при обработке!")
        if self.sender() == self.compression_worker:
            self.compression_worker = None
        self._handle_file_completion()

        if not self.processing_stopped:
            self.process_next_file()
        else:
            self.on_canceled()

    def process_next_file(self):
        if self.processing_stopped:
            self.on_canceled()
            return
            
        if self.current_file:
            if self.file_queue:
                self.current_file, self.current_info = self.file_queue.pop(0)
                self.set_current_file(self.current_file, self.current_info)
                QTimer.singleShot(500, self.start_processing)
            else:
                self.current_file = None
                self.current_info = None
        
        self.update_queue_table()
        self.update_queue_label()
        
        if not self.current_file:
            if self.batch_in_progress:
                logging.info("Обработка пакета завершена.")
                self.batch_in_progress = False
                self.total_files_in_batch = 0
                self.completed_files_in_batch = 0

            self.set_ui_enabled(True)
            self.file_label.setText("Перетащите файлы сюда или нажмите 'Выбрать'")
            self.status_label.setText("Готов к работе")
            self.progress_bar.setValue(0)

    def set_ui_enabled(self, enabled):
        self.select_file_btn.setEnabled(enabled)
        self.process_btn.setEnabled(enabled and self.current_file is not None)
        self.cancel_btn.setEnabled(not enabled and self.current_file is not None)
        self.cancel_btn.setVisible(not enabled and self.current_file is not None)
        self.operations_tabs.setEnabled(enabled)
        self.output_dir_btn.setEnabled(enabled)

    def log_slot(self, message):
        if hasattr(self, 'log_text'):
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.log_text.append(f"[{timestamp}] {message}")

    def closeEvent(self, event):
        if self.compression_worker and self.compression_worker.isRunning():
            reply = QMessageBox.question(self, "Выход",
                                         "Процесс обработки еще не завершен. Вы уверены, что хотите выйти?",
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                if self.compression_worker:
                    self.compression_worker.stop()
                self.compression_worker.quit()
                self.compression_worker.wait(5000)
                event.accept()
            else:
                event.ignore()
        else:
            for worker in self.active_workers:
                worker.quit()
                worker.wait(1000)
            event.accept()

    def create_settings_tab(self):
        layout = QVBoxLayout(self.settings_tab)
        
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
        
        self.load_settings_to_tab()
    
    def load_settings_to_tab(self):
        settings = load_settings()
        self.ffmpeg_path_input.setText(settings.get("ffmpeg_path", "./"))
        self.ytdlp_path_input.setText(settings.get("yt_dlp_path", "./yt_dlp"))
        self.check_ffmpeg_status()
        self.check_ytdlp_status()
    
    def browse_ffmpeg_path(self):
        folder = QFileDialog.getExistingDirectory(self, "Выберите папку с FFmpeg")
        if folder:
            self.ffmpeg_path_input.setText(folder)
    
    def browse_ytdlp_path(self):
        folder = QFileDialog.getExistingDirectory(self, "Выберите папку для yt-dlp")
        if folder:
            self.ytdlp_path_input.setText(folder)
    
    def save_settings_from_tab(self):
        settings = {
            "ffmpeg_path": self.ffmpeg_path_input.text().strip() or "./",
            "yt_dlp_path": self.ytdlp_path_input.text().strip() or "./yt_dlp"
        }
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
        
        success = ensure_deno_installed(callback)
        if success:
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

    # --- НОВАЯ ВЕРСИЯ ВКЛАДКИ СКАЧИВАНИЯ ---
    def create_download_tab(self):
        layout = QVBoxLayout(self.download_tab)
        
        # Группа авторизации
        auth_group = QGroupBox("Авторизация (необходима для видео 18+ и закрытых видео)")
        auth_layout = QVBoxLayout()
        
        self.auth_group_btn = QButtonGroup(self)
        
        # 1. Без авторизации
        self.auth_none_radio = QRadioButton("Без авторизации (Только для открытых видео)")
        self.auth_none_radio.setChecked(True)
        self.auth_group_btn.addButton(self.auth_none_radio)
        auth_layout.addWidget(self.auth_none_radio)
        
        # 2. Из установленного браузера
        browser_layout = QHBoxLayout()
        self.auth_browser_radio = QRadioButton("Использовать профиль браузера:")
        self.auth_group_btn.addButton(self.auth_browser_radio)
        self.browser_combo = QComboBox()
        self.browser_combo.addItems(["chrome", "edge", "firefox", "brave", "opera", "vivaldi", "safari", "chromium"])
        browser_layout.addWidget(self.auth_browser_radio)
        browser_layout.addWidget(self.browser_combo)
        browser_layout.addStretch()
        auth_layout.addLayout(browser_layout)
        
        # 3. Из файла cookies.txt (Самый надежный)
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
        
        # Подсказка
        help_label = QLabel(
            'ℹ️ <b>Для нестандартных браузеров (Thorium, Яндекс и др.):</b><br>'
            '1. Установите расширение <b>"Get cookies.txt LOCALLY"</b><br>'
            '2. Авторизуйтесь на YouTube<br>'
            '3. Выгрузите файл <i>cookies.txt</i> и выберите его в пункте выше.'
        )
        help_label.setStyleSheet("color: #aaaaaa; font-size: 11px;")
        help_label.setWordWrap(True)
        auth_layout.addWidget(help_label)
        
        auth_group.setLayout(auth_layout)
        layout.addWidget(auth_group)
        
        # URL
        url_layout = QHBoxLayout()
        url_layout.addWidget(QLabel("URL видео:"))
        self.youtube_url_input = QLineEdit()
        self.youtube_url_input.setPlaceholderText("https://www.youtube.com/watch?v=...")
        url_layout.addWidget(self.youtube_url_input)
        layout.addLayout(url_layout)
        
        # Настройки качества и формата
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
        
        # Путь сохранения
        path_layout = QHBoxLayout()
        path_layout.addWidget(QLabel("Сохранить в:"))
        self.download_path_input = QLineEdit()
        self.download_path_input.setText(os.getcwd())
        path_layout.addWidget(self.download_path_input)
        download_browse_btn = QPushButton("Обзор")
        download_browse_btn.clicked.connect(self.browse_download_path)
        path_layout.addWidget(download_browse_btn)
        layout.addLayout(path_layout)
        
        # Кнопка скачать
        self.download_btn = QPushButton("Скачать")
        self.download_btn.setMinimumHeight(40)
        self.download_btn.clicked.connect(self.start_youtube_download)
        layout.addWidget(self.download_btn)
        
        self.download_progress_bar = QProgressBar()
        layout.addWidget(self.download_progress_bar)
        
        self.download_status_label = QLabel("Ожидание...")
        self.download_status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.download_status_label)
        
        log_label = QLabel("Лог:")
        layout.addWidget(log_label)
        
        self.download_log = QTextEdit()
        self.download_log.setReadOnly(True)
        self.download_log.setStyleSheet("background-color: #1e1e1e; color: #00ff00; font-family: Consolas;")
        layout.addWidget(self.download_log)

    def browse_cookies_file(self):
        file, _ = QFileDialog.getOpenFileName(self, "Выберите файл cookies.txt", "", "Text Files (*.txt);;All Files (*)")
        if file:
            self.cookies_file_input.setText(file)
            self.auth_file_radio.setChecked(True)

    def browse_download_path(self):
        folder = QFileDialog.getExistingDirectory(self, "Выберите папку для сохранения")
        if folder:
            self.download_path_input.setText(folder)
    
    def start_youtube_download(self):
        url = self.youtube_url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "Ошибка", "Введите URL видео!")
            return
        
        add_yt_dlp_to_path()
        
        if not is_yt_dlp_installed():
            reply = QMessageBox.question(
                self, "yt-dlp не установлен",
                "yt-dlp не найден. Установить сейчас?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                success, msg = install_or_update_yt_dlp()
                if not success:
                    QMessageBox.critical(self, "Ошибка", f"Не удалось установить yt-dlp:\n{msg}")
                    return
            else:
                return
        
        auth_mode = 'none'
        browser_name = None
        cookies_file = None
        
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
        if format_idx == 0:
            format_type = 'mp4'
        elif format_idx == 1:
            format_type = 'best'
        else:
            format_type = 'mp3'
            
        res_text = self.download_res_combo.currentText()
        if res_text == "Максимальное":
            resolution = None
        else:
            resolution = res_text.replace("p", "")
        
        self.download_btn.setEnabled(False)
        self.youtube_url_input.setEnabled(False)
        self.download_progress_bar.setValue(0)
        self.download_log.clear()
        
        self.append_download_log(f"Путь к yt-dlp: {get_yt_dlp_path()}")
        self.append_download_log(f"Формат: {format_type.upper()}, Качество: {res_text}")
        
        self.download_worker = YoutubeDownloadWorker(
            url, self.download_path_input.text(), format_type, resolution,
            auth_mode, browser_name, cookies_file
        )
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
        self.download_status_label.setText("Готово!")
        self.download_log.append("\n--- УСПЕШНО ЗАВЕРШЕНО ---")
        QMessageBox.information(self, "Успех", "Видео успешно скачано!")
        self.download_btn.setEnabled(True)
        self.youtube_url_input.setEnabled(True)
    
    def on_download_error(self, err_msg):
        self.download_status_label.setText("Ошибка")
        self.download_log.append(f"\n--- ОШИБКА ---\n{err_msg}")
        QMessageBox.critical(self, "Ошибка", f"Смотрите детали в логах.\n{err_msg}")
        self.download_btn.setEnabled(True)
        self.youtube_url_input.setEnabled(True)


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
        import sys
        import traceback
        from settings_manager import get_yt_dlp_path, get_actual_ffmpeg_path
        from yt_dlp_manager import get_yt_dlp_bin_dir, get_deno_path
        
        yt_path = get_yt_dlp_path()
        bin_path = get_yt_dlp_bin_dir()
        if yt_path not in sys.path:
            sys.path.insert(0, yt_path)
        if bin_path not in sys.path:
            sys.path.insert(0, bin_path)
        
        try:
            import yt_dlp
        except ImportError:
            self.error_signal.emit("Модуль yt_dlp не найден. Обновите его в настройках.")
            return

        # Добавляем Deno в PATH, чтобы yt-dlp мог его найти для обхода блокировок
        deno_path = get_deno_path()
        deno_dir = os.path.dirname(deno_path)
        if os.path.exists(deno_path) and deno_dir not in os.environ.get("PATH", ""):
            os.environ["PATH"] = deno_dir + os.pathsep + os.environ.get("PATH", "")
            self.log_signal.emit(f"[INFO] Deno добавлен в PATH для обхода блокировок YouTube")
        
        res_str = ""
        if self.resolution:
            res_str = f"[height<={self.resolution}]"
        
        # Формируем строку фильтра с fallback-вариантами, чтобы не было ошибки "Requested format is not available"
        if self.format_type == 'mp4':
            # Сначала пытаемся найти mp4 видео + m4a аудио. Если нет, берем просто mp4. Если и этого нет, берем любой лучший.
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
            'fragment_retries': 10,
            'ignoreerrors': False,
            'quiet': True,        # Убираем спам в консоли
            'no_warnings': True,  # Убираем предупреждения
            'verbose': False,     # Отключаем DEBUG-логи
            'ffmpeg_location': get_actual_ffmpeg_path(),
        }
        
        if merge_format:
            ydl_opts['merge_output_format'] = merge_format
        
        if self.format_type == 'mp3':
            ydl_opts['postprocessors'] =[{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]
            
        # --- ПРИМЕНЕНИЕ АВТОРИЗАЦИИ ---
        if self.auth_mode == 'browser' and self.browser_name:
            ydl_opts['cookiesfrombrowser'] = (self.browser_name,)
            self.log_signal.emit(f"[INFO] Используются cookies из браузера: {self.browser_name}")
        elif self.auth_mode == 'file' and self.cookies_file:
            ydl_opts['cookiefile'] = self.cookies_file
            self.log_signal.emit(f"[INFO] Используются cookies из файла: {self.cookies_file}")
        else:
            self.log_signal.emit("[INFO] Скачивание без авторизации (анонимно)")
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                self.log_signal.emit("--- Анализ видео ---")
                self.log_signal.emit(f"[URL] {self.url}")
                
                info = ydl.extract_info(self.url, download=False)
                
                if info is None:
                    self.log_signal.emit("\n" + "="*50)
                    self.log_signal.emit("!!! ОШИБКА ЗАГРУЗКИ !!!")
                    self.log_signal.emit("="*50)
                    self.log_signal.emit("Не удалось получить информацию о видео.")
                    self.log_signal.emit("Если видео требует подтверждения возраста (18+) или скрыто:")
                    self.log_signal.emit("- Используйте метод 'Из файла cookies.txt'")
                    self.log_signal.emit("="*50)
                    self.error_signal.emit("Ошибка: не удалось получить информацию о видео (возрастное ограничение?)")
                    return
                
                title = info.get('title', 'Video')
                self.log_signal.emit(f"Название: {title}")
                
                if 'requested_formats' in info:
                    for f in info['requested_formats']:
                        ftype = "ВИДЕО" if f.get('vcodec') != 'none' else "АУДИО"
                        note = f.get('format_note', 'unknown')
                        self.log_signal.emit(f"\n[{ftype}] Качество: {note}")
                
                self.log_signal.emit("\n--- Начало загрузки ---")
                ydl.download([self.url])
            
            self.finished_signal.emit()
            
        except Exception as e:
            # Не печатаем огромный traceback в UI лог, чтобы не засорять
            self.log_signal.emit(f"\n=== КРИТИЧЕСКАЯ ОШИБКА ===")
            self.log_signal.emit(f"Тип: {type(e).__name__}")
            self.log_signal.emit(f"Сообщение: {str(e)}")
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


def main():
    app = QApplication(sys.argv)
    
    processor = VideoProcessor()
    
    logging.info("--- Информация о среде выполнения ---")
    gpu_info = processor.get_gpu_info()
    logging.info(gpu_info)
    if "Доступные GPU" in gpu_info:
        logging.info("-> Обнаружена поддержка аппаратного кодирования (GPU).")
    else:
        logging.info("-> Аппаратное кодирование не обнаружено. Сжатие будет выполняться на процессоре (CPU).")
    logging.info("------------------------------------\n")

    ffmpeg_path = get_actual_ffmpeg_path()
    ffprobe_path = get_ffprobe_path()
    if not os.path.exists(ffmpeg_path) or not os.path.exists(ffprobe_path):
        downloader = FFmpegDownloader()
        if not downloader.check_and_download():
            logging.critical("Критическая ошибка: FFmpeg не найден и не может быть скачан. Приложение будет закрыто.")
            return -1
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()