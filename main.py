import sys
import os
import logging
from datetime import datetime
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                               QHBoxLayout, QPushButton, QLabel, QFileDialog,
                               QProgressBar, QTextEdit, QGroupBox,
                               QMessageBox, QComboBox, QCheckBox, QSlider,
                               QRadioButton, QButtonGroup,
                               QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
                               QTabWidget, QToolButton, QSpinBox)
from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QColor
from config import (OUTPUT_FORMATS, CODECS, DEFAULT_OUTPUT_FORMAT_KEY, 
                    DEFAULT_CODEC_KEY, DEFAULT_USE_HARDWARE_ENCODING, EXTRACTED_FRAME_SUFFIX)
from video_processor import VideoProcessor
from ffmpeg_downloader import FFmpegDownloader
from dialogs import VideoInfoDialog
from threads import WorkerThread
from gui_logger import setup_logging
from settings_manager import get_actual_ffmpeg_path, get_ffprobe_path
from tab_settings import SettingsTab
from tab_download import DownloadTab
from crf_extractor import format_crf_display

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.processor = VideoProcessor()
        self.file_queue =[]
        self.current_file = None
        self.current_info = None
        self.compression_worker = None
        self.active_workers =[]
        self._cached_info = None
        self.processing_stopped = False
        
        self.batch_in_progress = False
        self.total_files_in_batch = 0
        self.completed_files_in_batch = 0
        
        self.batch_test_in_progress = False
        self.files_to_test = []
        
        self.output_directory = None
        self.compression_start_time = None
        
        self.quality_test_frame_number = 0
        
        setup_logging(self.log_slot)
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Video Compressor")
        self.setGeometry(100, 100, 1250, 750)
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)
        
        self.main_tab = QWidget()
        self.tab_widget.addTab(self.main_tab, "Редактор")
        main_tab_layout = QVBoxLayout(self.main_tab)
        
        self.log_tab = QWidget()
        self.tab_widget.addTab(self.log_tab, "Логи")
        log_tab_layout = QVBoxLayout(self.log_tab)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        log_tab_layout.addWidget(self.log_text)

        self.settings_tab = SettingsTab()
        self.tab_widget.addTab(self.settings_tab, "Настройки")

        self.download_tab = DownloadTab()
        self.tab_widget.addTab(self.download_tab, "Скачать видео")

        file_group = self.create_file_group()
        main_tab_layout.addWidget(file_group)

        queue_group = QGroupBox("Очередь файлов")
        queue_layout = QVBoxLayout()
        self.queue_table = QTableWidget()
        self.queue_table.setColumnCount(9)
        self.queue_table.setHorizontalHeaderLabels([
            "Имя файла", "Размер", "Длительность", "CRF", "Статус VFR", 
            "Прим. размер (Разница)", "VMAF", "Время сжатия", "Действия"
        ])
        self.queue_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for i in range(1, 9):
            self.queue_table.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        self.queue_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.queue_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.queue_table.setAlternatingRowColors(True)
        queue_layout.addWidget(self.queue_table)
        queue_group.setLayout(queue_layout)
        main_tab_layout.addWidget(queue_group)

        self.operations_tabs = QTabWidget()
        self.compression_tab = self.create_compression_tab()
        self.operations_tabs.addTab(self.compression_tab, "Сжатие видео")
        self.trim_tab = self.create_trim_tab()
        self.operations_tabs.addTab(self.trim_tab, "Сокращение")
        self.normalize_tab = self.create_normalize_tab()
        self.operations_tabs.addTab(self.normalize_tab, "Починка громкости")
        self.quality_test_tab = self.create_quality_test_tab()
        self.operations_tabs.addTab(self.quality_test_tab, "Тест качества")
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
        self.select_file_btn = QPushButton("Выбрать файл(ы)")
        self.select_file_btn.clicked.connect(self.select_files)
        self.output_dir_btn = QPushButton("Путь сохранения")
        self.output_dir_btn.clicked.connect(self.select_output_directory)
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
        if DEFAULT_USE_HARDWARE_ENCODING: self.hardware_radio.setChecked(True)
        else: self.software_radio.setChecked(True)
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
        self.crf_slider = QSlider(Qt.Orientation.Horizontal)
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
        info_label = QLabel("Нормализует громкость аудио в два этапа:\n1. Динамическая нормализация\n2. Нормализация громкости")
        info_label.setStyleSheet("color: gray;")
        output_label = QLabel("Видео будет сохранено с суффиксом '_volnorm'.")
        output_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(info_label)
        layout.addWidget(output_label)
        layout.addStretch()
        return tab

    def create_quality_test_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        info_label = QLabel("Извлечение конкретного кадра из видео для оценки качества.\nКадр сохраняется в папку с исходным видео.")
        info_label.setStyleSheet("color: gray;")
        layout.addWidget(info_label)
        
        frame_layout = QHBoxLayout()
        frame_layout.addWidget(QLabel("Номер кадра:"))
        self.frame_number_spin = QSpinBox()
        self.frame_number_spin.setRange(0, 999999)
        self.frame_number_spin.setValue(0)
        self.frame_number_spin.setSuffix(" кадр")
        self.frame_number_spin.valueChanged.connect(self.on_quality_test_frame_changed)
        frame_layout.addWidget(self.frame_number_spin)
        frame_layout.addStretch()
        layout.addLayout(frame_layout)
        
        fps_info_label = QLabel("FPS видео: —")
        fps_info_label.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(fps_info_label)
        self.quality_fps_label = fps_info_label
        
        total_frames_label = QLabel("Всего кадров: —")
        total_frames_label.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(total_frames_label)
        self.quality_total_frames_label = total_frames_label
        
        layout.addSpacing(10)
        
        self.extract_frame_status = QLabel("")
        self.extract_frame_status.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(self.extract_frame_status)
        
        layout.addStretch()
        return tab

    def create_process_group(self):
        process_group = QGroupBox("Запуск обработки")
        process_layout = QVBoxLayout()
        buttons_layout = QHBoxLayout()
        
        self.process_btn = QPushButton("Начать")
        self.process_btn.clicked.connect(self.start_processing)
        self.process_btn.setEnabled(False)
        
        self.test_all_btn = QPushButton("Тест всех")
        self.test_all_btn.clicked.connect(self.start_batch_test)
        self.test_all_btn.setEnabled(False)
        self.test_all_btn.setToolTip("Запустить тест сжатия для всех видео в очереди")
        
        self.cancel_btn = QPushButton("Отменить")
        self.cancel_btn.clicked.connect(self.cancel_processing)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setVisible(False)
        
        buttons_layout.addWidget(self.process_btn)
        buttons_layout.addWidget(self.test_all_btn)
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
        if event.mimeData().hasUrls(): event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            if url.isLocalFile(): self.add_file_to_queue(url.toLocalFile())
        self.update_queue_label()

    def select_output_directory(self):
        directory = QFileDialog.getExistingDirectory(self, "Выберите папку для сохранения", "" if not self.output_directory else self.output_directory)
        if directory:
            self.output_directory = directory
            self.output_dir_label.setText(directory)
            self.output_dir_label.setStyleSheet("color: green; font-size: 10px;")
        else:
            self.output_directory = None
            self.output_dir_label.setText("Сохранять в папке с оригиналами")
            self.output_dir_label.setStyleSheet("color: gray; font-size: 10px;")

    def add_file_to_queue(self, file_path):
        if os.path.isfile(file_path):
            info = self.processor.get_video_info(file_path)
            if "error" not in info:
                info["is_video"] = info.get("width", 0) > 0 and info.get("height", 0) > 0
                self.file_queue.append((file_path, info))
                self.update_queue_table()
                self.update_queue_label()
                if len(self.file_queue) == 1 and self.current_file is None:
                    self.current_file, self.current_info = self.file_queue.pop(0)
                    self.set_current_file(self.current_file, self.current_info)
                    self.set_ui_enabled(True)

    def update_queue_table(self):
        all_files =[]
        if self.current_file: all_files.append((self.current_file, self.current_info))
        all_files.extend(self.file_queue)
        self.queue_table.setRowCount(len(all_files))
        
        for row, (file_path, info) in enumerate(all_files):
            self.queue_table.setItem(row, 0, QTableWidgetItem(os.path.basename(file_path)))
            self.queue_table.setItem(row, 1, QTableWidgetItem(f"{info.get('size_mb', 0):.1f} МБ"))
            self.queue_table.setItem(row, 2, QTableWidgetItem(self.processor.size_estimator.format_duration(info.get("duration", 0))))
            
            # CRF Колонка (нет = зеленый, цифра = красный)
            crf_value = info.get('crf_value')
            crf_text = format_crf_display(crf_value)
            crf_item = QTableWidgetItem(crf_text)
            crf_item.setForeground(Qt.GlobalColor.darkGreen if crf_text == "нет" else Qt.GlobalColor.red)
            self.queue_table.setItem(row, 3, crf_item)
            
            vfr_item = QTableWidgetItem("Требуется" if info.get("needs_vfr_fix") else "Не требуется")
            vfr_item.setForeground(Qt.GlobalColor.red if info.get("needs_vfr_fix") else Qt.GlobalColor.darkGreen)
            self.queue_table.setItem(row, 4, vfr_item)
            
            # Объединенный столбец Размер (Разница)
            diff_text = info.get('test_diff', '')
            est_size_text = info.get('test_est_size', '-')
            if diff_text:
                size_diff_text = f"{est_size_text} ({diff_text})"
            else:
                size_diff_text = "-"
                
            size_diff_item = QTableWidgetItem(size_diff_text)
            if info.get('is_profitable', False):
                size_diff_item.setForeground(Qt.GlobalColor.darkGreen)
            elif diff_text:
                size_diff_item.setForeground(Qt.GlobalColor.red)
            self.queue_table.setItem(row, 5, size_diff_item)
            
            # Столбец VMAF
            vmaf_val = info.get('test_vmaf', -1.0)
            if vmaf_val == -2.0:
                vmaf_text = "Нет libvmaf"
                vmaf_color = Qt.GlobalColor.gray
            elif vmaf_val >= 0:
                vmaf_text = f"{vmaf_val:.1f}"
                if vmaf_val >= 93:
                    vmaf_color = Qt.GlobalColor.darkGreen
                elif vmaf_val >= 80:
                    vmaf_color = QColor(255, 140, 0) # Оранжевый/Желтый
                else:
                    vmaf_color = Qt.GlobalColor.red
            else:
                vmaf_text = "-"
                vmaf_color = Qt.GlobalColor.black
                
            vmaf_item = QTableWidgetItem(vmaf_text)
            if vmaf_text != "-":
                vmaf_item.setForeground(vmaf_color)
            self.queue_table.setItem(row, 6, vmaf_item)
            
            self.queue_table.setItem(row, 7, QTableWidgetItem(info.get('test_est_time', '-')))
            
            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(2, 2, 2, 2)
            
            test_btn = QToolButton()
            test_btn.setText("🧪")
            test_btn.setToolTip("Запустить тест сжатия (определить выгоду и время)")
            test_btn.setProperty("file_path", file_path)
            test_btn.clicked.connect(self.on_chunk_test_clicked)
            
            info_btn = QToolButton()
            info_btn.setText("ℹ")
            info_btn.setProperty("video_info", info)
            info_btn.clicked.connect(self.on_info_button_clicked)
            
            delete_btn = QToolButton()
            delete_btn.setText("✕")
            delete_btn.setProperty("file_path", file_path)
            delete_btn.clicked.connect(self.on_delete_button_clicked)
            
            actions_layout.addWidget(test_btn)
            actions_layout.addWidget(info_btn)
            actions_layout.addWidget(delete_btn)
            actions_layout.addStretch()
            self.queue_table.setCellWidget(row, 8, actions_widget)
        self.queue_table.viewport().update()

    def start_batch_test(self):
        if not self.current_file: return
        
        self.files_to_test = []
        if self.current_file:
            self.files_to_test.append(self.current_file)
        for path, _ in self.file_queue:
            self.files_to_test.append(path)
            
        self.batch_test_in_progress = True
        self.processing_stopped = False
        self.process_next_test()

    def process_next_test(self):
        if self.processing_stopped or not self.files_to_test:
            self.batch_test_in_progress = False
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(100 if not self.processing_stopped else 0)
            self.status_label.setText("Тестирование всех файлов завершено" if not self.processing_stopped else "Отменено")
            self.set_ui_enabled(True)
            return
            
        next_file = self.files_to_test.pop(0)
        self.start_chunk_test(next_file)

    def on_chunk_test_clicked(self):
        button = self.sender()
        if button and button.property("file_path"):
            file_path = button.property("file_path")
            self.batch_test_in_progress = False # Сброс, так как это одиночный запуск
            self.start_chunk_test(file_path)

    def start_chunk_test(self, file_path):
        self.set_ui_enabled(False)
        self.status_label.setText(f"Выполняется тест фрагментов для {os.path.basename(file_path)}...")
        self.progress_bar.setRange(0, 0)

        params = {
            "input_path": file_path,
            "codec": self.codec_combo.currentData(),
            "crf_value": self.crf_slider.value(),
            "preset_value": self.preset_combo.currentData(),
            "use_hardware": self.hardware_radio.isChecked()
        }

        self.compression_worker = WorkerThread(self.processor, "chunk_test", **params)
        self.compression_worker.finished.connect(self.on_chunk_test_finished)
        self.compression_worker.error_occurred.connect(self.on_chunk_test_error)
        self.active_workers.append(self.compression_worker)
        self.compression_worker.start()

    def on_chunk_test_finished(self, result):
        if type(result) == dict and "file_path" in result:
            file_path = result["file_path"]
            if self.current_file == file_path:
                self.current_info.update(result)
            else:
                for q_path, q_info in self.file_queue:
                    if q_path == file_path:
                        q_info.update(result)
                        break

        self.update_queue_table()
        
        if self.batch_test_in_progress:
            self.process_next_test()
        else:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(100)
            self.status_label.setText("Тест успешно завершен")
            self.set_ui_enabled(True)

    def on_chunk_test_error(self, error):
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        
        if self.batch_test_in_progress:
            self.log_slot(f"Ошибка теста: {error}")
            self.process_next_test() # Пропускаем файл с ошибкой и идем дальше
        else:
            self.status_label.setText("Ошибка при тестировании!")
            QMessageBox.critical(self, "Ошибка теста", f"Не удалось выполнить тест:\n{error}")
            self.set_ui_enabled(True)

    def on_info_button_clicked(self):
        button = self.sender()
        if button and button.property("video_info"):
            VideoInfoDialog(button.property("video_info"), self).exec()

    def on_delete_button_clicked(self):
        button = self.sender()
        if button and button.property("file_path"):
            self.remove_from_queue(button.property("file_path"))

    def remove_from_queue(self, file_path_to_delete):
        if self.current_file == file_path_to_delete:
            self.current_file, self.current_info, self._cached_info = None, None, None
            if self.file_queue:
                self.current_file, self.current_info = self.file_queue.pop(0)
                self.set_current_file(self.current_file, self.current_info)
            else:
                self.set_ui_enabled(True) 
                self.file_label.setText("Перетащите файлы сюда или нажмите 'Выбрать'")
                self.process_btn.setEnabled(False)
                self.test_all_btn.setEnabled(False)
                self.vfr_status_label.setText("Статус VFR: Не определено")
        else:
            try:
                index = next(i for i, (path, _) in enumerate(self.file_queue) if path == file_path_to_delete)
                self.file_queue.pop(index)
            except StopIteration: pass
        self.update_queue_table()
        self.update_queue_label()

    def update_queue_label(self):
        self.queue_label.setText(f"В очереди: {len(self.file_queue)} файлов")

    def select_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Выберите видеофайлы", "", "Video files (*.mp4 *.avi *.mkv *.mov *.webm)")
        if files:
            for file in files: self.add_file_to_queue(file)

    def set_current_file(self, file_path, file_info):
        self.file_label.setText(f"Текущий файл: {os.path.basename(file_path)}")
        self.process_btn.setEnabled(True)
        self.test_all_btn.setEnabled(True)
        self._cached_info = file_info
        self.check_vfr_status()
        self.operations_tabs.setTabEnabled(0, file_info.get("is_video", True))
        self.update_quality_test_tab(file_info)

    def current_codec(self): return self.codec_combo.currentData()
    def current_preset(self): return self.preset_combo.currentData()

    def update_codec_options(self):
        self.codec_combo.clear()
        current_format = self.format_combo.currentData()
        for codec_key in OUTPUT_FORMATS[current_format]["compatible_codecs"]:
            self.codec_combo.addItem(CODECS[codec_key]["name"], codec_key)
        index = self.codec_combo.findData(OUTPUT_FORMATS[current_format]["default_codec"])
        if index >= 0: self.codec_combo.setCurrentIndex(index)

    def update_preset_options(self):
        self.preset_combo.clear()
        codec_key = self.codec_combo.currentData()
        if not codec_key: return
        for preset in CODECS[codec_key]["presets"]:
            self.preset_combo.addItem(preset, preset)
        index = self.preset_combo.findData(CODECS[codec_key]["preset_default"])
        if index >= 0: self.preset_combo.setCurrentIndex(index)

    def on_format_changed(self):
        self.update_codec_options()
        self.update_preset_options()
        self.on_codec_changed()

    def on_codec_changed(self):
        codec_key = self.codec_combo.currentData()
        if not codec_key: return
        self.update_preset_options()
        codec_details = CODECS.get(codec_key, CODECS[DEFAULT_CODEC_KEY])
        self.crf_slider.setRange(codec_details["crf_min"], codec_details["crf_max"])
        self.crf_slider.setValue(codec_details["crf_default"])
        self.on_crf_changed(codec_details["crf_default"])

    def on_preset_changed(self): pass
    def on_encoding_changed(self): pass

    def on_crf_changed(self, value):
        self.crf_label.setText("CRF: только VFR-fix (copy)" if value == self.crf_slider.minimum() else f"CRF: {value}")

    def check_vfr_status(self):
        if self.current_file:
            needs_fix = self._cached_info.get('needs_vfr_fix', False) if self._cached_info else False
            self.vfr_status_label.setText("Статус VFR: Рекомендуется!" if needs_fix else "Статус VFR: Не требуется")
            self.vfr_status_label.setStyleSheet("color: orange;" if needs_fix else "color: green;")

    def update_quality_test_tab(self, file_info):
        fps = file_info.get("fps", 0)
        duration = file_info.get("duration", 0)
        if fps > 0 and duration > 0:
            total_frames = int(duration * fps)
            self.quality_fps_label.setText(f"FPS видео: {fps:.3f}")
            self.quality_total_frames_label.setText(f"Всего кадров: ~{total_frames} (макс. номер: {total_frames - 1})")
            self.frame_number_spin.setRange(0, total_frames - 1)
            if self.quality_test_frame_number > total_frames - 1:
                self.quality_test_frame_number = total_frames - 1
            self.frame_number_spin.blockSignals(True)
            self.frame_number_spin.setValue(self.quality_test_frame_number)
            self.frame_number_spin.blockSignals(False)
            self.extract_frame_status.setText("")
        else:
            self.quality_fps_label.setText("FPS видео: —")
            self.quality_total_frames_label.setText("Всего кадров: —")
            self.frame_number_spin.setRange(0, 999999)
            self.extract_frame_status.setText("Невозможно определить количество кадров")

    def on_quality_test_frame_changed(self, value):
        self.quality_test_frame_number = value

    def extract_frame_action(self):
        if not self.current_file:
            QMessageBox.warning(self, "Ошибка", "Не выбран видеофайл.")
            return
        
        frame_number = self.frame_number_spin.value()
        video_name = os.path.splitext(os.path.basename(self.current_file))[0]
        codec = self._cached_info.get('video_codec', 'unknown')
        crf_val = self._cached_info.get('crf_value')
        crf_str = f"crf{int(crf_val)}" if crf_val is not None else "crfunknown"
        frame_filename = f"{video_name}{EXTRACTED_FRAME_SUFFIX}_{codec}_{crf_str}_frame{frame_number:06d}.jpg"
        output_path = os.path.join(os.path.dirname(self.current_file), frame_filename)
        
        self.extract_frame_status.setText("Извлечение кадра...")
        self.extract_frame_status.setStyleSheet("color: orange;")
        
        self.compression_worker = WorkerThread(
            self.processor, "extract_frame",
            input_path=self.current_file,
            frame_number=frame_number,
            output_path=output_path
        )
        self.compression_worker.progress_updated.connect(self.update_progress)
        self.compression_worker.finished.connect(self.on_extract_frame_finished)
        self.compression_worker.error_occurred.connect(self.on_extract_frame_error)
        self.active_workers.append(self.compression_worker)
        self.compression_worker.start()

    def on_extract_frame_finished(self, result):
        self.extract_frame_status.setText(f"Кадр сохранён: {os.path.basename(result)}")
        self.extract_frame_status.setStyleSheet("color: green;")
        QMessageBox.information(self, "Готово", f"Кадр успешно сохранён:\n{result}")

    def on_extract_frame_error(self, error):
        self.extract_frame_status.setText("Ошибка при извлечении кадра!")
        self.extract_frame_status.setStyleSheet("color: red;")
        QMessageBox.critical(self, "Ошибка", f"Не удалось извлечь кадр:\n{error}")

    def start_processing(self):
        if not self.current_file: return
        if not self.batch_in_progress:
            self.batch_in_progress = True
            self.total_files_in_batch = len(self.file_queue) + (1 if self.current_file else 0)
            self.completed_files_in_batch = 0
        self.processing_stopped = False
        self.compression_start_time = datetime.now()
        
        current_tab_text = self.operations_tabs.tabText(self.operations_tabs.currentIndex())
        params = {"input_path": self.current_file, "output_dir": self.output_directory}
        worker_mode = ""

        if current_tab_text == "Сжатие видео":
            worker_mode = "compress"
            params.update({
                "output_format": self.format_combo.currentData(), "codec": self.codec_combo.currentData(),
                "crf_value": self.crf_slider.value(), "preset_value": self.preset_combo.currentData(),
                "force_vfr_fix": self.vfr_checkbox.isChecked(), "use_hardware": self.hardware_radio.isChecked(),
            })
        elif current_tab_text == "Сокращение":
            worker_mode = "trim"
            params.update({"seconds": self.trim_seconds_spin.value(), "from_start": self.trim_from_start_radio.isChecked()})
        elif current_tab_text == "Починка громкости":
            worker_mode = "normalize_audio"
        elif current_tab_text == "Тест качества":
            worker_mode = "extract_frame"
            frame_number = self.frame_number_spin.value()
            video_name = os.path.splitext(os.path.basename(self.current_file))[0]
            codec = self._cached_info.get('video_codec', 'unknown')
            crf_val = self._cached_info.get('crf_value')
            crf_str = f"crf{int(crf_val)}" if crf_val is not None else "crfunknown"
            frame_filename = f"{video_name}{EXTRACTED_FRAME_SUFFIX}_{codec}_{crf_str}_frame{frame_number:06d}.jpg"
            output_dir = self.output_directory if self.output_directory else os.path.dirname(self.current_file)
            params["output_path"] = os.path.join(output_dir, frame_filename)
            params["frame_number"] = frame_number
            del params["output_dir"]

        self.set_ui_enabled(False)
        self.compression_worker = WorkerThread(self.processor, worker_mode, **params)
        self.compression_worker.progress_updated.connect(self.update_progress)
        self.compression_worker.finished.connect(self.on_finished)
        self.compression_worker.error_occurred.connect(self.on_error)
        self.active_workers.append(self.compression_worker)
        self.compression_worker.start()

    def cancel_processing(self):
        if QMessageBox.question(self, "Отмена", "Отменить процесс?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self.processing_stopped = True
            if self.compression_worker:
                self.compression_worker.stop()
                QTimer.singleShot(1000, self.on_canceled)

    def on_canceled(self):
        self.batch_test_in_progress = False
        self.files_to_test = []
        self.status_label.setText("Отменено")
        self.progress_bar.setValue(0)
        self.batch_in_progress = False
        self.current_file = self.current_info = None
        self.set_ui_enabled(True)
        self.file_label.setText("Перетащите файлы сюда или нажмите 'Выбрать'")

    def update_progress(self, value, message):
        if self.batch_in_progress and self.total_files_in_batch > 0:
            total_progress = int(((self.completed_files_in_batch + value / 100.0) / self.total_files_in_batch) * 100)
            self.progress_bar.setValue(total_progress)
            self.status_label.setText(f"Обработка ({value}%) | Общий: {total_progress}%")
        else:
            self.progress_bar.setValue(value)
            self.status_label.setText(message)

    def on_finished(self, result):
        if self.batch_in_progress: self.completed_files_in_batch += 1
        current_tab_text = self.operations_tabs.tabText(self.operations_tabs.currentIndex())
        if current_tab_text == "Тест качества":
            self.extract_frame_status.setText(f"Кадр сохранён: {os.path.basename(result)}")
            self.extract_frame_status.setStyleSheet("color: green;")
        if not self.processing_stopped: self.process_next_file()
        else: self.on_canceled()

    def on_error(self, error):
        self.status_label.setText("Ошибка при обработке!")
        current_tab_text = self.operations_tabs.tabText(self.operations_tabs.currentIndex())
        if current_tab_text == "Тест качества":
            self.extract_frame_status.setText("Ошибка при извлечении кадра!")
            self.extract_frame_status.setStyleSheet("color: red;")
        if self.batch_in_progress: self.completed_files_in_batch += 1
        if not self.processing_stopped: self.process_next_file()
        else: self.on_canceled()

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
                self.current_file = self.current_info = None
        self.update_queue_table()
        self.update_queue_label()
        if not self.current_file:
            self.batch_in_progress = False
            self.set_ui_enabled(True)
            self.file_label.setText("Перетащите файлы сюда или нажмите 'Выбрать'")
            self.status_label.setText("Готов к работе")
            self.progress_bar.setValue(0)

    def set_ui_enabled(self, enabled):
        self.select_file_btn.setEnabled(enabled)
        self.process_btn.setEnabled(enabled and self.current_file is not None)
        self.test_all_btn.setEnabled(enabled and self.current_file is not None)
        self.cancel_btn.setEnabled(not enabled and self.current_file is not None)
        self.cancel_btn.setVisible(not enabled and self.current_file is not None)
        self.operations_tabs.setEnabled(enabled)
        self.output_dir_btn.setEnabled(enabled)
        
        # Блокируем кнопки теста во время обработки
        for i in range(self.queue_table.rowCount()):
            widget = self.queue_table.cellWidget(i, 8)
            if widget:
                for child in widget.findChildren(QToolButton):
                    child.setEnabled(enabled)

    def log_slot(self, message):
        if hasattr(self, 'log_text'):
            self.log_text.append(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")

    def closeEvent(self, event):
        if self.compression_worker and self.compression_worker.isRunning():
            if QMessageBox.question(self, "Выход", "Идет обработка. Выйти?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
                self.compression_worker.stop()
                self.compression_worker.wait(2000)
                event.accept()
            else: event.ignore()
        else: event.accept()

def main():
    app = QApplication(sys.argv)
    processor = VideoProcessor()
    logging.info("--- Инфо ---")
    logging.info(processor.get_gpu_info())
    
    if not os.path.exists(get_actual_ffmpeg_path()) or not os.path.exists(get_ffprobe_path()):
        if not FFmpegDownloader().check_and_download(): return -1
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()