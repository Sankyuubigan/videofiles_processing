import sys
import os
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                               QHBoxLayout, QPushButton, QLabel, QFileDialog,
                               QProgressBar, QTextEdit, QGroupBox,
                               QMessageBox, QComboBox, QCheckBox, QSlider,
                               QDialog, QTextBrowser, QRadioButton, QButtonGroup,
                               QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QFont, QDragEnterEvent, QDropEvent
from config import (OUTPUT_FORMATS, CODECS, DEFAULT_OUTPUT_FORMAT_KEY, DEFAULT_CODEC_KEY,
                   DEFAULT_USE_HARDWARE_ENCODING)
from video_processor import VideoProcessor
from ffmpeg_downloader import FFmpegDownloader


class VideoInfoDialog(QDialog):
    def __init__(self, video_info, parent=None):
        super().__init__(parent)
        self.video_info = video_info
        self.setWindowTitle("Информация о видео")
        self.setModal(True)
        self.resize(500, 400)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()
        title = QLabel("Информация о файле")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)
        info_text = QTextBrowser()
        audio_info = ""
        audio_tracks = self.video_info.get('audio_tracks', [])
        if audio_tracks:
            audio_info = f"<b>Аудиодорожки:</b> {len(audio_tracks)}<br>"
            for i, track in enumerate(audio_tracks):
                lang = track.get('language', 'und')
                title_str = track.get('title', f'Audio {i+1}')
                channels = track.get('channels', 0)
                audio_info += f"&nbsp;&nbsp;• {title_str} ({lang}, {channels}ch)<br>"
        else:
            audio_info = "<b>Аудиодорожки:</b> Не найдены<br>"
        
        needs_vfr_text = "Да" if self.video_info.get('needs_vfr_fix') else "Нет"
        
        info_html = f"""
        <b>Путь:</b> {self.video_info.get('path', 'N/A')}<br>
        <b>Размер:</b> {self.video_info.get('size_mb', 0):.2f} МБ<br>
        <b>Длительность:</b> {self.video_info.get('duration', 0):.2f} сек<br>
        <b>Разрешение:</b> {self.video_info.get('width', 0)}x{self.video_info.get('height', 0)}<br>
        <b>FPS:</b> {self.video_info.get('fps', 0):.2f}<br>
        <b>Битрейт видео:</b> {self.video_info.get('video_bitrate', 0) // 1000} кбит/с<br>
        <b>Битрейт аудио:</b> {self.video_info.get('audio_bitrate', 0) // 1000} кбит/с<br>
        <b>Требуется VFR fix:</b> {needs_vfr_text}<br>
        <b>Примерный размер после сжатия:</b> {self.video_info.get('estimated_size_mb', 0):.2f} МБ<br>
        {audio_info}
        <b>GPU:</b> {self.video_info.get('gpu_info', 'N/A')}<br>
        <b>Режим обработки:</b> {self.video_info.get('processing_mode', 'N/A')}
        """
        info_text.setHtml(info_html)
        layout.addWidget(info_text)
        close_btn = QPushButton("Закрыть")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)
        self.setLayout(layout)


