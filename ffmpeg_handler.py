"""
Модуль для работы с FFmpeg
"""
import subprocess
import json
import os
import platform
import logging
from pathlib import Path
from typing import Optional, Callable, List, Dict, Tuple
from config import (TEMP_FIXED_VIDEO_SUFFIX, COMPRESSED_VIDEO_SUFFIX, 
                    DEFAULT_FPS_FIX, FFMPEG_PATH, FFPROBE_PATH)


class FFmpegHandler:
    """Класс для работы с FFmpeg"""
    
    def __init__(self):
        self.ffmpeg_path = FFMPEG_PATH
        self.ffprobe_path = FFPROBE_PATH
    
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
        error_lines = []
        for line_bytes in iter(process.stdout.readline, b''):
            try:
                line = line_bytes.decode('utf-8', errors='replace')
            except UnicodeDecodeError:
                try:
                    line = line_bytes.decode('cp1251', errors='replace')
                except UnicodeDecodeDecodeError:
                    line = line_bytes.decode('ascii', errors='replace')
            
            output_log.append(line)
            if any(keyword in line.lower() for keyword in ['error', 'failed', 'invalid', 'cannot', 'unable']):
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
            logging.error(f"Error lines found:")
            for error_line in error_lines:
                logging.error(f"  {error_line}")
            
            if len(cmd) > 3 and cmd[1] == "-i":
                input_file = cmd[2]
                logging.error(f"Detailed info about input file:")
                try:
                    probe_cmd = [self.ffprobe_path, "-v", "error", "-show_format", "-show_streams", input_file]
                    probe_result = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=10)
                    if probe_result.returncode == 0:
                        logging.error(f"FFprobe output:\n{probe_result.stdout}")
                    else:
                        logging.error(f"FFprobe failed: {probe_result.stderr}")
                except Exception as e:
                    logging.error(f"Failed to get detailed info: {str(e)}")
            
            error_summary = "\n".join(full_output_message.strip().split('\n')[-15:])
            error_message = f"Ошибка FFmpeg (код {return_code}).\nЛог:\n{error_summary}\n\nДетальные ошибки:\n" + "\n".join(error_lines[-10:])
            logging.error(error_message)
            return False, error_message
        else:
            logging.debug(f"FFmpeg command completed successfully")
            return True, "Команда FFmpeg успешно выполнена."
    
    def get_gpu_info(self) -> str:
        try:
            cmd = [self.ffmpeg_path, "-hide_banner", "-encoders"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10, startupinfo=self._get_platform_specific_startupinfo())
            if result.returncode == 0:
                encoders = result.stdout
                gpu_encoders = []
                if "h264_nvenc" in encoders: gpu_encoders.append("NVIDIA NVENC (H.264)")
                if "hevc_nvenc" in encoders: gpu_encoders.append("NVIDIA NVENC (HEVC)")
                if "h265_nvenc" in encoders: gpu_encoders.append("NVIDIA NVENC (HEVC)")
                if "h264_amf" in encoders: gpu_encoders.append("AMD AMF (H.264)")
                if "hevc_amf" in encoders: gpu_encoders.append("AMD AMF (HEVC)")
                if "h264_qsv" in encoders: gpu_encoders.append("Intel QSV (H.264)")
                if "hevc_qsv" in encoders: gpu_encoders.append("Intel QSV (HEVC)")
                return f"Доступные GPU: {', '.join(gpu_encoders)}" if gpu_encoders else "GPU не обнаружены"
            return "Не удалось получить инфо о GPU"
        except Exception:
            return "Ошибка при получении инфо о GPU"
    
    def get_audio_tracks(self, input_path: str) -> List[Dict]:
        cmd = [self.ffprobe_path, "-v", "quiet", "-print_format", "json", "-show_streams", input_path]
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=30, startupinfo=self._get_platform_specific_startupinfo())
            if result.returncode == 0:
                try:
                    output_text = result.stdout.decode('utf-8', errors='replace')
                except UnicodeDecodeError:
                    try:
                        output_text = result.stdout.decode('cp1251', errors='replace')
                    except UnicodeDecodeError:
                        output_text = result.stdout.decode('ascii', errors='replace')
                
                data = json.loads(output_text)
                return [
                    {
                        "index": s.get("index", i),
                        "codec": s.get("codec_name", "n/a"),
                        "language": s.get("tags", {}).get("language", "und"),
                        "title": s.get("tags", {}).get("title", f"Audio {i+1}"),
                        "channels": s.get("channels", 0),
                        "sample_rate": s.get("sample_rate", "n/a"),
                        "bit_rate": s.get("bit_rate", "n/a"),
                    }
                    for i, s in enumerate(data.get("streams", [])) if s.get("codec_type") == "audio"
                ]
            return []
        except Exception:
            return []
    
    def get_video_info(self, input_path: str) -> dict:
        logging.debug(f"Getting video info for: {input_path}")
        cmd = [self.ffprobe_path, "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", input_path]
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=30, startupinfo=self._get_platform_specific_startupinfo())
            if result.returncode != 0: 
                try:
                    stderr_text = result.stderr.decode('utf-8', errors='replace')
                except UnicodeDecodeError:
                    try:
                        stderr_text = result.stderr.decode('cp1251', errors='replace')
                    except UnicodeDecodeError:
                        stderr_text = result.stderr.decode('ascii', errors='replace')
                
                logging.error(f"FFprobe failed with code {result.return_code}: {stderr_text}")
                return {"error": f"Ошибка ffprobe: {stderr_text}"}
            
            try:
                output_text = result.stdout.decode('utf-8', errors='replace')
            except UnicodeDecodeError:
                try:
                    output_text = result.stdout.decode('cp1251', errors='replace')
                except UnicodeDecodeError:
                    output_text = result.stdout.decode('ascii', errors='replace')
            
            data = json.loads(output_text)
            video_stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
            if not video_stream: 
                logging.error(f"No video stream found in file")
                return {"error": "Видеопоток не найден"}
            
            format_info = data.get("format", {})
            duration = float(format_info.get("duration", 0))
            
            try:
                size_bytes = os.path.getsize(input_path)
                logging.debug(f"get_video_info: Actual file size from filesystem: {size_bytes} bytes")
            except Exception as e:
                logging.debug(f"get_video_info: Error getting file size: {e}")
                size_bytes = int(format_info.get("size", 0))
            
            size_mb = size_bytes / (1024 * 1024)
            logging.debug(f"get_video_info: File size in MB: {size_mb:.2f} MB")
            
            total_bitrate = int(format_info.get("bit_rate", 0))
            if total_bitrate == 0 and duration > 0:
                total_bitrate = int((size_bytes * 8) / duration)
            video_bitrate = int(video_stream.get("bit_rate", 0))
            if video_bitrate == 0:
                audio_streams = [s for s in data.get("streams", []) if s.get("codec_type") == "audio"]
                audio_bitrate = sum(int(s.get("bit_rate", 128000)) for s in audio_streams) if audio_streams else 128000
                video_bitrate = max(0, total_bitrate - audio_bitrate)
                logging.debug(f"get_video_info: Used fallback for video_bitrate. Calculated: {video_bitrate} bit/s")
            audio_streams = [s for s in data.get("streams", []) if s.get("codec_type") == "audio"]
            audio_bitrate = sum(int(s.get("bit_rate", 128000)) for s in audio_streams) if audio_streams else 128000
            
            # Проверяем наличие субтитров
            subtitle_streams = [s for s in data.get("streams", []) if s.get("codec_type") == "subtitle"]
            has_subtitles = len(subtitle_streams) > 0
            
            logging.debug(f"Video stream info:")
            logging.debug(f"  Codec: {video_stream.get('codec_name', 'unknown')}")
            logging.debug(f"  Resolution: {video_stream.get('width', 0)}x{video_stream.get('height', 0)}")
            logging.debug(f"  Pixel format: {video_stream.get('pix_fmt', 'unknown')}")
            logging.debug(f"  Frame rate: {video_stream.get('avg_frame_rate', 'unknown')}")
            logging.debug(f"  Bitrate: {video_bitrate}")
            
            logging.debug(f"Audio streams info:")
            for i, stream in enumerate(audio_streams):
                logging.debug(f"  Stream {i}:")
                logging.debug(f"    Codec: {stream.get('codec_name', 'unknown')}")
                logging.debug(f"    Sample rate: {stream.get('sample_rate', 'unknown')}")
                logging.debug(f"    Channels: {stream.get('channels', 0)}")
                logging.debug(f"    Bitrate: {stream.get('bit_rate', 'unknown')}")
            
            logging.debug(f"Subtitle streams info: {len(subtitle_streams)} found")
            
            fps_str = video_stream.get("avg_frame_rate", "0/1")
            num, den = map(int, fps_str.split('/'))
            fps = num / den if den != 0 else 0
            needs_vfr_fix = video_stream.get("r_frame_rate") in ["1000/1", "0/0"] or fps_str == "0/0"
            
            is_hevc = video_stream.get("codec_name", "").lower() in ["hevc", "h265"]
            is_10bit = video_stream.get("pix_fmt", "").endswith("10le") or video_stream.get("pix_fmt", "").endswith("10be")
            
            return {
                "path": input_path,
                "duration": duration,
                "size_mb": size_mb,
                "video_bitrate": video_bitrate,
                "audio_bitrate": audio_bitrate,
                "width": int(video_stream.get("width", 0)),
                "height": int(video_stream.get("height", 0)),
                "fps": fps,
                "needs_vfr_fix": needs_vfr_fix,
                "is_hevc": is_hevc,
                "is_10bit": is_10bit,
                "video_codec": video_stream.get("codec_name", "unknown"),
                "pixel_format": video_stream.get("pix_fmt", "unknown"),
                "has_subtitles": has_subtitles,
                "audio_tracks": self.get_audio_tracks(input_path)
            }
        except Exception as e:
            logging.error(f"Exception in get_video_info: {str(e)}")
            return {"error": f"Исключение при получении информации: {str(e)}"}
    
    def fix_vfr_target_crf(self, input_path: str, output_path: str,
                          output_format: str, codec: str, crf_value: int, preset_value: str,
                          progress_callback: Optional[Callable], duration_seconds: float, 
                          use_hardware: bool = False, video_info: dict = None,
                          process_setter: Optional[Callable] = None) -> tuple[bool, str]:
        logging.debug(f"Starting VFR fix with compression:")
        logging.debug(f"  Input: {input_path}")
        logging.debug(f"  Output: {output_path}")
        logging.debug(f"  Format: {output_format}")
        logging.debug(f"  Codec: {codec}")
        logging.debug(f"  CRF: {crf_value}")
        logging.debug(f"  Preset: {preset_value}")
        
        gpu_info = self.get_gpu_info()
        has_nvenc = "NVIDIA NVENC" in gpu_info
        logging.debug(f"GPU info: {gpu_info}")
        logging.debug(f"Has NVENC: {has_nvenc}")
        
        cmd = [self.ffmpeg_path, "-y"]
        
        if video_info and video_info.get("is_hevc", False) and has_nvenc:
            cmd.extend(["-hwaccel", "cuda"])
            logging.debug(f"Using CUDA hardware acceleration for HEVC decoding")
        
        cmd.extend(["-i", input_path])
        
        vf_filters = []
        vf_filters.append(f"fps={DEFAULT_FPS_FIX}")
        
        if video_info and video_info.get("is_10bit", False) and codec != "libx265":
            vf_filters.append("format=yuv420p")
            logging.debug(f"Adding 10-bit to 8-bit conversion filter")
        
        if vf_filters:
            cmd.extend(["-vf", ",".join(vf_filters)])
            logging.debug(f"Added video filters: {','.join(vf_filters)}")
        
        if codec == "libvpx-vp9":
            if use_hardware and has_nvenc:
                cmd.extend(["-c:v", "vp9_nvenc", "-crf", str(crf_value), "-b:v", "0"])
                logging.debug(f"Using VP9 hardware encoder")
            else:
                cmd.extend(["-c:v", "libvpx-vp9", "-crf", str(crf_value), "-b:v", "0"])
                cmd.extend(["-deadline", "good", "-cpu-used", "2"])
                logging.debug(f"Using VP9 software encoder")
            cmd.extend(["-c:a", "copy"])
            logging.debug(f"Copying audio streams as-is")
        elif codec == "libx265":
            if use_hardware and has_nvenc:
                cmd.extend(["-c:v", "hevc_nvenc", "-crf", str(crf_value), "-preset", "p6", "-tune", "ll"])
                logging.debug(f"Using HEVC hardware encoder with tune=ll")
            else:
                cmd.extend(["-c:v", "libx265", "-crf", str(crf_value), "-preset", preset_value])
                logging.debug(f"Using HEVC software encoder with preset: {preset_value}")
            cmd.extend(["-c:a", "copy"])
            logging.debug(f"Copying audio streams as-is")
        else:  # libx264
            if use_hardware and has_nvenc:
                cmd.extend(["-c:v", "h264_nvenc", "-cq", str(crf_value), "-preset", "p6", "-tune", "ll"])
                logging.debug(f"Using H.264 hardware encoder with tune=ll")
            else:
                cmd.extend(["-c:v", "libx264", "-crf", str(crf_value), "-preset", preset_value])
                logging.debug(f"Using H.264 software encoder with preset: {preset_value}")
            cmd.extend(["-c:a", "copy"])
            logging.debug(f"Copying audio streams as-is")
        
        # Добавляем субтитры, только если они есть
        if video_info and video_info.get("has_subtitles", False):
            if output_format == "mp4":
                cmd.extend(["-c:s", "mov_text"])
                logging.debug(f"Using mov_text for subtitles")
            else:
                cmd.extend(["-c:s", "copy"])
                logging.debug(f"Copying subtitles as-is")
            
            cmd.extend(["-map", "0:V", "-map", "0:a", "-map", "0:s"])
            logging.debug(f"Mapping video, audio and subtitle streams (excluding cover art)")
        else:
            cmd.extend(["-map", "0:V", "-map", "0:a"])
            logging.debug(f"Mapping video and audio streams only (no subtitles found)")
        
        if output_format == "mp4":
            cmd.extend(["-movflags", "+faststart"])
            logging.debug(f"Added faststart flag for MP4")
            
        cmd.extend(["-progress", "pipe:1", output_path])
        logging.debug(f"Final command: {' '.join(cmd)}")
        
        return self._run_command_with_progress(cmd, progress_callback, duration_seconds, "VFR-fix+сжатие", process_setter)
    
    def compress_video_core(self, input_path: str, output_path: str, output_format: str, codec: str, crf_value: int,
                           preset_value: str, progress_callback: Optional[Callable], duration_seconds: float, 
                           video_info: dict = None, use_hardware: bool = False,
                           process_setter: Optional[Callable] = None) -> tuple[bool, str]:
        logging.debug(f"Starting direct compression:")
        logging.debug(f"  Input: {input_path}")
        logging.debug(f"  Output: {output_path}")
        logging.debug(f"  Format: {output_format}")
        logging.debug(f"  Codec: {codec}")
        logging.debug(f"  CRF: {crf_value}")
        logging.debug(f"  Preset: {preset_value}")
        
        if video_info is None:
            video_info = self.get_video_info(input_path)
            if "error" in video_info:
                return False, video_info["error"]
        
        gpu_info = self.get_gpu_info()
        has_nvenc = "NVIDIA NVENC" in gpu_info
        logging.debug(f"GPU info: {gpu_info}")
        logging.debug(f"Has NVENC: {has_nvenc}")
        
        cmd = [self.ffmpeg_path, "-y"]
        
        if video_info.get("is_hevc", False) and has_nvenc:
            cmd.extend(["-hwaccel", "cuda"])
            logging.debug(f"Using CUDA hardware acceleration for HEVC decoding")
        
        cmd.extend(["-i", input_path])
        
        vf_filters = []
        
        if video_info.get("is_10bit", False) and codec != "libx265":
            vf_filters.append("format=yuv420p")
            logging.debug(f"Adding 10-bit to 8-bit conversion filter")
        
        if codec == "libx264" and not use_hardware:
            vf_filters.append("pad=ceil(iw/2)*2:ceil(ih/2)*2")
            logging.debug(f"Adding pad filter for H.264")
        
        if vf_filters:
            cmd.extend(["-vf", ",".join(vf_filters)])
            logging.debug(f"Added video filters: {','.join(vf_filters)}")
        
        if codec == "libvpx-vp9":
            if use_hardware and has_nvenc:
                cmd.extend(["-c:v", "vp9_nvenc", "-crf", str(crf_value), "-b:v", "0"])
                logging.debug(f"Using VP9 hardware encoder")
            else:
                cmd.extend(["-c:v", "libvpx-vp9", "-crf", str(crf_value), "-b:v", "0"])
                cmd.extend(["-deadline", "good", "-cpu-used", "2"])
                logging.debug(f"Using VP9 software encoder")
            cmd.extend(["-c:a", "aac", "-b:a", "192k"]) # Изменено с 320k на 192k
            logging.debug(f"Converting audio to AAC 192k")
        elif codec == "libx265":
            if use_hardware and has_nvenc:
                cmd.extend(["-c:v", "hevc_nvenc", "-crf", str(crf_value), "-preset", "p6", "-tune", "ll"])
                logging.debug(f"Using HEVC hardware encoder with tune=ll")
            else:
                cmd.extend(["-c:v", "libx265", "-crf", str(crf_value), "-preset", preset_value])
                logging.debug(f"Using HEVC software encoder with preset: {preset_value}")
            cmd.extend(["-c:a", "aac", "-b:a", "192k"]) # Изменено с 320k на 192k
            logging.debug(f"Converting audio to AAC 192k")
        else:  # libx264
            if use_hardware and has_nvenc:
                cmd.extend([
                    "-c:v", "h264_nvenc",
                    "-cq", str(crf_value),
                    "-preset", "p6",
                    "-tune", "ll",
                    "-spatial_aq", "1",
                    "-temporal_aq", "1",
                    "-rc-lookahead", "20",
                    "-aq-strength", "15"
                ])
                logging.debug(f"Using H.264 hardware encoder with tune=ll")
            else:
                cmd.extend([
                    "-c:v", "libx264", 
                    "-crf", str(crf_value), 
                    "-preset", preset_value
                ])
                logging.debug(f"Using H.264 software encoder with preset: {preset_value}")
            cmd.extend(["-c:a", "aac", "-b:a", "192k"]) # Изменено с 320k на 192k
            logging.debug(f"Converting audio to AAC 192k")
            
        # Добавляем субтитры, только если они есть
        if video_info and video_info.get("has_subtitles", False):
            if output_format == "mp4":
                cmd.extend(["-c:s", "mov_text"])
                logging.debug(f"Using mov_text for subtitles")
            else:
                cmd.extend(["-c:s", "copy"])
                logging.debug(f"Copying subtitles as-is")
            
            cmd.extend(["-map", "0:V", "-map", "0:a", "-map", "0:s"])
            logging.debug(f"Mapping video, audio and subtitle streams (excluding cover art)")
        else:
            cmd.extend(["-map", "0:V", "-map", "0:a"])
            logging.debug(f"Mapping video and audio streams only (no subtitles found)")
        
        if output_format == "mp4":
            cmd.extend(["-movflags", "+faststart"])
            logging.debug(f"Added faststart flag for MP4")
            
        cmd.extend(["-progress", "pipe:1", output_path])
        logging.debug(f"Final command: {' '.join(cmd)}")
        
        return self._run_command_with_progress(cmd, progress_callback, duration_seconds, "Сжатие", process_setter)
    
    def compress_video_core_no_subtitles(self, input_path: str, output_path: str, output_format: str, codec: str, crf_value: int,
                                        preset_value: str, progress_callback: Optional[Callable], duration_seconds: float, 
                                        video_info: dict = None, use_hardware: bool = False,
                                        process_setter: Optional[Callable] = None) -> tuple[bool, str]:
        logging.debug(f"Starting compression without subtitles:")
        logging.debug(f"  Input: {input_path}")
        logging.debug(f"  Output: {output_path}")
        logging.debug(f"  Format: {output_format}")
        logging.debug(f"  Codec: {codec}")
        logging.debug(f"  CRF: {crf_value}")
        logging.debug(f"  Preset: {preset_value}")
        
        if video_info is None:
            video_info = self.get_video_info(input_path)
            if "error" in video_info:
                return False, video_info["error"]
        
        gpu_info = self.get_gpu_info()
        has_nvenc = "NVIDIA NVENC" in gpu_info
        logging.debug(f"GPU info: {gpu_info}")
        logging.debug(f"Has NVENC: {has_nvenc}")
        
        cmd = [self.ffmpeg_path, "-y"]
        
        if video_info.get("is_hevc", False) and has_nvenc:
            cmd.extend(["-hwaccel", "cuda"])
            logging.debug(f"Using CUDA hardware acceleration for HEVC decoding")
        
        cmd.extend(["-i", input_path])
        
        vf_filters = []
        
        if video_info.get("is_10bit", False) and codec != "libx265":
            vf_filters.append("format=yuv420p")
            logging.debug(f"Adding 10-bit to 8-bit conversion filter")
        
        if codec == "libx264" and not use_hardware:
            vf_filters.append("pad=ceil(iw/2)*2:ceil(ih/2)*2")
            logging.debug(f"Adding pad filter for H.264")
        
        if vf_filters:
            cmd.extend(["-vf", ",".join(vf_filters)])
            logging.debug(f"Added video filters: {','.join(vf_filters)}")
        
        if codec == "libvpx-vp9":
            if use_hardware and has_nvenc:
                cmd.extend(["-c:v", "vp9_nvenc", "-crf", str(crf_value), "-b:v", "0"])
                logging.debug(f"Using VP9 hardware encoder")
            else:
                cmd.extend(["-c:v", "libvpx-vp9", "-crf", str(crf_value), "-b:v", "0"])
                cmd.extend(["-deadline", "good", "-cpu-used", "2"])
                logging.debug(f"Using VP9 software encoder")
            cmd.extend(["-c:a", "aac", "-b:a", "192k"]) # Изменено с 320k на 192k
            logging.debug(f"Converting audio to AAC 192k")
        elif codec == "libx265":
            if use_hardware and has_nvenc:
                cmd.extend(["-c:v", "hevc_nvenc", "-crf", str(crf_value), "-preset", "p6", "-tune", "ll"])
                logging.debug(f"Using HEVC hardware encoder with tune=ll")
            else:
                cmd.extend(["-c:v", "libx265", "-crf", str(crf_value), "-preset", preset_value])
                logging.debug(f"Using HEVC software encoder with preset: {preset_value}")
            cmd.extend(["-c:a", "aac", "-b:a", "192k"]) # Изменено с 320k на 192k
            logging.debug(f"Converting audio to AAC 192k")
        else:  # libx264
            if use_hardware and has_nvenc:
                cmd.extend([
                    "-c:v", "h264_nvenc",
                    "-cq", str(crf_value),
                    "-preset", "p6",
                    "-tune", "ll",
                    "-spatial_aq", "1",
                    "-temporal_aq", "1",
                    "-rc-lookahead", "20",
                    "-aq-strength", "15"
                ])
                logging.debug(f"Using H.264 hardware encoder with tune=ll")
            else:
                cmd.extend([
                    "-c:v", "libx264", 
                    "-crf", str(crf_value), 
                    "-preset", preset_value
                ])
                logging.debug(f"Using H.264 software encoder with preset: {preset_value}")
            cmd.extend(["-c:a", "aac", "-b:a", "192k"]) # Изменено с 320k на 192k
            logging.debug(f"Converting audio to AAC 192k")
            
        cmd.extend(["-map", "0:V", "-map", "0:a"])
        logging.debug(f"Mapping video and audio streams only (excluding subtitles and cover art)")
        
        if output_format == "mp4":
            cmd.extend(["-movflags", "+faststart"])
            logging.debug(f"Added faststart flag for MP4")
            
        cmd.extend(["-progress", "pipe:1", output_path])
        logging.debug(f"Final command: {' '.join(cmd)}")
        
        return self._run_command_with_progress(cmd, progress_callback, duration_seconds, "Сжатие без субтитров", process_setter)
    
    def compress_video_core_full_map(self, input_path: str, output_path: str, output_format: str, codec: str, crf_value: int,
                                     preset_value: str, progress_callback: Optional[Callable], duration_seconds: float, 
                                     video_info: dict = None, use_hardware: bool = False,
                                     process_setter: Optional[Callable] = None) -> tuple[bool, str]:
        logging.debug(f"Starting compression with full mapping but no data:")
        logging.debug(f"  Input: {input_path}")
        logging.debug(f"  Output: {output_path}")
        logging.debug(f"  Format: {output_format}")
        logging.debug(f"  Codec: {codec}")
        logging.debug(f"  CRF: {crf_value}")
        logging.debug(f"  Preset: {preset_value}")
        
        if video_info is None:
            video_info = self.get_video_info(input_path)
            if "error" in video_info:
                return False, video_info["error"]
        
        gpu_info = self.get_gpu_info()
        has_nvenc = "NVIDIA NVENC" in gpu_info
        logging.debug(f"GPU info: {gpu_info}")
        logging.debug(f"Has NVENC: {has_nvenc}")
        
        cmd = [self.ffmpeg_path, "-y"]
        
        if video_info.get("is_hevc", False) and has_nvenc:
            cmd.extend(["-hwaccel", "cuda"])
            logging.debug(f"Using CUDA hardware acceleration for HEVC decoding")
        
        cmd.extend(["-i", input_path])
        
        vf_filters = []
        
        if video_info.get("is_10bit", False) and codec != "libx265":
            vf_filters.append("format=yuv420p")
            logging.debug(f"Adding 10-bit to 8-bit conversion filter")
        
        if codec == "libx264" and not use_hardware:
            vf_filters.append("pad=ceil(iw/2)*2:ceil(ih/2)*2")
            logging.debug(f"Adding pad filter for H.264")
        
        if vf_filters:
            cmd.extend(["-vf", ",".join(vf_filters)])
            logging.debug(f"Added video filters: {','.join(vf_filters)}")
        
        if codec == "libvpx-vp9":
            if use_hardware and has_nvenc:
                cmd.extend(["-c:v", "vp9_nvenc", "-crf", str(crf_value), "-b:v", "0"])
                logging.debug(f"Using VP9 hardware encoder")
            else:
                cmd.extend(["-c:v", "libvpx-vp9", "-crf", str(crf_value), "-b:v", "0"])
                cmd.extend(["-deadline", "good", "-cpu-used", "2"])
                logging.debug(f"Using VP9 software encoder")
            cmd.extend(["-c:a", "aac", "-b:a", "192k"]) # Изменено с 320k на 192k
            logging.debug(f"Converting audio to AAC 192k")
        elif codec == "libx265":
            if use_hardware and has_nvenc:
                cmd.extend(["-c:v", "hevc_nvenc", "-crf", str(crf_value), "-preset", "p6", "-tune", "ll"])
                logging.debug(f"Using HEVC hardware encoder with tune=ll")
            else:
                cmd.extend(["-c:v", "libx265", "-crf", str(crf_value), "-preset", preset_value])
                logging.debug(f"Using HEVC software encoder with preset: {preset_value}")
            cmd.extend(["-c:a", "aac", "-b:a", "192k"]) # Изменено с 320k на 192k
            logging.debug(f"Converting audio to AAC 192k")
        else:  # libx264
            if use_hardware and has_nvenc:
                cmd.extend([
                    "-c:v", "h264_nvenc",
                    "-cq", str(crf_value),
                    "-preset", "p6",
                    "-tune", "ll",
                    "-spatial_aq", "1",
                    "-temporal_aq", "1",
                    "-rc-lookahead", "20",
                    "-aq-strength", "15"
                ])
                logging.debug(f"Using H.264 hardware encoder with tune=ll")
            else:
                cmd.extend([
                    "-c:v", "libx264", 
                    "-crf", str(crf_value), 
                    "-preset", preset_value
                ])
                logging.debug(f"Using H.264 software encoder with preset: {preset_value}")
            cmd.extend(["-c:a", "aac", "-b:a", "192k"]) # Изменено с 320k на 192k
            logging.debug(f"Converting audio to AAC 192k")
            
        cmd.extend(["-map", "0", "-map", "-0:d"])
        logging.debug(f"Mapping all streams except data streams (cover art)")
        
        if output_format == "mp4":
            cmd.extend(["-movflags", "+faststart"])
            logging.debug(f"Added faststart flag for MP4")
            
        cmd.extend(["-progress", "pipe:1", output_path])
        logging.debug(f"Final command: {' '.join(cmd)}")
        
        return self._run_command_with_progress(cmd, progress_callback, duration_seconds, "Сжатие с полным маппингом", process_setter)