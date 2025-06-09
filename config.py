# config.py
import os
import platform # Добавлено для определения ОС

# Пути к FFmpeg и ffprobe (предполагаем, что они лежат рядом с main.py)
# BASE_DIR теперь определяется в main.py и передается, либо используется абсолютный путь к скрипту
# Это сделано для корректной работы при упаковке в .exe с PyInstaller/Nuitka,
# где __file__ может вести себя по-разному.
# Но для простоты разработки пока оставим определение здесь, предполагая запуск из корня.
# Для большей надежности при запуске из разных мест, BASE_DIR лучше определять в main.py
# и передавать в другие модули, или использовать os.path.abspath(os.path.dirname(__file__))
# непосредственно в ffmpeg_utils.py, если он всегда будет рядом с ffmpeg.exe

_is_windows = platform.system() == "Windows"
_executable_ext = ".exe" if _is_windows else ""

# Предполагаем, что config.py, ffmpeg_utils.py, main.py находятся на одном уровне,
# а ffmpeg/ffprobe лежат в той же директории.
# Если структура другая, нужно будет скорректировать.
try:
    # Этот путь будет работать, если скрипты и ffmpeg лежат в одной директории
    # и вы запускаете main.py из этой директории.
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
except NameError:
    # Если __file__ не определен (например, при интерактивном запуске или в некоторых сценариях упаковки),
    # пытаемся получить текущую рабочую директорию. Это менее надежно.
    BASE_DIR = os.getcwd()


FFMPEG_PATH = os.path.join(BASE_DIR, f"ffmpeg{_executable_ext}")
FFPROBE_PATH = os.path.join(BASE_DIR, f"ffprobe{_executable_ext}")


# Настройки CRF
DEFAULT_MIN_CRF_H264 = 18 # Сделаем чуть лучше для "минимального" CRF (визуально без потерь)
DEFAULT_MAX_CRF_H264 = 35 # Уменьшим макс, т.к. выше 30-35 уже очень плохо
DEFAULT_CRF_H264 = 23     # Стандартный хороший CRF

DEFAULT_MIN_CRF_VP9 = 15
DEFAULT_MAX_CRF_VP9 = 50 # Для VP9 диапазон шире, но практический смысл выше 50 редкий
DEFAULT_CRF_VP9 = 28     # Дефолтный хороший CRF для VP9

# Настройки починки VFR
DEFAULT_FIX_CRF_VP9 = 18
DEFAULT_FIX_CRF_H264 = 18
DEFAULT_FPS_FIX = 25.0 # Сделаем float для большей точности в ffmpeg

# Расширения
OUTPUT_EXTENSIONS = {
    "mp4": {"codec": "libx264", "audio_codec": "aac", "crf_min": DEFAULT_MIN_CRF_H264, "crf_max": DEFAULT_MAX_CRF_H264, "crf_default": DEFAULT_CRF_H264},
    "webm": {"codec": "libvpx-vp9", "audio_codec": "libopus", "crf_min": DEFAULT_MIN_CRF_VP9, "crf_max": DEFAULT_MAX_CRF_VP9, "crf_default": DEFAULT_CRF_VP9},
    "mkv": {"codec": "libx264", "audio_codec": "aac", "crf_min": DEFAULT_MIN_CRF_H264, "crf_max": DEFAULT_MAX_CRF_H264, "crf_default": DEFAULT_CRF_H264}
}
DEFAULT_OUTPUT_EXTENSION_KEY = "mp4" # Ключ, а не значение

# Настройки для определения проблемного VFR
# Эти значения являются сильными индикаторами, но не 100% гарантией.
# Иногда ffprobe может выводить их даже для CFR видео, если метаданные повреждены.
VFR_INDICATORS = {
    "r_frame_rate_problem": ["1000/1", "0/0"], # Если r_frame_rate одно из этих
    "avg_frame_rate_problem": ["0/0"]          # ИЛИ avg_frame_rate одно из этих
}

# Имена временных файлов
TEMP_FIXED_VIDEO_SUFFIX = "_temp_fixed"
COMPRESSED_VIDEO_SUFFIX = "_compressed"