import sys
import os
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                               QHBoxLayout, QPushButton, QLabel, QFileDialog,
                               QProgressBar, QTextEdit, QGroupBox,
                               QMessageBox, QComboBox, QCheckBox, QSlider,
                               QRadioButton, QButtonGroup,
                               QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QFont, QDragEnterEvent, QDropEvent
from config import (OUTPUT_FORMATS, CODECS, DEFAULT_OUTPUT_FORMAT_KEY, DEFAULT_CODEC_KEY,
                   DEFAULT_USE_HARDWARE_ENCODING)
from video_processor import VideoProcessor
from ffmpeg_downloader import FFmpegDownloader
from dialogs import VideoInfoDialog
from threads import WorkerThread


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.processor = VideoProcessor()
        self.file_queue = []  # Список кортежей (путь, информация_о_файле)
        self.current_file = None
        self.current_info = None
        self.compression_worker = None
        self.active_workers = []
        self._cached_info = None
        self.processing_stopped = False  # Флаг для остановки всей очереди
        
        # Переменные для отслеживания общего прогресса
        self.batch_in_progress = False
        self.total_files_in_batch = 0
        self.completed_files_in_batch = 0
        
        # Путь для сохранения файлов
        self.output_directory = None
        
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Video Compressor")
        self.setGeometry(100, 100, 1000, 700)
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        file_group = self.create_file_group()
        main_layout.addWidget(file_group)

        # Группа с таблицей очереди
        queue_group = QGroupBox("Очередь файлов")
        queue_layout = QVBoxLayout()
        
        # Создаем таблицу для очереди файлов
        self.queue_table = QTableWidget()
        self.queue_table.setColumnCount(4)
        self.queue_table.setHorizontalHeaderLabels(["Имя файла", "Размер", "Статус VFR", "Примерный размер после сжатия"])
        self.queue_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.queue_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.queue_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.queue_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.queue_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.queue_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.queue_table.setAlternatingRowColors(True)
        
        queue_layout.addWidget(self.queue_table)
        queue_group.setLayout(queue_layout)
        main_layout.addWidget(queue_group)

        self.estimated_label = QLabel("Примерный размер после сжатия: —")
        main_layout.addWidget(self.estimated_label)

        settings_group = self.create_settings_group()
        main_layout.addWidget(settings_group)

        process_group = self.create_process_group()
        main_layout.addWidget(process_group)

        log_group = QGroupBox("Лог")
        log_layout = QVBoxLayout()
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        log_layout.addWidget(self.log_text)
        log_group.setLayout(log_layout)
        main_layout.addWidget(log_group)

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
        self.info_btn = QPushButton("Информация о файле")
        self.info_btn.clicked.connect(self.show_info)
        self.info_btn.setEnabled(False)
        
        # Кнопка выбора пути сохранения
        self.output_dir_btn = QPushButton("Путь сохранения")
        self.output_dir_btn.clicked.connect(self.select_output_directory)
        self.output_dir_btn.setToolTip("Выбрать папку для сохранения сжатых файлов")
        self.output_dir_label = QLabel("Сохранять в папке с оригиналами")
        self.output_dir_label.setStyleSheet("color: gray; font-size: 10px;")
        
        file_select_layout.addWidget(self.select_file_btn)
        file_select_layout.addWidget(self.info_btn)
        file_select_layout.addWidget(self.output_dir_btn)
        file_select_layout.addStretch()
        file_layout.addLayout(file_select_layout)
        
        # Метка с путем сохранения
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

    def create_settings_group(self):
        settings_group = QGroupBox("2. Настройки сжатия")
        settings_layout = QVBoxLayout()
        
        # Выбор формата
        format_layout = QHBoxLayout()
        format_layout.addWidget(QLabel("Формат:"))
        self.format_combo = QComboBox()
        for ext, details in OUTPUT_FORMATS.items():
            self.format_combo.addItem(f".{ext.upper()}", ext)
        self.format_combo.setCurrentText(f".{DEFAULT_OUTPUT_FORMAT_KEY.upper()}")
        self.format_combo.currentTextChanged.connect(self.on_format_changed)
        format_layout.addWidget(self.format_combo)
        format_layout.addStretch()
        
        # Выбор кодека
        codec_layout = QHBoxLayout()
        codec_layout.addWidget(QLabel("Кодек:"))
        self.codec_combo = QComboBox()
        self.update_codec_options()
        self.codec_combo.currentTextChanged.connect(self.on_codec_changed)
        codec_layout.addWidget(self.codec_combo)
        codec_layout.addStretch()
        
        # Выбор типа кодирования
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
        
        # Выбор пресета
        preset_layout = QHBoxLayout()
        preset_layout.addWidget(QLabel("Пресет:"))
        self.preset_combo = QComboBox()
        self.update_preset_options()
        self.preset_combo.currentTextChanged.connect(self.on_preset_changed)
        preset_layout.addWidget(self.preset_combo)
        preset_layout.addStretch()
        
        # Настройка CRF
        crf_layout = QHBoxLayout()
        self.crf_label = QLabel("CRF: ")
        self.crf_slider = QSlider(Qt.Horizontal)
        self.crf_slider.valueChanged.connect(self.on_crf_changed)
        crf_layout.addWidget(self.crf_label)
        crf_layout.addWidget(self.crf_slider)
        
        # Настройка VFR
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
        settings_group.setLayout(settings_layout)
        return settings_group

    def create_process_group(self):
        process_group = QGroupBox("3. Запуск обработки")
        process_layout = QVBoxLayout()
        
        # Кнопки управления процессом
        buttons_layout = QHBoxLayout()
        self.process_btn = QPushButton("Сжать видео")
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
            self.log_text.append(f"Выбрана папка для сохранения: {directory}")
        else:
            self.output_directory = None
            self.output_dir_label.setText("Сохранять в папке с оригиналами")
            self.output_dir_label.setStyleSheet("color: gray; font-size: 10px;")

    def add_file_to_queue(self, file_path):
        if os.path.isfile(file_path):
            info = self.processor.get_video_info(file_path)
            if "error" not in info:
                self.file_queue.append((file_path, info))
                self.update_queue_table()
                self.update_queue_label()
                print(f"Файл добавлен в очередь: {file_path}")
                
                if len(self.file_queue) == 1 and self.current_file is None:
                    self.current_file, self.current_info = self.file_queue[0]
                    self.set_current_file(self.current_file, self.current_info)

    def update_queue_table(self):
        self.queue_table.setRowCount(len(self.file_queue))
        
        crf_value = self.crf_slider.value()
        codec = self.current_codec()
        use_hardware = self.hardware_radio.isChecked()
        force_vfr_fix = self.vfr_checkbox.isChecked()
        
        for row, (file_path, info) in enumerate(self.file_queue):
            file_name_item = QTableWidgetItem(os.path.basename(file_path))
            self.queue_table.setItem(row, 0, file_name_item)
            
            size_mb = info.get("size_mb", 0)
            size_item = QTableWidgetItem(f"{size_mb:.1f} МБ")
            self.queue_table.setItem(row, 1, size_item)
            
            needs_vfr = info.get("needs_vfr_fix", False)
            vfr_text = "Требуется" if needs_vfr else "Не требуется"
            vfr_item = QTableWidgetItem(vfr_text)
            if needs_vfr:
                vfr_item.setForeground(Qt.GlobalColor.red)
            else:
                vfr_item.setForeground(Qt.GlobalColor.darkGreen)
            self.queue_table.setItem(row, 2, vfr_item)
            
            est_size = self.processor.estimated_size_mb(
                video_bitrate=info.get("video_bitrate", 0),
                audio_bitrate=info.get("audio_bitrate", 128000),
                duration=info["duration"],
                crf=crf_value,
                codec=codec,
                needs_vfr_fix=needs_vfr or force_vfr_fix,
                use_hardware=use_hardware
            )
            est_item = QTableWidgetItem(f"{est_size:.1f} МБ")
            self.queue_table.setItem(row, 3, est_item)
        
        self.queue_table.viewport().update()

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
        self.info_btn.setEnabled(True)
        self._cached_info = file_info
        self.check_vfr_status()
        self.update_estimated_size(self.crf_slider.value(), self.current_codec())

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
        self.update_estimated_size(self.crf_slider.value(), codec_key)
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
        self.update_estimated_size(self.crf_slider.value(), codec_key)
        self.update_queue_table()

    def on_preset_changed(self):
        self.update_queue_table()

    def on_encoding_changed(self):
        self.update_estimated_size(self.crf_slider.value(), self.current_codec())
        self.update_queue_table()

    def on_crf_changed(self, value):
        if value == self.crf_slider.minimum():
            self.crf_label.setText("CRF: только VFR-fix (copy)")
        else:
            self.crf_label.setText(f"CRF: {value}")
        self.update_estimated_size(value, self.current_codec())
        self.update_queue_table()

    def update_estimated_size(self, crf, codec):
        if not self.current_file:
            self.estimated_label.setText("Примерный размер после сжатия: —")
            return
        
        info = self._cached_info if self._cached_info else None
        
        if info is None:
            return

        est = self.processor.estimated_size_mb(
            video_bitrate=info.get("video_bitrate", 0),
            audio_bitrate=info.get("audio_bitrate", 128000),
            duration=info["duration"],
            crf=crf,
            codec=codec,
            needs_vfr_fix=info.get('needs_vfr_fix', False) or self.vfr_checkbox.isChecked(),
            use_hardware=self.hardware_radio.isChecked()
        )

        self.estimated_label.setText(f"Примерный размер после сжатия: {est:.1f} МБ")

    def check_vfr_status(self):
        if self.current_file:
            needs_fix = self._cached_info.get('needs_vfr_fix', False) if self._cached_info else False
            if needs_fix:
                self.vfr_status_label.setText("Статус VFR: Рекомендуется!")
                self.vfr_status_label.setStyleSheet("color: orange;")
            else:
                self.vfr_status_label.setText("Статус VFR: Не требуется")
                self.vfr_status_label.setStyleSheet("color: green;")

    def show_info(self):
        if self.current_file and self._cached_info:
            self.show_info_dialog(self._cached_info)

    def show_info_dialog(self, info):
        dialog = VideoInfoDialog(info, self)
        dialog.exec()

    def start_processing(self):
        if not self.current_file:
            self.log_text.append("Предупреждение: Сначала выберите файл")
            return
        
        # Инициализация пакета, если это первый файл
        if not self.batch_in_progress:
            self.batch_in_progress = True
            self.total_files_in_batch = len(self.file_queue) + 1 # +1 для текущего файла
            self.completed_files_in_batch = 0
            print(f"Начало обработки пакета из {self.total_files_in_batch} файла(ов).")
        
        self.processing_stopped = False
        
        params = {
            "input_path": self.current_file,
            "output_format": self.format_combo.currentData(),
            "codec": self.codec_combo.currentData(),
            "crf_value": self.crf_slider.value(),
            "preset_value": self.preset_combo.currentData(),
            "force_vfr_fix": self.vfr_checkbox.isChecked(),
            "use_hardware": self.hardware_radio.isChecked(),
            "output_dir": self.output_directory  # Передаем путь сохранения
        }
        self.set_ui_enabled(False)
        self.run_compression_worker(**params)

    def cancel_processing(self):
        reply = QMessageBox.question(
            self, "Подтверждение отмены",
            "Вы уверены, что хотите отменить процесс сжатия и всю очередь?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.processing_stopped = True
            if self.compression_worker:
                self.log_text.append("Отмена процесса сжатия и всей очереди...")
                self.status_label.setText("Отмена процесса...")
                self.compression_worker.stop()
                QTimer.singleShot(1000, self.on_canceled)

    def on_canceled(self):
        self.log_text.append("Процесс сжатия и обработка очереди отменены пользователем")
        self.status_label.setText("Отменено пользователем")
        self.progress_bar.setValue(0)
        
        # Сброс состояния пакета
        self.batch_in_progress = False
        self.total_files_in_batch = 0
        self.completed_files_in_batch = 0
        
        self.current_file = None
        self.current_info = None
        self.set_ui_enabled(True)
        self.file_label.setText("Перетащите файлы сюда или нажмите 'Выбрать'")
        self.status_label.setText("Готов к работе")
        self.progress_bar.setValue(0)
        self.info_btn.setEnabled(False)
        self.process_btn.setEnabled(False)

    def run_compression_worker(self, **kwargs):
        self.compression_worker = WorkerThread(self.processor, 'compress', **kwargs)
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
            # Рассчитываем общий прогресс для всего пакета
            current_file_progress = value / 100.0
            total_progress_float = (self.completed_files_in_batch + current_file_progress) / self.total_files_in_batch
            total_progress_percent = int(total_progress_float * 100)
            
            self.progress_bar.setValue(total_progress_percent)
            
            current_file_name = os.path.basename(self.current_file) if self.current_file else "неизвестный файл"
            self.status_label.setText(f"Сжатие: {current_file_name} ({value}%) | Общий прогресс: {total_progress_percent}%")
        else:
            # Для одиночного файла или вне пакета
            self.progress_bar.setValue(value)
            self.status_label.setText(message)

    def _handle_file_completion(self):
        """Внутренний метод для обновления счетчика обработанных файлов."""
        if self.batch_in_progress:
            self.completed_files_in_batch += 1
            print(f"Файл обработан. Прогресс по пакету: {self.completed_files_in_batch}/{self.total_files_in_batch}")

    def on_finished(self, result):
        self.log_text.append(f"Готово: {result}")
        self._handle_file_completion()
        
        if not self.processing_stopped:
            self.process_next_file()
        else:
            self.on_canceled()

    def on_error(self, error):
        self.log_text.append(f"ОШИБКА: {error}")
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
            self.file_queue = [(path, info) for path, info in self.file_queue if path != self.current_file]
            self.update_queue_table()
        
        self.update_queue_label()
        if self.file_queue:
            self.current_file, self.current_info = self.file_queue[0]
            self.set_current_file(self.current_file, self.current_info)
            QTimer.singleShot(500, self.start_processing)
        else:
            # Пакет завершен
            if self.batch_in_progress:
                print("Обработка пакета завершена.")
                self.batch_in_progress = False
                self.total_files_in_batch = 0
                self.completed_files_in_batch = 0

            self.current_file = None
            self.current_info = None
            self.set_ui_enabled(True)
            self.file_label.setText("Перетащите файлы сюда или нажмите 'Выбрать'")
            self.status_label.setText("Готов к работе")
            self.progress_bar.setValue(0)
            self.info_btn.setEnabled(False)
            self.process_btn.setEnabled(False)

    def set_ui_enabled(self, enabled):
        self.select_file_btn.setEnabled(enabled)
        self.process_btn.setEnabled(enabled and self.current_file is not None)
        self.cancel_btn.setEnabled(not enabled and self.current_file is not None)
        self.cancel_btn.setVisible(not enabled and self.current_file is not None)
        self.info_btn.setEnabled(enabled and self.current_file is not None)
        self.format_combo.setEnabled(enabled)
        self.codec_combo.setEnabled(enabled)
        self.preset_combo.setEnabled(enabled)
        self.crf_slider.setEnabled(enabled)
        self.vfr_checkbox.setEnabled(enabled)
        self.hardware_radio.setEnabled(enabled)
        self.software_radio.setEnabled(enabled)
        self.output_dir_btn.setEnabled(enabled)

    def closeEvent(self, event):
        if self.compression_worker and self.compression_worker.isRunning():
            reply = QMessageBox.question(self, "Выход",
                                         "Процесс сжатия еще не завершен. Вы уверены, что хотите выйти?",
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


def main():
    app = QApplication(sys.argv)
    
    # Проверка и вывод информации о среде выполнения
    processor = VideoProcessor()
    print("--- Информация о среде выполнения ---")
    gpu_info = processor.get_gpu_info()
    print(gpu_info)
    if "Доступные GPU" in gpu_info:
        print("-> Обнаружена поддержка аппаратного кодирования (GPU).")
        print("-> В настройках программы можно выбрать тип кодирования: 'Аппаратное (NVENC)' или 'Программное (CPU)'.")
    else:
        print("-> Аппаратное кодирование не обнаружено. Сжатие будет выполняться на процессоре (CPU).")
    print("------------------------------------\n")

    if not os.path.exists("ffmpeg.exe") or not os.path.exists("ffprobe.exe"):
        downloader = FFmpegDownloader()
        if not downloader.check_and_download():
            print("Критическая ошибка: FFmpeg не найден и не может быть скачан. Приложение будет закрыто.")
            return -1
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()