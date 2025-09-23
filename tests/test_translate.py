import sys
import os
import shutil
import subprocess
from pathlib import Path
from PySide6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, 
                               QWidget, QPushButton, QLabel, QFileDialog, 
                               QProgressBar, QTextEdit, QSpinBox, QGroupBox, QMessageBox)
from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtGui import QFont
import time
import uuid

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

    def is_file_locked(self, filepath):
        """Проверка, заблокирован ли файл"""
        try:
            # Пытаемся открыть файл в режиме записи
            with open(filepath, 'a') as f:
                pass
            return False
        except IOError:
            return True

    def wait_for_file_unlock(self, filepath, timeout=10):
        """Ждать разблокировки файла"""
        self.debug_info.emit(f"Ожидание разблокировки файла: {filepath}")
        for i in range(timeout):
            if not self.is_file_locked(filepath):
                self.debug_info.emit(f"Файл разблокирован через {i} секунд")
                return True
            time.sleep(1)
        return False

    def find_vot_cli(self):
        """Поиск vot-cli в системе"""
        self.debug_info.emit("Поиск vot-cli в системе...")
        
        # Способ 1: Проверка vot-cli как команды
        try:
            result = subprocess.run(['vot-cli', '--version'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                self.debug_info.emit(f"Найден vot-cli как команда: {result.stdout.strip()}")
                return ['vot-cli']
        except:
            self.debug_info.emit("vot-cli как команда не найден")
        
        # Способ 2: Проверка python -m vot_cli
        try:
            result = subprocess.run([sys.executable, '-m', 'vot_cli', '--version'], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                self.debug_info.emit(f"Найден vot-cli как модуль: {result.stdout.strip()}")
                return [sys.executable, '-m', 'vot_cli']
        except:
            self.debug_info.emit("vot-cli как модуль не найден")
        
        # Способ 3: Поиск в PATH (исправлено для Windows)
        try:
            result = subprocess.run(['where', 'vot-cli'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                # Берем первую строку вывода
                vot_path = result.stdout.strip().split('\n')[0]
                self.debug_info.emit(f"Найден vot-cli в PATH: {vot_path}")
                
                # Проверяем различные расширения для Windows
                path_obj = Path(vot_path)
                possible_extensions = ['.cmd', '.bat', '.exe', '']
                
                for ext in possible_extensions:
                    test_path = path_obj.with_suffix(ext) if ext else path_obj
                    if test_path.exists():
                        self.debug_info.emit(f"Найден исполняемый файл: {test_path}")
                        # Для .cmd и .bat файлов запускаем через cmd.exe
                        if ext in ['.cmd', '.bat']:
                            return ['cmd', '/c', str(test_path)]
                        return [str(test_path)]
                
                # Если ни один из вариантов не найден, пробуем искать в родительской директории
                parent_dir = path_obj.parent
                for ext in possible_extensions:
                    test_path = parent_dir / f"{path_obj.name}{ext}"
                    if test_path.exists():
                        self.debug_info.emit(f"Найден исполняемый файл: {test_path}")
                        # Для .cmd и .bat файлов запускаем через cmd.exe
                        if ext in ['.cmd', '.bat']:
                            return ['cmd', '/c', str(test_path)]
                        return [str(test_path)]
                
                # Если ничего не найдено, используем оригинальный путь через cmd
                return ['cmd', '/c', vot_path]
        except Exception as e:
            self.debug_info.emit(f"Ошибка при поиске в PATH: {e}")
        
        # Способ 4: Поиск в папках Python
        python_scripts = Path(sys.executable).parent / 'Scripts'
        possible_names = ['vot-cli.exe', 'vot-cli.cmd', 'vot-cli.bat', 'vot-cli']
        
        for name in possible_names:
            vot_file = python_scripts / name
            if vot_file.exists():
                self.debug_info.emit(f"Найден vot-cli в Scripts: {vot_file}")
                # Для .cmd и .bat файлов запускаем через cmd.exe
                if name.endswith(('.cmd', '.bat')):
                    return ['cmd', '/c', str(vot_file)]
                return [str(vot_file)]
        
        # Способ 5: Поиск в AppData\npm (типичное место для npm на Windows)
        npm_global = Path(os.environ.get('APPDATA', '')) / 'npm'
        if npm_global.exists():
            possible_names = ['vot-cli.exe', 'vot-cli.cmd', 'vot-cli.bat', 'vot-cli']
            for name in possible_names:
                vot_file = npm_global / name
                if vot_file.exists():
                    self.debug_info.emit(f"Найден vot-cli в npm global: {vot_file}")
                    # Для .cmd и .bat файлов запускаем через cmd.exe
                    if name.endswith(('.cmd', '.bat')):
                        return ['cmd', '/c', str(vot_file)]
                    return [str(vot_file)]
        
        # Способ 6: Прямой поиск в AppData\npm с проверкой расширений
        npm_global = Path(os.environ.get('APPDATA', '')) / 'npm'
        if npm_global.exists():
            vot_cmd = npm_global / 'vot-cli.cmd'
            if vot_cmd.exists():
                self.debug_info.emit(f"Найден vot-cli.cmd в npm global: {vot_cmd}")
                return ['cmd', '/c', str(vot_cmd)]
            
            vot_bat = npm_global / 'vot-cli.bat'
            if vot_bat.exists():
                self.debug_info.emit(f"Найден vot-cli.bat в npm global: {vot_bat}")
                return ['cmd', '/c', str(vot_bat)]
            
            vot_exe = npm_global / 'vot-cli.exe'
            if vot_exe.exists():
                self.debug_info.emit(f"Найден vot-cli.exe в npm global: {vot_exe}")
                return [str(vot_exe)]
        
        self.debug_info.emit("vot-cli не найден ни в одном из мест")
        return None

    def run(self):
        temp_dir = None
        working_video_path = None
        try:
            temp_dir = Path('./temp')
            temp_audio_dir = temp_dir / 'audio'
            
            self.progress_updated.emit(10, "Создание временных директорий...")
            temp_dir.mkdir(exist_ok=True)
            temp_audio_dir.mkdir(exist_ok=True)
            
            # Копируем видеофайл с уникальным именем
            self.progress_updated.emit(20, "Копирование видеофайла...")
            unique_id = str(uuid.uuid4())[:8]
            safe_filename = f"original_video_{unique_id}.mp4"
            working_video_path = Path.cwd() / safe_filename
            
            self.debug_info.emit(f"Копирование в: {working_video_path}")
            
            # Проверяем, не заблокирован ли исходный файл
            if self.is_file_locked(self.video_path):
                self.debug_info.emit("Исходный файл заблокирован, ожидаем...")
                if not self.wait_for_file_unlock(self.video_path):
                    raise Exception("Не удалось дождаться разблокировки исходного файла")
            
            shutil.copy2(self.video_path, working_video_path)
            self.debug_info.emit(f"Файл успешно скопирован")
            
            # Находим vot-cli
            self.progress_updated.emit(30, "Поиск vot-cli...")
            vot_cmd = self.find_vot_cli()
            
            if not vot_cmd:
                raise Exception("""vot-cli не найден! Установите его:
1. Откройте командную строку
2. Выполните: npm install -g vot-cli
3. Или нажмите кнопку "Установить vot-cli" в интерфейсе""")
            
            # Переводим аудио через vot-cli
            self.progress_updated.emit(40, "Начинаем перевод аудио...")
            cmd = vot_cmd + [self.video_link, '--output', str(temp_audio_dir)]
            self.debug_info.emit(f"Выполняем команду: {' '.join(cmd)}")
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            if result.returncode != 0:
                self.debug_info.emit(f"Ошибка vot-cli: {result.stderr}")
                raise Exception(f"vot-cli завершился с ошибкой: {result.stderr}")
            
            self.debug_info.emit(f"vot-cli stdout: {result.stdout}")
            
            # Проверяем, есть ли переведенные файлы
            audio_files = list(temp_audio_dir.glob('*'))
            if not audio_files:
                raise Exception("Переведенные аудиофайлы не найдены")
            
            self.debug_info.emit(f"Найдены аудиофайлы: {[f.name for f in audio_files]}")
            
            # Микширование звука через ffmpeg
            self.progress_updated.emit(70, "Микширование аудио...")
            # Используем первый найденный аудиофайл вместо маски
            audio_path = str(audio_files[0])
            self.debug_info.emit(f"Используем аудиофайл: {audio_path}")
            output_filename = "translated_video.mp4"
            
            # Проверяем наличие ffmpeg
            try:
                subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True, timeout=5)
            except:
                raise Exception("ffmpeg не найден. Установите его и добавьте в PATH")
            
            ffmpeg_cmd = [
                'ffmpeg',
                '-i', str(working_video_path),
                '-i', audio_path,  # Используем конкретный файл вместо маски
                '-c:v', 'copy',
                '-filter_complex', 
                f'[0:a] volume={self.volume_ratio} [original]; [original][1:a] amix=inputs=2:duration=longest [audio_out]',
                '-map', '0:v',
                '-map', '[audio_out]',
                '-y', output_filename
            ]
            
            self.debug_info.emit(f"Выполняем ffmpeg: {' '.join(ffmpeg_cmd)}")
            subprocess.run(ffmpeg_cmd, check=True, capture_output=True, text=True, timeout=300)
            
            self.progress_updated.emit(90, "Очистка временных файлов...")
            
            # Удаляем скопированный видеофайл
            if working_video_path.exists():
                try:
                    working_video_path.unlink()
                    self.debug_info.emit("Временный видеофайл удален")
                except Exception as e:
                    self.debug_info.emit(f"Не удалось удалить временный файл: {e}")
            
            # Чистим временные файлы
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
            
            self.progress_updated.emit(100, "Готово!")
            self.finished.emit(output_filename)
            
        except subprocess.TimeoutExpired:
            self.error_occurred.emit("Превышено время выполнения команды")
        except subprocess.CalledProcessError as e:
            error_msg = f"Ошибка выполнения команды: {e}\nStdout: {e.stdout}\nStderr: {e.stderr}"
            self.error_occurred.emit(error_msg)
        except Exception as e:
            self.error_occurred.emit(str(e))
        finally:
            # Чистим временные файлы при ошибке
            if temp_dir and temp_dir.exists():
                try:
                    shutil.rmtree(temp_dir)
                except:
                    pass
            # Удаляем рабочий видеофайл, если он остался
            if working_video_path and working_video_path.exists():
                try:
                    working_video_path.unlink()
                except:
                    pass

class VideoTranslatorGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.video_path = None
        self.initUI()
    
    def initUI(self):
        self.setWindowTitle("Video Translator")
        self.setGeometry(100, 100, 800, 700)
        
        # Центральный виджет
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # Группа настроек
        settings_group = QGroupBox("Настройки")
        settings_layout = QVBoxLayout()
        
        # Выбор файла
        file_layout = QHBoxLayout()
        self.file_label = QLabel("Файл не выбран")
        self.file_label.setWordWrap(True)
        self.select_file_btn = QPushButton("Выбрать видеофайл")
        self.select_file_btn.clicked.connect(self.select_file)
        file_layout.addWidget(self.file_label)
        file_layout.addWidget(self.select_file_btn)
        
        # Громкость
        volume_layout = QHBoxLayout()
        volume_layout.addWidget(QLabel("Громкость оригинала:"))
        self.volume_spinbox = QSpinBox()
        self.volume_spinbox.setRange(0, 100)
        self.volume_spinbox.setValue(30)
        self.volume_spinbox.setSuffix("%")
        volume_layout.addWidget(self.volume_spinbox)
        volume_layout.addStretch()
        
        # Ссылка на YouTube
        self.link_label = QLabel("YouTube ссылка:")
        self.link_edit = QTextEdit()
        self.link_edit.setMaximumHeight(60)
        self.link_edit.setPlainText("https://www.youtube.com/watch?v=cizQ70wYZyw")
        
        settings_layout.addLayout(file_layout)
        settings_layout.addLayout(volume_layout)
        settings_layout.addWidget(self.link_label)
        settings_layout.addWidget(self.link_edit)
        settings_group.setLayout(settings_layout)
        
        # Прогресс бар
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        
        # Статус
        self.status_label = QLabel("Готов к работе")
        self.status_label.setAlignment(Qt.AlignCenter)
        
        # Кнопка запуска
        self.start_btn = QPushButton("Начать обработку")
        self.start_btn.clicked.connect(self.start_processing)
        self.start_btn.setEnabled(False)
        
        # Кнопки установки
        install_layout = QHBoxLayout()
        self.install_vot_btn = QPushButton("Установить vot-cli")
        self.install_vot_btn.clicked.connect(self.install_vot_cli)
        self.install_ffmpeg_btn = QPushButton("Установить ffmpeg")
        self.install_ffmpeg_btn.clicked.connect(self.install_ffmpeg)
        self.check_deps_btn = QPushButton("Проверить зависимости")
        self.check_deps_btn.clicked.connect(self.check_dependencies)
        install_layout.addWidget(self.install_vot_btn)
        install_layout.addWidget(self.install_ffmpeg_btn)
        install_layout.addWidget(self.check_deps_btn)
        
        # Лог
        log_group = QGroupBox("Лог и отладка")
        log_layout = QVBoxLayout()
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        log_layout.addWidget(self.log_text)
        log_group.setLayout(log_layout)
        
        # Добавляем всё в основной layout
        layout.addWidget(settings_group)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.status_label)
        layout.addWidget(self.start_btn)
        layout.addLayout(install_layout)
        layout.addWidget(log_group)
        
        # Шрифты
        font = QFont()
        font.setPointSize(10)
        self.file_label.setFont(font)
        self.status_label.setFont(font)
        self.start_btn.setFont(font)
        
        # Поток для обработки
        self.worker_thread = None
    
    def select_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, 
            "Выберите видеофайл", 
            "", 
            "Video files (*.mp4 *.avi *.mkv *.mov *.webm)"
        )
        
        if file_path:
            self.video_path = Path(file_path)
            
            # Проверяем, не является ли файл временным от предыдущего запуска
            if self.video_path.name.startswith('original_video_') and self.video_path.name.endswith('.mp4'):
                QMessageBox.warning(self, "Внимание", 
                                  "Вы выбрали временный файл от предыдущего запуска.\n"
                                  "Пожалуйста, выберите исходный видеофайл.")
                return
            
            self.file_label.setText(f"Файл: {self.video_path.name}")
            self.start_btn.setEnabled(True)
            self.log_message(f"Выбран файл: {self.video_path}")
    
    def install_vot_cli(self):
        try:
            self.log_message("Установка vot-cli...")
            # Исправляем команду установки для npm
            result = subprocess.run(['npm', 'install', '-g', 'vot-cli'], 
                                  capture_output=True, text=True)
            if result.returncode == 0:
                self.log_message("vot-cli успешно установлен!")
                QMessageBox.information(self, "Успех", "vot-cli успешно установлен!")
            else:
                self.log_message(f"Ошибка установки: {result.stderr}")
                QMessageBox.critical(self, "Ошибка", f"Не удалось установить vot-cli: {result.stderr}")
        except Exception as e:
            self.log_message(f"Ошибка установки vot-cli: {e}")
            QMessageBox.critical(self, "Ошибка", f"Не удалось установить vot-cli: {e}")
    
    def install_ffmpeg(self):
        self.log_message("Для установки ffmpeg скачайте его с https://ffmpeg.org/download.html")
        self.log_message("Или используйте менеджер пакетов:")
        self.log_message("winget install ffmpeg")
        self.log_message("choco install ffmpeg")
        QMessageBox.information(self, "Установка ffmpeg", 
                               "Скачайте ffmpeg с https://ffmpeg.org/download.html\n"
                               "Или установите через winget: winget install ffmpeg")
    
    def check_dependencies(self):
        self.log_message("=== Проверка зависимостей ===")
        
        # Проверка vot-cli
        self.log_message("Проверка vot-cli...")
        try:
            result = subprocess.run(['vot-cli', '--version'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                self.log_message(f"✓ vot-cli найден: {result.stdout.strip()}")
            else:
                self.log_message(f"✗ vot-cli ошибка: {result.stderr}")
        except:
            self.log_message("✗ vot-cli не найден как команда")
        
        try:
            result = subprocess.run([sys.executable, '-m', 'vot_cli', '--version'], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                self.log_message(f"✓ vot-cli найден как модуль: {result.stdout.strip()}")
            else:
                self.log_message(f"✗ vot-cli модуль ошибка: {result.stderr}")
        except:
            self.log_message("✗ vot-cli не найден как модуль")
        
        # Проверка ffmpeg
        self.log_message("Проверка ffmpeg...")
        try:
            result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                version = result.stdout.split('\n')[0]
                self.log_message(f"✓ ffmpeg найден: {version}")
            else:
                self.log_message(f"✗ ffmpeg ошибка: {result.stderr}")
        except:
            self.log_message("✗ ffmpeg не найден")
        
        self.log_message("=== Конец проверки ===")
    
    def start_processing(self):
        if not self.video_path:
            self.log_message("Ошибка: Файл не выбран!")
            return
            
        if not self.video_path.exists():
            self.log_message(f"Ошибка: Файл не найден: {self.video_path}")
            return
        
        video_link = self.link_edit.toPlainText().strip()
        if not video_link:
            self.log_message("Ошибка: Укажите ссылку на YouTube!")
            return
        
        volume_ratio = self.volume_spinbox.value() / 100.0
        
        # Блокируем кнопки
        self.start_btn.setEnabled(False)
        self.select_file_btn.setEnabled(False)
        self.progress_bar.setValue(0)
        self.status_label.setText("Начинаем обработку...")
        
        self.log_message("Начинаем обработку...")
        
        # Создаем и запускаем поток
        self.worker_thread = WorkerThread(self.video_path, video_link, volume_ratio)
        self.worker_thread.progress_updated.connect(self.update_progress)
        self.worker_thread.finished.connect(self.processing_finished)
        self.worker_thread.error_occurred.connect(self.processing_error)
        self.worker_thread.debug_info.connect(self.log_message)
        self.worker_thread.start()
    
    def update_progress(self, value, message):
        self.progress_bar.setValue(value)
        self.status_label.setText(message)
        self.log_message(message)
    
    def processing_finished(self, output_file):
        self.log_message(f"Готово! Результат: {output_file}")
        self.status_label.setText("Обработка завершена!")
        QMessageBox.information(self, "Успех", f"Видео успешно обработано!\nРезультат: {output_file}")
        
        # Разблокируем кнопки
        self.start_btn.setEnabled(True)
        self.select_file_btn.setEnabled(True)
    
    def processing_error(self, error_message):
        self.log_message(f"ОШИБКА: {error_message}")
        self.status_label.setText("Произошла ошибка!")
        self.progress_bar.setValue(0)  # Сбрасываем прогрессбар
        QMessageBox.critical(self, "Ошибка", f"Произошла ошибка:\n{error_message}")
        
        # Разблокируем кнопки
        self.start_btn.setEnabled(True)
        self.select_file_btn.setEnabled(True)
    
    def log_message(self, message):
        self.log_text.append(message)
        # Прокручиваем вниз
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    
    def closeEvent(self, event):
        # Если поток работает, ждем его завершения
        if self.worker_thread and self.worker_thread.isRunning():
            self.worker_thread.quit()
            self.worker_thread.wait()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = VideoTranslatorGUI()
    window.show()
    sys.exit(app.exec())