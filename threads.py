import subprocess
from PySide6.QtCore import QThread, Signal


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
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    # Если процесс не завершился, принудительно убиваем
                    self.process.kill()
                    # Даем время на принудительное завершение
                    try:
                        self.process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        # Если и это не помогло, пробуем завершить через taskkill (Windows)
                        import platform
                        if platform.system() == "Windows":
                            import os
                            os.system(f"taskkill /F /T /PID {self.process.pid}")
            except Exception:
                # Игнорируем другие ошибки при остановке
                pass