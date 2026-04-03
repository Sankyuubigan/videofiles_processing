import os
import subprocess
import logging
from typing import Optional, Callable

class FFmpegEditMixin:
    def trim_video_core(self, input_path: str, output_path: str, start_time: float, duration: float, 
                        progress_callback: Optional[Callable], total_duration_for_progress: float,
                        process_setter: Optional[Callable] = None) -> tuple[bool, str]:
        cmd =[self.ffmpeg_path, "-y", "-ss", str(start_time), "-i", input_path, "-t", str(duration)]
        cmd.extend(["-c:v", "libx264", "-crf", "23", "-preset", "medium", "-c:a", "aac", "-b:a", "192k"])
        cmd.extend(["-progress", "pipe:1", output_path])
        return self._run_command_with_progress(cmd, progress_callback, duration, "Сокращение", process_setter)

    def normalize_audio_volume(self, input_path: str, output_path: str,
                                progress_callback: Optional[Callable] = None,
                                process_setter: Optional[Callable] = None) -> tuple[bool, str]:
        cmd =[
            self.ffmpeg_path, "-y", "-i", input_path,
            "-af", "dynaudnorm=f=150:m=100:s=12:g=15,loudnorm=I=-16:LRA=11:TP=-1.5",
            "-c:v", "copy", "-progress", "pipe:1", output_path
        ]
        video_info = self.get_video_info(input_path)
        duration = video_info.get("duration", 0)
        return self._run_command_with_progress(cmd, progress_callback, duration, "Нормализация громкости", process_setter)

    def extract_frame(self, input_path: str, output_path: str, frame_number: int,
                      fps: float, process_setter: Optional[Callable] = None) -> tuple[bool, str]:
        """
        Извлекает конкретный кадр из видео и сохраняет как изображение.
        
        Args:
            input_path: Путь к видеофайлу.
            output_path: Путь для сохранения изображения.
            frame_number: Номер кадра (начиная с 0).
            fps: Частота кадров видео.
            process_setter: Колбэк для установки ссылки на процесс.
        """
        # Нормализуем пути: заменяем все разделители на нативные для ОС
        input_path = os.path.normpath(input_path)
        output_path = os.path.normpath(output_path)
        logging.info(f"Извлечение кадра #{frame_number} из {input_path} -> {output_path}")
        
        # Вычисляем время кадра в секундах
        timestamp = frame_number / fps
        logging.debug(f"Кадр #{frame_number} при fps={fps} соответствует timestamp={timestamp:.6f} сек")
        
        # -ss перед -i для быстрого поиска, -frames:v 1 для одного кадра, -update 1 для одиночного изображения
        cmd = [
            self.ffmpeg_path, "-y",
            "-ss", str(timestamp),
            "-i", input_path,
            "-frames:v", "1",
            "-update", "1",
            "-q:v", "2",  # Высокое качество JPEG (2 — лучшее, 31 — худшее)
            output_path
        ]
        
        logging.debug(f"Запуск _run_command_simple для извлечения кадра")
        result = self._run_command_simple(cmd, process_setter)
        logging.debug(f"Результат извлечения кадра: success={result[0]}, msg={result[1]}")
        return result

    def _run_command_simple(self, cmd: list, process_setter: Optional[Callable] = None) -> tuple[bool, str]:
        """Запускает FFmpeg-команду без отслеживания прогресса."""
        logging.info(f"Запуск FFmpeg команды (simple): {' '.join(cmd)}")
        logging.debug(f"Executing FFmpeg command (simple): {' '.join(cmd)}")
        startupinfo = self._get_platform_specific_startupinfo()
        logging.debug(f"Запуск subprocess.Popen для FFmpeg команды")
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            startupinfo=startupinfo
        )
        logging.debug(f"FFmpeg процесс запущен с PID: {process.pid}")
        
        if process_setter:
            process_setter(process)
            logging.debug(f"process_setter вызван для FFmpeg процесса")
        
        output_log = []
        error_lines = []
        logging.debug(f"Начало чтения вывода FFmpeg процесса")
        for line_bytes in iter(process.stdout.readline, b''):
            try:
                line = line_bytes.decode('utf-8', errors='replace')
            except UnicodeDecodeError:
                try:
                    line = line_bytes.decode('cp1251', errors='replace')
                except UnicodeDecodeError:
                    line = line_bytes.decode('ascii', errors='replace')
            
            output_log.append(line)
            if any(keyword in line.lower() for keyword in ['error', 'failed', 'invalid', 'cannot', 'unable']):
                error_lines.append(line.strip())
        
        process.stdout.close()
        return_code = process.wait()
        logging.debug(f"FFmpeg процесс завершён с кодом возврата: {return_code}")
        full_output_message = "".join(output_log)
        
        if return_code != 0:
            logging.error(f"FFmpeg failed with return code: {return_code}")
            logging.error(f"Command: {' '.join(cmd)}")
            error_summary = "\n".join(full_output_message.strip().split('\n')[-15:])
            error_message = f"Ошибка FFmpeg (код {return_code}).\nЛог:\n{error_summary}\n\nДетальные ошибки:\n" + "\n".join(error_lines[-10:])
            return False, error_message
        else:
            logging.debug("FFmpeg extract_frame completed successfully")
            return True, "Кадр успешно извлечён."