import logging
from typing import Optional, Callable
from config import DEFAULT_FPS_FIX

class FFmpegEncodeMixin:
    def fix_vfr_target_crf(self, input_path: str, output_path: str, output_format: str, codec: str, crf_value: int, 
                           preset_value: str, progress_callback: Optional[Callable], duration_seconds: float, 
                           use_hardware: bool = False, video_info: dict = None, process_setter: Optional[Callable] = None) -> tuple[bool, str]:
        gpu_info = self.get_gpu_info()
        has_nvenc = "NVIDIA NVENC" in gpu_info
        cmd = [self.ffmpeg_path, "-y"]
        if video_info and video_info.get("is_hevc", False) and has_nvenc:
            cmd.extend(["-hwaccel", "cuda"])
        cmd.extend(["-i", input_path])
        vf_filters = [f"fps={DEFAULT_FPS_FIX}"]
        if video_info and video_info.get("is_10bit", False) and codec != "libx265":
            vf_filters.append("format=yuv420p")
        if vf_filters:
            cmd.extend(["-vf", ",".join(vf_filters)])
            
        if codec == "libvpx-vp9":
            if use_hardware and has_nvenc:
                cmd.extend(["-c:v", "vp9_nvenc", "-crf", str(crf_value), "-b:v", "0"])
            else:
                cmd.extend(["-c:v", "libvpx-vp9", "-crf", str(crf_value), "-b:v", "0", "-deadline", "good", "-cpu-used", "2"])
            cmd.extend(["-c:a", "copy"])
        elif codec == "libx265":
            if use_hardware and has_nvenc:
                cmd.extend(["-c:v", "hevc_nvenc", "-crf", str(crf_value), "-preset", "p6", "-tune", "ll"])
            else:
                cmd.extend(["-c:v", "libx265", "-crf", str(crf_value), "-preset", preset_value])
            cmd.extend(["-c:a", "copy"])
        else:
            if use_hardware and has_nvenc:
                cmd.extend(["-c:v", "h264_nvenc", "-cq", str(crf_value), "-preset", "p6", "-tune", "ll"])
            else:
                cmd.extend(["-c:v", "libx264", "-crf", str(crf_value), "-preset", preset_value])
            cmd.extend(["-c:a", "copy"])
            
        if video_info and video_info.get("has_subtitles", False):
            if output_format == "mp4": cmd.extend(["-c:s", "mov_text"])
            else: cmd.extend(["-c:s", "copy"])
            cmd.extend(["-map", "0:V", "-map", "0:a", "-map", "0:s"])
        else:
            cmd.extend(["-map", "0:V", "-map", "0:a"])
            
        if output_format == "mp4": cmd.extend(["-movflags", "+faststart"])
        cmd.extend(["-progress", "pipe:1", output_path])
        return self._run_command_with_progress(cmd, progress_callback, duration_seconds, "VFR-fix+сжатие", process_setter)
    
    def compress_video_core(self, input_path: str, output_path: str, output_format: str, codec: str, crf_value: int,
                           preset_value: str, progress_callback: Optional[Callable], duration_seconds: float, 
                           video_info: dict = None, use_hardware: bool = False, process_setter: Optional[Callable] = None) -> tuple[bool, str]:
        if video_info is None: video_info = self.get_video_info(input_path)
        gpu_info = self.get_gpu_info()
        has_nvenc = "NVIDIA NVENC" in gpu_info
        cmd =[self.ffmpeg_path, "-y"]
        if video_info.get("is_hevc", False) and has_nvenc: cmd.extend(["-hwaccel", "cuda"])
        cmd.extend(["-i", input_path])
        
        vf_filters =[]
        if video_info.get("is_10bit", False) and codec != "libx265": vf_filters.append("format=yuv420p")
        if codec == "libx264" and not use_hardware: vf_filters.append("pad=ceil(iw/2)*2:ceil(ih/2)*2")
        if vf_filters: cmd.extend(["-vf", ",".join(vf_filters)])
        
        if codec == "libvpx-vp9":
            if use_hardware and has_nvenc: cmd.extend(["-c:v", "vp9_nvenc", "-crf", str(crf_value), "-b:v", "0"])
            else: cmd.extend(["-c:v", "libvpx-vp9", "-crf", str(crf_value), "-b:v", "0", "-deadline", "good", "-cpu-used", "2"])
        elif codec == "libx265":
            if use_hardware and has_nvenc: cmd.extend(["-c:v", "hevc_nvenc", "-crf", str(crf_value), "-preset", "p6", "-tune", "ll"])
            else: cmd.extend(["-c:v", "libx265", "-crf", str(crf_value), "-preset", preset_value])
        else:
            if use_hardware and has_nvenc: cmd.extend(["-c:v", "h264_nvenc", "-cq", str(crf_value), "-preset", "p6", "-tune", "ll", "-spatial_aq", "1", "-temporal_aq", "1", "-rc-lookahead", "20", "-aq-strength", "15"])
            else: cmd.extend(["-c:v", "libx264", "-crf", str(crf_value), "-preset", preset_value])
            
        cmd.extend(["-c:a", "aac", "-b:a", "192k"])
        
        if video_info and video_info.get("has_subtitles", False):
            if output_format == "mp4": cmd.extend(["-c:s", "mov_text"])
            else: cmd.extend(["-c:s", "copy"])
            cmd.extend(["-map", "0:V", "-map", "0:a", "-map", "0:s"])
        else:
            cmd.extend(["-map", "0:V", "-map", "0:a"])
            
        if output_format == "mp4": cmd.extend(["-movflags", "+faststart"])
        cmd.extend(["-progress", "pipe:1", output_path])
        return self._run_command_with_progress(cmd, progress_callback, duration_seconds, "Сжатие", process_setter)

    def compress_video_core_no_subtitles(self, *args, **kwargs) -> tuple[bool, str]:
        # Аналогичный метод, но без маппинга субтитров
        kwargs['video_info'] = kwargs.get('video_info', {})
        kwargs['video_info']['has_subtitles'] = False
        return self.compress_video_core(*args, **kwargs)

    def compress_video_core_full_map(self, input_path: str, output_path: str, output_format: str, codec: str, crf_value: int,
                                     preset_value: str, progress_callback: Optional[Callable], duration_seconds: float, 
                                     video_info: dict = None, use_hardware: bool = False, process_setter: Optional[Callable] = None) -> tuple[bool, str]:
        # Полный маппинг, используется как фоллбэк
        cmd =[self.ffmpeg_path, "-y", "-i", input_path]
        cmd.extend(["-c:v", "libx264", "-crf", str(crf_value), "-preset", preset_value, "-c:a", "aac", "-b:a", "192k"])
        cmd.extend(["-map", "0", "-map", "-0:d", "-progress", "pipe:1", output_path])
        return self._run_command_with_progress(cmd, progress_callback, duration_seconds, "Сжатие (fallback)", process_setter)