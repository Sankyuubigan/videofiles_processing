import logging
import os
import tempfile
import time
import json
import subprocess
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
        kwargs['video_info'] = kwargs.get('video_info', {})
        kwargs['video_info']['has_subtitles'] = False
        return self.compress_video_core(*args, **kwargs)

    def compress_video_core_full_map(self, input_path: str, output_path: str, output_format: str, codec: str, crf_value: int,
                                     preset_value: str, progress_callback: Optional[Callable], duration_seconds: float, 
                                     video_info: dict = None, use_hardware: bool = False, process_setter: Optional[Callable] = None) -> tuple[bool, str]:
        cmd =[self.ffmpeg_path, "-y", "-i", input_path]
        cmd.extend(["-c:v", "libx264", "-crf", str(crf_value), "-preset", preset_value, "-c:a", "aac", "-b:a", "192k"])
        cmd.extend(["-map", "0", "-map", "-0:d", "-progress", "pipe:1", output_path])
        return self._run_command_with_progress(cmd, progress_callback, duration_seconds, "Сжатие (fallback)", process_setter)

    def encode_chunk(self, input_path: str, output_path: str, start_time: float, duration: float,
                     codec: str, crf_value: int, preset_value: str, use_hardware: bool,
                     video_info: dict = None, force_vfr_fix: bool = False,
                     process_setter: Optional[Callable] = None) -> tuple[bool, str]:
        gpu_info = self.get_gpu_info()
        has_nvenc = "NVIDIA NVENC" in gpu_info
        
        cmd = [self.ffmpeg_path, "-y", "-ss", str(start_time), "-i", input_path, "-t", str(duration)]

        vf_filters = []
        needs_fix = force_vfr_fix or (video_info.get("needs_vfr_fix", False) if video_info else False)
        
        if needs_fix:
            vf_filters.append(f"fps={DEFAULT_FPS_FIX}")
            
        if video_info and video_info.get("is_10bit", False) and codec != "libx265":
            vf_filters.append("format=yuv420p")
            
        if codec == "libx264" and not use_hardware and not needs_fix:
            vf_filters.append("pad=ceil(iw/2)*2:ceil(ih/2)*2")
            
        if vf_filters:
            cmd.extend(["-vf", ",".join(vf_filters)])

        if codec == "libvpx-vp9":
            if use_hardware and has_nvenc: cmd.extend(["-c:v", "vp9_nvenc", "-crf", str(crf_value), "-b:v", "0"])
            else: cmd.extend(["-c:v", "libvpx-vp9", "-crf", str(crf_value), "-b:v", "0", "-deadline", "good", "-cpu-used", "2"])
        elif codec == "libx265":
            if use_hardware and has_nvenc: cmd.extend(["-c:v", "hevc_nvenc", "-crf", str(crf_value), "-preset", "p6", "-tune", "ll"])
            else: cmd.extend(["-c:v", "libx265", "-crf", str(crf_value), "-preset", preset_value])
        else:
            if use_hardware and has_nvenc: cmd.extend(["-c:v", "h264_nvenc", "-cq", str(crf_value), "-preset", "p6", "-tune", "ll"])
            else: cmd.extend(["-c:v", "libx264", "-crf", str(crf_value), "-preset", preset_value])

        cmd.extend(["-c:a", "aac", "-b:a", "192k", output_path])
        return self._run_command_simple(cmd, process_setter)

    def calculate_vmaf(self, original_path: str, chunk_path: str, start_time: float, duration: float, 
                       n_subsample: int = 5, width: int = 1920, video_info: dict = None, 
                       force_vfr_fix: bool = False, process_setter: Optional[Callable] = None) -> float:
        """Рассчитывает VMAF оценку (0-100) между оригинальным куском и сжатым с жесткой покадровой привязкой."""
        json_filename = f"vmaf_{os.getpid()}_{int(time.time() * 1000)}.json"
        json_path = os.path.join(tempfile.gettempdir(), json_filename)
        json_path_ff = json_path.replace('\\', '/').replace(':', '\\:')
        
        scale_filter = f",scale=1920:-1:flags=bicubic" if width > 1920 else ""
        
        needs_fix = force_vfr_fix or (video_info.get("needs_vfr_fix", False) if video_info else False)
        fps = video_info.get("fps", 0) if video_info else 0
        target_fps = DEFAULT_FPS_FIX if needs_fix else (fps if fps > 0 else 30)
        
        # Надежная синхронизация:
        # 1. format=yuv420p гарантирует, что разница в цветовых профилях не занизит оценку
        # 2. fps=... предотвращает дрифт таймстемпов из-за переменной частоты кадров (VFR)
        # 3. setpts=PTS-STARTPTS привязывает начало обоих потоков строго к нулевой отметке
        filter_complex = (
            f"[0:v]fps={target_fps},setpts=PTS-STARTPTS,format=yuv420p{scale_filter}[ref];"
            f"[1:v]fps={target_fps},setpts=PTS-STARTPTS,format=yuv420p{scale_filter}[dist];"
            f"[dist][ref]libvmaf=model=version=vmaf_v0.6.1neg:log_fmt=json:log_path='{json_path_ff}':n_subsample={n_subsample}"
        )
        
        cmd = [
            self.ffmpeg_path, "-y",
            "-ss", str(start_time), "-t", str(duration), "-i", original_path,
            "-i", chunk_path,
            "-filter_complex", filter_complex,
            "-f", "null", "-"
        ]
        
        startupinfo = None
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, startupinfo=startupinfo, text=True, encoding='utf-8', errors='replace')
        if process_setter:
            process_setter(process)
            
        output_log = []
        for line in process.stdout:
            output_log.append(line)
            
        process.wait()
        full_output = "".join(output_log)
        
        score = -1.0
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if 'pooled_metrics' in data and 'vmaf' in data['pooled_metrics']:
                        score = data['pooled_metrics']['vmaf']['mean']
                    elif 'VMAF score' in data:
                        score = data['VMAF score']
            except Exception as e:
                logging.error(f"Failed to parse VMAF JSON: {e}")
            finally:
                try:
                    os.remove(json_path)
                except:
                    pass
                    
        if score == -1.0:
            if "No such filter: 'libvmaf'" in full_output:
                logging.warning("libvmaf не встроен в эту сборку FFmpeg.")
                return -2.0
            logging.error(f"Ошибка расчета VMAF. Лог FFmpeg:\n{full_output}")
            
        return score