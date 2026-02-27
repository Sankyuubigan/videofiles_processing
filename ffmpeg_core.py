import subprocess
import platform
import logging
from typing import Optional, Callable

class FFmpegCore:
    def __init__(self):
        from settings_manager import get_actual_ffmpeg_path, get_ffprobe_path
        self.ffmpeg_path = get_actual_ffmpeg_path()
        self.ffprobe_path = get_ffprobe_path()
    
    def _get_platform_specific_startupinfo(self):
        if platform.system() == "Windows":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            return startupinfo
        return None
    
    def _parse_ffmpeg_progress_line(self, line: str, duration_seconds: float) -> int:
        if duration_seconds is None or duration_seconds <= 0:
            return -1
        line = line.strip()
        if line.startswith("out_time_us="):
            try:
                parts = line.split("=", 1)
                if len(parts) < 2:
                    return -1
                value_str = parts[1].strip()
                if value_str == "N/A":
                    return -1
                processed_us = int(value_str)
                processed_seconds = processed_us / 1_000_000
                percent = int((processed_seconds / duration_seconds) * 100)
                return min(max(percent, 0), 100)
            except (ValueError, IndexError):
                return -1
        elif line.startswith("progress=end"):
            return 100
        return -1
    
    def _run_command_with_progress(self, cmd: list, progress_callback: Optional[Callable[[int, str], None]], 
                                  duration_seconds: Optional[float], stage_name: str, 
                                  process_setter: Optional[Callable] = None) -> tuple[bool, str]:
        logging.debug(f"Executing FFmpeg command: {' '.join(cmd)}")
        startupinfo = self._get_platform_specific_startupinfo()
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            startupinfo=startupinfo
        )
        
        if process_setter:
            process_setter(process)
        
        output_log = []
        error_lines =[]
        for line_bytes in iter(process.stdout.readline, b''):
            try:
                line = line_bytes.decode('utf-8', errors='replace')
            except UnicodeDecodeError:
                try:
                    line = line_bytes.decode('cp1251', errors='replace')
                except UnicodeDecodeError:
                    line = line_bytes.decode('ascii', errors='replace')
            
            output_log.append(line)
            if any(keyword in line.lower() for keyword in['error', 'failed', 'invalid', 'cannot', 'unable']):
                error_lines.append(line.strip())
            if progress_callback and duration_seconds:
                percent = self._parse_ffmpeg_progress_line(line, duration_seconds)
                if percent != -1:
                    progress_callback(percent, f"{stage_name}: {percent}%")
        process.stdout.close()
        return_code = process.wait()
        full_output_message = "".join(output_log)
        
        if return_code != 0:
            logging.error(f"FFmpeg failed with return code: {return_code}")
            logging.error(f"Command: {' '.join(cmd)}")
            error_summary = "\n".join(full_output_message.strip().split('\n')[-15:])
            error_message = f"Ошибка FFmpeg (код {return_code}).\nЛог:\n{error_summary}\n\nДетальные ошибки:\n" + "\n".join(error_lines[-10:])
            return False, error_message
        else:
            logging.debug("FFmpeg command completed successfully")
            return True, "Команда FFmpeg успешно выполнена."