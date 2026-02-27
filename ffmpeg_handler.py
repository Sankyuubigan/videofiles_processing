from ffmpeg_core import FFmpegCore
from ffmpeg_probe import FFmpegProbeMixin
from ffmpeg_encode import FFmpegEncodeMixin
from ffmpeg_edit import FFmpegEditMixin

class FFmpegHandler(FFmpegCore, FFmpegProbeMixin, FFmpegEncodeMixin, FFmpegEditMixin):
    """Фасад для работы с FFmpeg, объединяющий все модули."""
    def __init__(self):
        super().__init__()