class WorkerThread(QThread):
    progress_updated = Signal(int, str)
    finished = Signal(str)
    error_occurred = Signal(str)
    info_ready = Signal(dict)

    def __init__(self, processor, mode, **kwargs):
        super().__init__()
        self.processor = processor
        self.mode = mode
        self.kwargs = kwargs
        self.process = None

    def run(self):
        try:
            if self.mode == 'info':
                info = self.processor.get_video_info(self.kwargs['input_path'])
                if "error" in info:
                    self.error_occurred.emit(info["error"])
                else:
                    self.info_ready.emit(info)
            elif self.mode == 'compress':
                result = self.processor.compress_video(
                    progress_callback=self.progress_updated.emit,
                    process_setter=self.set_process,
                    **self.kwargs
                )
                self.finished.emit(result)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.error_occurred.emit(str(e))
    
    def set_process(self, process):
        """Сохраняет ссылку на процесс FFmpeg для возможности остановки"""
        self.process = process
    
    def stop(self):
        """Останавливает процесс сжатия"""
        if self.process:
            try:
                self.process.terminate()
                # Даем процессу время на завершение
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                # Если процесс не завершился, принудительно убиваем
                self.process.kill()
            except Exception:
                # Игнорируем другие ошибки при остановке
                pass


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
        file_select_layout.addWidget(self.select_file_btn)
        file_select_layout.addWidget(self.info_btn)
        file_select_layout.addStretch()
        file_layout.addLayout(file_select_layout)
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
        # Не запускаем обработку первого файла сразу, даем пользователю увидеть все файлы в очереди
        self.update_queue_label()

    def add_file_to_queue(self, file_path):
        if os.path.isfile(file_path):
            # Получаем информацию о файле
            info = self.processor.get_video_info(file_path)
            if "error" not in info:
                self.file_queue.append((file_path, info))
                self.update_queue_table()
                self.update_queue_label()
                print(f"Файл добавлен в очередь: {file_path}")
                
                # Если это первый файл и нет текущего файла, устанавливаем его как текущий
                if len(self.file_queue) == 1 and self.current_file is None:
                    self.current_file, self.current_info = self.file_queue[0]
                    self.set_current_file(self.current_file, self.current_info)

    def update_queue_table(self):
        print(f"Обновление таблицы, файлов в очереди: {len(self.file_queue)}")
        self.queue_table.setRowCount(len(self.file_queue))
        
        # Получаем текущие настройки для расчета размера
        crf_value = self.crf_slider.value()
        codec = self.current_codec()
        use_hardware = self.hardware_radio.isChecked()
        force_vfr_fix = self.vfr_checkbox.isChecked()
        
        for row, (file_path, info) in enumerate(self.file_queue):
            print(f"Добавление в таблицу: {os.path.basename(file_path)}")
            # Имя файла
            file_name_item = QTableWidgetItem(os.path.basename(file_path))
            self.queue_table.setItem(row, 0, file_name_item)
            
            # Размер файла
            size_mb = info.get("size_mb", 0)
            size_item = QTableWidgetItem(f"{size_mb:.1f} МБ")
            self.queue_table.setItem(row, 1, size_item)
            
            # Статус VFR
            needs_vfr = info.get("needs_vfr_fix", False)
            vfr_text = "Требуется" if needs_vfr else "Не требуется"
            vfr_item = QTableWidgetItem(vfr_text)
            if needs_vfr:
                vfr_item.setForeground(Qt.GlobalColor.red)
            else:
                vfr_item.setForeground(Qt.GlobalColor.darkGreen)
            self.queue_table.setItem(row, 2, vfr_item)
            
            # Примерный размер после сжатия с учетом текущих настроек
            est_size = self.processor.estimated_size_mb(
                video_bitrate=info.get("video_bitrate", 0),
                audio_bitrate=info.get("audio_bitrate", 128000),
                duration=info["duration"],
                crf=crf_value,
                codec=codec,
                needs_vfr_fix=needs_vfr or force_vfr_fix,
                use_hardware=use_hardware
            )
            print(f"[DEBUG] Таблица: Расчетный размер для {os.path.basename(file_path)}: {est_size:.2f} МБ (CRF={crf_value})")
            est_item = QTableWidgetItem(f"{est_size:.1f} МБ")
            self.queue_table.setItem(row, 3, est_item)
        
        # Принудительно обновляем отображение таблицы
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
            # Не запускаем обработку первого файла сразу

    def set_current_file(self, file_path, file_info):
        self.file_label.setText(f"Текущий файл: {os.path.basename(file_path)}")
        self.process_btn.setEnabled(True)
        self.info_btn.setEnabled(True)
        self._cached_info = file_info
        self.check_vfr_status()
        self.update_estimated_size(self.crf_slider.value(), self.current_codec())

    def current_codec(self):
        return self.codec_combo.currentData()

    def update_codec_options(self):
        """Обновляет список доступных кодеков на основе выбранного формата."""
        self.codec_combo.clear()
        current_format = self.format_combo.currentData()
        compatible_codecs = OUTPUT_FORMATS[current_format]["compatible_codecs"]
        
        for codec_key in compatible_codecs:
            codec_name = CODECS[codec_key]["name"]
            self.codec_combo.addItem(codec_name, codec_key)
        
        # Устанавливаем кодек по умолчанию для текущего формата
        default_codec = OUTPUT_FORMATS[current_format]["default_codec"]
        index = self.codec_combo.findData(default_codec)
        if index >= 0:
            self.codec_combo.setCurrentIndex(index)

    def on_format_changed(self):
        # Обновляем список доступных кодеков
        self.update_codec_options()
        
        # Обновляем настройки CRF
        codec_key = self.codec_combo.currentData()
        codec_details = CODECS.get(codec_key, CODECS[DEFAULT_CODEC_KEY])
        self.crf_slider.setRange(codec_details["crf_min"], codec_details["crf_max"])
        self.crf_slider.setValue(codec_details["crf_default"])
        self.on_crf_changed(codec_details["crf_default"])
        self.update_estimated_size(self.crf_slider.value(), codec_key)
        # Обновляем таблицу при изменении формата
        self.update_queue_table()

    def on_codec_changed(self):
        # Обновляем настройки CRF при изменении кодека
        codec_key = self.codec_combo.currentData()
        codec_details = CODECS.get(codec_key, CODECS[DEFAULT_CODEC_KEY])
        self.crf_slider.setRange(codec_details["crf_min"], codec_details["crf_max"])
        self.crf_slider.setValue(codec_details["crf_default"])
        self.on_crf_changed(codec_details["crf_default"])
        self.update_estimated_size(self.crf_slider.value(), codec_key)
        # Обновляем таблицу при изменении кодека
        self.update_queue_table()

    def on_encoding_changed(self):
        self.update_estimated_size(self.crf_slider.value(), self.current_codec())
        # Обновляем таблицу при изменении типа кодирования
        self.update_queue_table()

    def on_crf_changed(self, value):
        if value == self.crf_slider.minimum():
            self.crf_label.setText("CRF: только VFR-fix (copy)")
        else:
            self.crf_label.setText(f"CRF: {value}")
        self.update_estimated_size(value, self.current_codec())
        # Обновляем таблицу при изменении CRF
        self.update_queue_table()

    def update_estimated_size(self, crf, codec):
        if not self.current_file:
            self.estimated_label.setText("Примерный размер после сжатия: —")
            return
        
        # Используем кэшированную информацию
        info = self._cached_info if self._cached_info else None
        
        if info is None:
            return

        # Используем новые поля video_bitrate и audio_bitrate
        est = self.processor.estimated_size_mb(
            video_bitrate=info.get("video_bitrate", 0),
            audio_bitrate=info.get("audio_bitrate", 128000),
            duration=info["duration"],
            crf=crf,
            codec=codec,
            needs_vfr_fix=info.get('needs_vfr_fix', False) or self.vfr_checkbox.isChecked(),
            use_hardware=self.hardware_radio.isChecked()
        )
        print(f"[DEBUG] Текущий файл: Расчетный размер: {est:.2f} МБ (CRF={crf})")

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
        
        # Сбрасываем флаг остановки при начале новой обработки
        self.processing_stopped = False
        
        params = {
            "input_path": self.current_file,
            "output_format": self.format_combo.currentData(),
            "codec": self.codec_combo.currentData(),
            "crf_value": self.crf_slider.value(),
            "force_vfr_fix": self.vfr_checkbox.isChecked(),
            "use_hardware": self.hardware_radio.isChecked()
        }
        self.set_ui_enabled(False)
        self.run_compression_worker(**params)

    def cancel_processing(self):
        # Показываем диалог подтверждения
        reply = QMessageBox.question(
            self, "Подтверждение отмены",
            "Вы уверены, что хотите отменить процесс сжатия и всю очередь?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # Устанавливаем флаг остановки всей очереди
            self.processing_stopped = True
            if self.compression_worker:
                self.log_text.append("Отмена процесса сжатия и всей очереди...")
                self.status_label.setText("Отмена процесса...")
                self.compression_worker.stop()
                # Небольшая задержка, чтобы процесс успел завершиться
                QTimer.singleShot(1000, self.on_canceled)

    def on_canceled(self):
        self.log_text.append("Процесс сжатия и обработка очереди отменены пользователем")
        self.status_label.setText("Отменено пользователем")
        self.progress_bar.setValue(0)
        
        # Возвращаем интерфейс в исходное состояние
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
        self.progress_bar.setValue(value)
        self.status_label.setText(message)
        # Не добавляем сообщения о прогрессе в лог, только важные события

    def on_finished(self, result):
        self.log_text.append(f"Готово: {result}")
        # Проверяем, не был ли процесс остановлен
        if not self.processing_stopped:
            self.process_next_file()
        else:
            # Если процесс был остановлен, не продолжаем обработку очереди
            self.on_canceled()

    def on_error(self, error):
        self.log_text.append(f"ОШИБКА: {error}")
        self.status_label.setText("Ошибка при обработке!")
        if self.sender() == self.compression_worker:
            self.compression_worker = None
        # Проверяем, не был ли процесс остановлен
        if not self.processing_stopped:
            self.process_next_file()
        else:
            # Если процесс был остановлен, не продолжаем обработку очереди
            self.on_canceled()

    def process_next_file(self):
        # Проверяем, не был ли процесс остановлен
        if self.processing_stopped:
            self.on_canceled()
            return
            
        # Удаляем обработанный файл из очереди
        if self.current_file:
            # Ищем и удаляем текущий файл из очереди
            self.file_queue = [(path, info) for path, info in self.file_queue if path != self.current_file]
            self.update_queue_table()
        
        self.update_queue_label()
        if self.file_queue:
            self.current_file, self.current_info = self.file_queue[0]
            self.set_current_file(self.current_file, self.current_info)
            QTimer.singleShot(500, self.start_processing)
        else:
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
        self.crf_slider.setEnabled(enabled)
        self.vfr_checkbox.setEnabled(enabled)
        self.hardware_radio.setEnabled(enabled)
        self.software_radio.setEnabled(enabled)

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