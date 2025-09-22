# ffmpeg_utils.py
import subprocess
import json
import os
import platform
import time

from config import FFMPEG_PATH, FFPROBE_PATH, VFR_INDICATORS

def _get_platform_specific_startupinfo():
    """Возвращает startupinfo для скрытия консольного окна на Windows."""
    if platform.system() == "Windows":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        return startupinfo
    return None

def _parse_ffmpeg_progress_line(line, duration_seconds):
    """
    Парсит строку вывода FFmpeg для определения прогресса.
    Возвращает процент выполнения (0-100) или -1, если прогресс не найден.
    """
    if duration_seconds is None or duration_seconds <= 0:
        return -1

    # Парсинг для вывода от -progress pipe:1
    if line.startswith("out_time_ms="):
        try:
            processed_ms = int(line.split("=")[1])
            processed_seconds = processed_ms / 1000.0
            percent = int((processed_seconds / duration_seconds) * 100)
            return min(max(percent, 0), 100)
        except (ValueError, IndexError):
            return -1
    elif line.startswith("progress=end"):
        return 100

    # Резервный парсинг для обычного вывода
    if "time=" in line and "speed=" in line:
        try:
            time_str = line.split("time=")[1].split(" ")[0]
            ts = time.strptime(time_str.split('.')[0], '%H:%M:%S')
            processed_seconds_val = ts.tm_hour * 3600 + ts.tm_min * 60 + ts.tm_sec
            percent = int((processed_seconds_val / duration_seconds) * 100)
            return min(max(percent, 0), 100)
        except (ValueError, IndexError):
            pass

    return -1

def _run_command_with_progress(command_list, progress_callback=None, duration_seconds=None):
    """Запускает FFmpeg, отслеживая прогресс."""
    print(f"Executing: {' '.join(command_list)}")
    startupinfo = _get_platform_specific_startupinfo()

    process = subprocess.Popen(
        command_list,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        startupinfo=startupinfo,
        bufsize=1
    )

    output_log = []
    for line in iter(process.stdout.readline, ''):
        stripped_line = line.strip()
        output_log.append(stripped_line)

        if progress_callback:
            percent = _parse_ffmpeg_progress_line(stripped_line, duration_seconds)
            if percent != -1:
                progress_callback(percent)
            elif duration_seconds is None:
                progress_callback(-1)

    process.stdout.close()
    return_code = process.wait()
    full_output_message = "\n".join(output_log)

    if return_code == 0:
        return True, "Команда FFmpeg успешно выполнена."
    else:
        error_message = f"Ошибка FFmpeg (код {return_code}).\nЛог:\n{full_output_message}"
        print(error_message)
        return False, f"Ошибка FFmpeg (код {return_code})."

def get_video_info(filepath):
    """Получает информацию о видео с помощью ffprobe."""
    if not os.path.exists(FFPROBE_PATH):
        return None, f"ffprobe не найден: {FFPROBE_PATH}"
    if not os.path.exists(filepath):
        return None, f"Видеофайл не найден: {filepath}"

    command = [
        FFPROBE_PATH, "-v", "error",
        "-show_format", "-show_streams", "-of", "json", filepath
    ]
    startupinfo = _get_platform_specific_startupinfo()
        
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, startupinfo=startupinfo)
        stdout, stderr = process.communicate(timeout=20)

        if process.returncode == 0 and stdout:
            return json.loads(stdout), None
        else:
            error_msg = f"Ошибка ffprobe (код {process.returncode}): {stderr.strip() or 'Нет вывода ошибок'}"
            print(error_msg)
            return None, error_msg
    except Exception as e:
        error_msg = f"Исключение при вызове ffprobe: {e}"
        print(error_msg)
        return None, error_msg

def needs_vfr_fix(video_info_data):
    """Проверяет, нуждается ли видео в починке VFR."""
    if not video_info_data or 'streams' not in video_info_data:
        return False
    
    for stream in video_info_data['streams']:
        if stream.get('codec_type') == 'video':
            r_rate = stream.get('r_frame_rate', '')
            avg_rate = stream.get('avg_frame_rate', '')
            
            if r_rate in VFR_INDICATORS["r_frame_rate_problem"] or avg_rate in VFR_INDICATORS["avg_frame_rate_problem"]:
                return True
    return False

def get_video_duration_seconds(video_info_data):
    """Извлекает длительность видео в секундах."""
    duration_str = None
    if video_info_data and 'format' in video_info_data and 'duration' in video_info_data['format']:
        duration_str = video_info_data['format']['duration']
    
    if not duration_str and video_info_data and 'streams' in video_info_data:
        for stream in video_info_data['streams']:
            if stream.get('codec_type') == 'video' and 'duration' in stream:
                duration_str = stream['duration']
                break
    
    if duration_str:
        try:
            return float(duration_str)
        except (ValueError, TypeError):
            return None
    return None

def fix_vfr(input_path, output_path, target_fps, fix_crf_h264, fix_crf_vp9, output_ext_key, progress_callback=None, duration_seconds=None):
    """Исправляет VFR, конвертируя видео в CFR."""
    command = [
        FFMPEG_PATH, "-y", "-i", input_path,
        "-vf", f"fps={target_fps}",
    ]
    
    if output_ext_key == "webm":
        command.extend(["-c:v", "libvpx-vp9", "-crf", str(fix_crf_vp9), "-b:v", "0"])
    else:
        command.extend(["-c:v", "libx264", "-crf", str(fix_crf_h264), "-preset", "medium"])

    command.extend(["-c:a", "copy", output_path])

    return _run_command_with_progress(command, progress_callback, duration_seconds)

def compress_video(input_path, output_path, output_ext_details, crf_value, progress_callback=None, duration_seconds=None):
    """Сжимает видео с заданными параметрами."""
    command = [
        FFMPEG_PATH, "-y", "-i", input_path,
        "-hide_banner", "-progress", "pipe:1"
    ]

    video_codec = output_ext_details["codec"]
    audio_codec = output_ext_details["audio_codec"]

    if video_codec == "libvpx-vp9":
        command.extend(["-c:v", "libvpx-vp9", "-crf", str(crf_value), "-b:v", "0", "-deadline", "good", "-cpu-used", "2"])
    elif video_codec == "libx264":
        command.extend([
            "-c:v", "libx264", "-crf", str(crf_value), "-preset", "medium",
            "-pix_fmt", "yuv420p", "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2"
        ])
        if os.path.splitext(output_path)[1].lower() == ".mp4":
            command.extend(["-movflags", "+faststart"])
    else:
        return False, f"Неподдерживаемый кодек: {video_codec}"

    if audio_codec == "libopus":
        command.extend(["-c:a", "libopus", "-b:a", "128k"])
    elif audio_codec == "aac":
        command.extend(["-c:a", "aac", "-b:a", "128k"])
    else:
        command.extend(["-c:a", "copy"])

    command.append(output_path)
    return _run_command_with_progress(command, progress_callback, duration_seconds)