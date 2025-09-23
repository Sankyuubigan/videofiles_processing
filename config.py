# config.py
import os
import platform

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_is_windows = platform.system() == "Windows"
_executable_ext = ".exe" if _is_windows else ""

FFMPEG_PATH   = os.path.join(BASE_DIR, f"ffmpeg{_executable_ext}")
FFPROBE_PATH  = os.path.join(BASE_DIR, f"ffprobe{_executable_ext}")

DEFAULT_MIN_CRF_H264 = 18
DEFAULT_MAX_CRF_H264 = 35
DEFAULT_CRF_H264     = 23

DEFAULT_MIN_CRF_VP9 = 15
DEFAULT_MAX_CRF_VP9 = 50
DEFAULT_CRF_VP9     = 28

DEFAULT_FIX_CRF_VP9  = 30
DEFAULT_FIX_CRF_H264 = 28
DEFAULT_FPS_FIX      = 25.0

# Используем программное кодирование по умолчанию (libx264)
DEFAULT_USE_HARDWARE_ENCODING = False

# коэффициенты условного сжатия для расчёта примерного размера
H264_CRF_FACTOR = {
    18: 1.0, 19: 0.95, 20: 0.90, 21: 0.85, 22: 0.80, 23: 0.75,
    24: 0.70, 25: 0.65, 26: 0.60, 27: 0.55, 28: 0.50, 29: 0.45, 30: 0.40,
    31: 0.38, 32: 0.36, 33: 0.34, 34: 0.32, 35: 0.30
}
VP9_CRF_FACTOR = {
    15: 1.0, 16: 0.95, 17: 0.90, 18: 0.85, 19: 0.80, 20: 0.75,
    21: 0.70, 22: 0.65, 23: 0.60, 24: 0.55, 25: 0.50, 26: 0.45, 27: 0.40,
    28: 0.38, 29: 0.36, 30: 0.34, 31: 0.32, 32: 0.30, 33: 0.28, 34: 0.26,
    35: 0.24, 36: 0.22, 37: 0.20, 38: 0.18, 39: 0.16, 40: 0.14,
    41: 0.13, 42: 0.12, 43: 0.11, 44: 0.10, 45: 0.09, 46: 0.08,
    47: 0.07, 48: 0.06, 49: 0.05, 50: 0.04
}

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

VFR_INDICATORS = {
    "r_frame_rate_problem": ["1000/1", "0/0"],
    "avg_frame_rate_problem": ["0/0"]
}

TEMP_FIXED_VIDEO_SUFFIX   = "_temp_fixed_cfr"
COMPRESSED_VIDEO_SUFFIX   = "_compressed"