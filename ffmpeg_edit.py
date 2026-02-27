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