# config.py
import os
import platform

# Определяем базовую директорию относительно этого файла.
# Это делает пути к ffmpeg/ffprobe надежными, независимо от того,
# откуда запускается main.py.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Определяем расширение исполняемых файлов для текущей ОС
_is_windows = platform.system() == "Windows"
_executable_ext = ".exe" if _is_windows else ""

# Формируем полные пути к исполняемым файлам
FFMPEG_PATH = os.path.join(BASE_DIR, f"ffmpeg{_executable_ext}")
FFPROBE_PATH = os.path.join(BASE_DIR, f"ffprobe{_executable_ext}")

# Настройки CRF (Constant Rate Factor)
# H.264 (для mp4, mkv)
DEFAULT_MIN_CRF_H264 = 18  # Визуально без потерь
DEFAULT_MAX_CRF_H264 = 35  # Выше уже очень плохое качество
DEFAULT_CRF_H264 = 23      # Стандартное хорошее значение

# VP9 (для webm)
DEFAULT_MIN_CRF_VP9 = 15   # Высокое качество для VP9
DEFAULT_MAX_CRF_VP9 = 50   # Практический верхний предел для VP9
DEFAULT_CRF_VP9 = 28       # Хорошее значение по умолчанию для VP9

# Настройки для этапа "починки" VFR (проблемная частота кадров)
DEFAULT_FIX_CRF_VP9 = 18    # Используем высокое качество, чтобы минимизировать потери
DEFAULT_FIX_CRF_H264 = 18   # Аналогично для H.264
DEFAULT_FPS_FIX = 25.0      # Целевая частота кадров

# Словарь с настройками для каждого поддерживаемого расширения
OUTPUT_EXTENSIONS = {
    "mp4": {
        "codec": "libx264",
        "audio_codec": "aac",
        "crf_min": DEFAULT_MIN_CRF_H264,
        "crf_max": DEFAULT_MAX_CRF_H264,
        "crf_default": DEFAULT_CRF_H264
    },
    "webm": {
        "codec": "libvpx-vp9",
        "audio_codec": "libopus",
        "crf_min": DEFAULT_MIN_CRF_VP9,
        "crf_max": DEFAULT_MAX_CRF_VP9,
        "crf_default": DEFAULT_CRF_VP9
    },
    "mkv": {
        "codec": "libx264",
        "audio_codec": "aac",
        "crf_min": DEFAULT_MIN_CRF_H264,
        "crf_max": DEFAULT_MAX_CRF_H264,
        "crf_default": DEFAULT_CRF_H264
    }
}
DEFAULT_OUTPUT_EXTENSION_KEY = "mp4"

# Индикаторы для определения проблемного VFR
VFR_INDICATORS = {
    "r_frame_rate_problem": ["1000/1", "0/0"],
    "avg_frame_rate_problem": ["0/0"]
}

# Суффиксы для имен файлов
TEMP_FIXED_VIDEO_SUFFIX = "_temp_fixed_cfr"
COMPRESSED_VIDEO_SUFFIX = "_compressed"