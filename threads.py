import subprocess
from PySide6.QtCore import QThread, Signal


class WorkerThread(QThread):
    progress_updated = Signal(int, str)
    finished = Signal(object)  # Изменено на object, чтобы передавать словари
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
            elif self.mode == 'trim':
                result = self.processor.trim_video(
                    progress_callback=self.progress_updated.emit,
                    process_setter=self.set_process,
                    **self.kwargs
                )
                self.finished.emit(result)
            elif self.mode == 'normalize_audio':
                result = self.processor.normalize_audio_volume(
                    progress_callback=self.progress_updated.emit,
                    process_setter=self.set_process,
                    **self.kwargs
                )
                self.finished.emit(result)
            elif self.mode == 'extract_frame':
                result = self.processor.extract_frame(
                    process_setter=self.set_process,
                    **self.kwargs
                )
                self.finished.emit(result)
            elif self.mode == 'chunk_test':
                result = self.processor.run_chunk_test(
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
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    try:
                        self.process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        import platform
                        if platform.system() == "Windows":
                            import os
                            os.system(f"taskkill /F /T /PID {self.process.pid}")
            except Exception:
                pass