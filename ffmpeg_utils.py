# ffmpeg_utils.py
import subprocess
import json
import os
import shlex
import platform
import time # Для более точного парсинга прогресса

# Импортируем пути из config.py
from config import FFMPEG_PATH, FFPROBE_PATH, VFR_INDICATORS

# --- Вспомогательные функции ---
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
    Парсит строку вывода FFmpeg, запущенного с -progress pipe:1
    Возвращает процент выполнения или None.
    Пример строк:
    frame=123
    fps=25.0
    stream_0_0_q=28.0
    bitrate=  150.2kbits/s
    total_size=12345
    out_time_us=123456789  (microseconds)
    out_time_ms=123456     (milliseconds)
    out_time=00:02:03.456
    dup_frames=0
    drop_frames=0
    speed=1.0x
    progress=continue / end
    """
    if duration_seconds is None or duration_seconds <= 0:
        return -1 # Неопределенный прогресс, если нет длительности

    if line.startswith("out_time_ms="):
        try:
            processed_ms = int(line.split("=")[1])
            processed_seconds = processed_ms / 1000.0
            percent = int((processed_seconds / duration_seconds) * 100)
            return min(max(percent, 0), 100)
        except (ValueError, IndexError):
            return -1 # Ошибка парсинга
    elif line.startswith("progress=end"):
        return 100 # Конец обработки
    
    # Резервный парсинг для -loglevel error (менее точный)
    # time=00:00:10.52 или frame=  13 fps=0.0 q=0.0 size=    21kB time=00:00:00.36
    if "time=" in line and ("bitrate=" in line or "speed=" in line): # "speed=" добавляется для большей надежности
        try:
            time_str = line.split("time=")[1].split(" ")[0]
            if '.' in time_str:
                hms_str = time_str.split('.')[0]
                ms_part = time_str.split('.')[1] if len(time_str.split('.')) > 1 else "0"
            else:
                hms_str = time_str
                ms_part = "0"

            if len(hms_str.split(':')) == 3:
                h, m, s = map(int, hms_str.split(':'))
                processed_seconds_val = float(h * 3600 + m * 60 + s) + float(f"0.{ms_part}")
                percent = int((processed_seconds_val / duration_seconds) * 100)
                return min(max(percent, 0), 100)
        except (ValueError, IndexError):
            pass # Ошибка парсинга, продолжаем

    return -1 # Не удалось определить прогресс по этой строке

def _run_command_with_progress(command_list, progress_callback=None, duration_seconds=None):
    """
    Запускает команду FFmpeg и вызывает callback с прогрессом.
    progress_callback(percent: int)
    duration_seconds: общая длительность видео для расчета прогресса (если известна)
    Возвращает (bool: успех, str: сообщение об ошибке/успехе)
    """
    print(f"Executing: {' '.join(command_list)}")
    startupinfo = _get_platform_specific_startupinfo()

    # Добавляем -progress pipe:1 для парсинга прогресса из stdout
    # Важно: -progress должен идти перед -i или после него, но до указания выходного файла.
    # Чтобы не конфликтовать с другими -loglevel, лучше добавить его в начало.
    # Однако, если уже есть -hide_banner и -loglevel error, стандартный вывод stderr может быть чище.
    # Попробуем перенаправить stderr в stdout и парсить его.
    # Для надежного прогресса, FFmpeg команду надо формировать так, чтобы `-progress pipe:1`
    # был одним из первых аргументов, а стандартный лог шел в stderr.
    # Здесь упрощенный вариант: читаем все из stdout (куда перенаправлен stderr)

    # Проверим, есть ли уже -progress в команде. Если нет, и progress_callback есть, добавим.
    # Это грязновато, лучше формировать команду сразу с этим флагом.
    # Для текущей реализации, где stderr->stdout, будем парсить обычный вывод.
    # Если хотим точный прогресс, команда должна включать `-v quiet -stats -progress pipe:1`
    # и stdout парситься специально.

    process = subprocess.Popen(
        command_list,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, # stderr -> stdout
        universal_newlines=True,
        startupinfo=startupinfo,
        bufsize=1 # Построчная буферизация для немедленного чтения
    )

    output_log = [] # Сохраняем весь вывод для лога ошибок

    for line in iter(process.stdout.readline, ''):
        stripped_line = line.strip()
        output_log.append(stripped_line)
        # print(stripped_line) # Для отладки в консоли

        if progress_callback:
            percent = _parse_ffmpeg_progress_line(stripped_line, duration_seconds)
            if percent != -1 : # Если -1, значит не строка с прогрессом или не удалось распарсить
                progress_callback(percent)
            elif progress_callback and duration_seconds is None: # Если длительность не известна
                progress_callback(-1) # Посылаем сигнал неопределенного прогресса


    process.stdout.close()
    return_code = process.wait()
    full_output_message = "\n".join(output_log)

    if return_code == 0:
        return True, "Команда FFmpeg успешно выполнена."
    else:
        error_message = f"Ошибка FFmpeg (код {return_code}).\nЛог:\n{full_output_message}"
        print(error_message) # Печатаем в консоль для разработчика
        return False, f"Ошибка FFmpeg (код {return_code}). См. консоль для деталей."


def get_video_info(filepath):
    """Получает информацию о видео с помощью ffprobe."""
    if not os.path.exists(FFPROBE_PATH):
        return None, f"ffprobe не найден: {FFPROBE_PATH}"
    if not os.path.exists(filepath):
        return None, f"Видеофайл не найден: {filepath}"

    # shlex.split некорректно работает с путями Windows внутри кавычек, если они уже переданы как одна строка
    # Лучше передавать список аргументов Popen или использовать platform-specific shlex
    command = [
        FFPROBE_PATH,
        "-v", "error",
        "-show_format",
        "-show_streams",
        "-of", "json",
        filepath
    ]
    
    startupinfo = _get_platform_specific_startupinfo()
        
    try:
        process = subprocess.Popen(command, 
                                   stdout=subprocess.PIPE, 
                                   stderr=subprocess.PIPE, 
                                   text=True,
                                   startupinfo=startupinfo)
        stdout, stderr = process.communicate(timeout=20) # Увеличим таймаут

        if process.returncode == 0 and stdout:
            try:
                return json.loads(stdout), None
            except json.JSONDecodeError as json_err:
                error_msg = f"Ошибка декодирования JSON из ffprobe: {json_err}\nВывод ffprobe:\n{stdout}"
                print(error_msg)
                return None, error_msg
        else:
            error_msg = f"Ошибка ffprobe (код {process.returncode}): {stderr.strip() if stderr else 'Нет вывода ошибок'}"
            print(error_msg)
            return None, error_msg
    except subprocess.TimeoutExpired:
        process.kill() # Завершить процесс, если он завис
        error_msg = "Ошибка ffprobe: команда выполнялась слишком долго (таймаут)."
        print(error_msg)
        return None, error_msg
    except FileNotFoundError: # Хотя мы проверяем путь к FFPROBE_PATH, эта ошибка может возникнуть если сам путь к видео некорректен для ОС
        return None, f"ffprobe не найден или путь к видео некорректен. Проверьте путь: {FFPROBE_PATH} и видео: {filepath}"
    except Exception as e:
        error_msg = f"Неизвестная ошибка ffprobe: {e}"
        print(error_msg)
        return None, error_msg


def needs_vfr_fix(video_info_data):
    """Проверка, нуждается ли видео в починке VFR на основе данных от ffprobe."""
    if not video_info_data or 'streams' not in video_info_data:
        return False
    
    for stream in video_info_data['streams']:
        if stream.get('codec_type') == 'video':
            r_frame_rate = stream.get('r_frame_rate', '')
            avg_frame_rate = stream.get('avg_frame_rate', '')
            
            # Проверяем, есть ли проблемные значения
            is_r_rate_problem = r_frame_rate in VFR_INDICATORS["r_frame_rate_problem"]
            is_avg_rate_problem = avg_frame_rate in VFR_INDICATORS["avg_frame_rate_problem"]
            
            if is_r_rate_problem or is_avg_rate_problem:
                print(f"VFR Check: r_frame_rate='{r_frame_rate}', avg_frame_rate='{avg_frame_rate}'. Рекомендуется починка.")
                return True
            
            # Дополнительная эвристика: если r_frame_rate и avg_frame_rate сильно различаются
            # (это требует более сложного парсинга и сравнения числовых значений)
            # Например, если r_frame_rate "60/1", а avg_frame_rate "23976/1001"
            if r_frame_rate and avg_frame_rate and r_frame_rate != "0/0" and avg_frame_rate != "0/0":
                try:
                    r_val_num, r_val_den = map(int, r_frame_rate.split('/'))
                    avg_val_num, avg_val_den = map(int, avg_frame_rate.split('/'))
                    if r_val_den != 0 and avg_val_den != 0:
                        r_numeric = r_val_num / r_val_den
                        avg_numeric = avg_val_num / avg_val_den
                        # Если разница больше, чем, скажем, 10% (можно настроить)
                        if abs(r_numeric - avg_numeric) > (avg_numeric * 0.1):
                            print(f"VFR Check: r_frame_rate ({r_numeric:.2f}) и avg_frame_rate ({avg_numeric:.2f}) значительно различаются. Рекомендуется починка.")
                            return True
                except ValueError:
                    pass # Не удалось распарсить как дроби

    return False

def get_video_duration_seconds(video_info_data):
    """Извлекает длительность видео в секундах из данных ffprobe."""
    duration_str = None
    if video_info_data and 'format' in video_info_data and 'duration' in video_info_data['format']:
        duration_str = video_info_data['format']['duration']
    
    # Если в формате нет, пробуем из первого видеопотока
    if not duration_str and video_info_data and 'streams' in video_info_data:
        for stream in video_info_data['streams']:
            if stream.get('codec_type') == 'video' and 'duration' in stream:
                duration_str = stream['duration']
                break
    
    if duration_str:
        try:
            return float(duration_str)
        except (ValueError, TypeError):
            print(f"Не удалось преобразовать длительность '{duration_str}' в float.")
            return None
    return None


# --- Основные функции для операций ---

def fix_vfr(input_path, output_path, target_fps, fix_crf_h264, fix_crf_vp9, output_extension_key, progress_callback=None, duration_seconds=None):
    """Исправляет VFR, конвертируя видео в CFR."""
    if not os.path.exists(FFMPEG_PATH):
        return False, f"ffmpeg не найден: {FFMPEG_PATH}"

    command = [
        FFMPEG_PATH, "-y", # Автоматически перезаписывать выходной файл
        "-i", input_path,
        "-vf", f"fps={target_fps}", # Устанавливаем постоянную частоту кадров
    ]
    
    # Кодек для починки выбираем на основе КОНЕЧНОГО желаемого формата,
    # чтобы минимизировать двойное пережатие потерь.
    if output_extension_key == "webm":
        command.extend(["-c:v", "libvpx-vp9", "-crf", str(fix_crf_vp9), "-b:v", "0", "-row-mt", "1", "-deadline", "good", "-cpu-used", "1"])
    elif output_extension_key in ["mp4", "mkv"]:
        command.extend(["-c:v", "libx264", "-crf", str(fix_crf_h264), "-preset", "medium"]) # medium - хороший баланс
    else:
        return False, f"Неизвестное расширение для этапа починки: {output_extension_key}"

    command.extend(["-c:a", "copy", output_path]) # Копируем аудио, чтобы сохранить качество и ускорить

    return _run_command_with_progress(command, progress_callback, duration_seconds)


def compress_video(input_path, output_path, output_ext_details, crf_value, progress_callback=None, duration_seconds=None):
    """Сжимает видео с заданными параметрами."""
    if not os.path.exists(FFMPEG_PATH):
        return False, f"ffmpeg не найден: {FFMPEG_PATH}"

    command = [
        FFMPEG_PATH, "-y",
        "-i", input_path,
        "-hide_banner", # Скрыть информацию о сборке ffmpeg
        # "-stats", # Для вывода статистики в stderr, если -progress не используется
        # Вместо -loglevel error, лучше парсить -progress pipe:1 или stderr от -stats
        # Если используется -progress pipe:1, то лог ошибок идет в stderr
        # Здесь мы перенаправили stderr в stdout, так что -loglevel error не нужен, если парсим прогресс
    ]
    # Для более надежного прогресса:
    if progress_callback and duration_seconds:
         command.extend(["-progress", "pipe:1"]) # Вывод прогресса в пайп (stdout в нашем случае)
    else: # Если прогресс не нужен или нет длительности
        command.extend(["-loglevel", "error"])


    video_codec = output_ext_details["codec"]
    audio_codec = output_ext_details["audio_codec"]

    if video_codec == "libvpx-vp9":
        command.extend(["-c:v", "libvpx-vp9", "-crf", str(crf_value), "-b:v", "0", "-row-mt", "1", "-deadline", "good", "-cpu-used", "2"])
        # -cpu-used: 0-8 (медленнее и качественнее к 0, быстрее к 8). 1-2 хороший компромисс.
        # -deadline: good (баланс), realtime (быстро, хуже качество), best (очень медленно)
    elif video_codec == "libx264":
        command.extend([
            "-c:v", "libx264",
            "-crf", str(crf_value),
            "-preset", "medium", # "slow" для лучшего сжатия, "medium" - хороший компромисс
            "-pix_fmt", "yuv420p", # Для совместимости
            "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2" # Как в CompressO
        ])
        if os.path.splitext(output_path)[1].lower() == ".mp4":
            command.extend(["-movflags", "+faststart"]) # Для стриминга mp4
    else:
        return False, f"Неподдерживаемый видеокодек для сжатия: {video_codec}"

    # Аудио
    if audio_codec == "libopus":
        command.extend(["-c:a", "libopus", "-b:a", "128k", "-vbr", "on"]) # Opus обычно VBR
    elif audio_codec == "aac":
        command.extend(["-c:a", "aac", "-b:a", "128k"]) # AAC, битрейт 128k
    else: # Если аудиокодек не указан или неизвестен
        command.extend(["-c:a", "copy"]) # Копируем аудиопоток

    command.append(output_path)
    return _run_command_with_progress(command, progress_callback, duration_seconds)