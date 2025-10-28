import subprocess
import json
import os
import platform
from pathlib import Path
from typing import Optional, Callable, List, Dict
from config import (OUTPUT_FORMATS, CODECS, TEMP_FIXED_VIDEO_SUFFIX,
COMPRESSED_VIDEO_SUFFIX, FFMPEG_PATH, FFPROBE_PATH,
DEFAULT_FPS_FIX, DEFAULT_FIX_CRF_H264, DEFAULT_FIX_CRF_H265, DEFAULT_FIX_CRF_VP9)


class VideoProcessor:
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
        print(f"[DEBUG] Executing FFmpeg command: {' '.join(cmd)}")
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
                except UnicodeDecodeError:
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
            print(f"[ERROR] FFmpeg failed with return code: {return_code}")
            print(f"[ERROR] Command: {' '.join(cmd)}")
            print(f"[ERROR] Error lines found:")
            for error_line in error_lines:
                print(f"[ERROR] {error_line}")
            
            if len(cmd) > 3 and cmd[1] == "-i":
                input_file = cmd[2]
                print(f"[ERROR] Detailed info about input file:")
                try:
                    probe_cmd = [self.ffprobe_path, "-v", "error", "-show_format", "-show_streams", input_file]
                    probe_result = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=10)
                    if probe_result.returncode == 0:
                        print(f"[ERROR] FFprobe output:\n{probe_result.stdout}")
                    else:
                        print(f"[ERROR] FFprobe failed: {probe_result.stderr}")
                except Exception as e:
                    print(f"[ERROR] Failed to get detailed info: {str(e)}")
            
            error_summary = "\n".join(full_output_message.strip().split('\n')[-15:])
            error_message = f"Ошибка FFmpeg (код {return_code}).\nЛог:\n{error_summary}\n\nДетальные ошибки:\n" + "\n".join(error_lines[-10:])
            print(error_message)
            return False, error_message
        else:
            print(f"[DEBUG] FFmpeg command completed successfully")
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

    def estimated_size_mb(self, video_bitrate: int, audio_bitrate: int, duration: float, crf: int, codec: str, needs_vfr_fix: bool = False, use_hardware: bool = False) -> float:
        if video_bitrate <= 0 or duration <= 0:
            print(f"[DEBUG] estimated_size_mb: Invalid input. video_bitrate={video_bitrate}, duration={duration}")
            return 0.0
        
        total_bitrate = video_bitrate + audio_bitrate
        base = (total_bitrate * duration) / 8 / (1024 * 1024)
        print(f"[DEBUG] estimated_size_mb: Video bitrate={video_bitrate} bit/s, Audio bitrate={audio_bitrate} bit/s, Total bitrate={total_bitrate} bit/s")
        print(f"[DEBUG] estimated_size_mb: Base size (MB): {base:.2f}")
        
        target_factor = self._calculate_compression_factor(crf, codec, use_hardware)
        print(f"[DEBUG] estimated_size_mb: Target CRF={crf}, Target factor={target_factor:.4f}")
        
        if needs_vfr_fix:
            fix_crf = 15 if codec == "libvpx-vp9" else (20 if codec == "libx265" else 18)
            fix_factor = self._calculate_compression_factor(fix_crf, codec, use_hardware)
            print(f"[DEBUG] estimated_size_mb: VFR-fix needed. Fix CRF={fix_crf}, Fix factor={fix_factor:.4f}")
            estimated_size = base * fix_factor * target_factor
            print(f"[DEBUG] estimated_size_mb: Estimated size with VFR-fix: {estimated_size:.2f} MB")
        else:
            estimated_size = base * target_factor
            print(f"[DEBUG] estimated_size_mb: Estimated size without VFR-fix: {estimated_size:.2f} MB")
        return max(0.1, estimated_size)

    def _calculate_compression_factor(self, crf: int, codec: str, use_hardware: bool = False) -> float:
        codec_info = CODECS.get(codec, None)
        if not codec_info:
            min_crf = 18
            max_crf = 35
            if crf <= min_crf:
                return 1.0
            elif crf >= max_crf:
                return 0.3
            else:
                crf_diff = crf - min_crf
                max_diff = max_crf - min_crf
                factor = 1.0 * (0.3 / 1.0) ** (crf_diff / max_diff)
                return max(0.3, factor)
        
        factor_dict = codec_info.get("factor", None)
        if factor_dict and crf in factor_dict:
            return factor_dict[crf]
        
        min_crf = codec_info["crf_min"]
        max_crf = codec_info["crf_max"]
        
        if crf <= min_crf:
            return 1.0
        elif crf >= max_crf:
            if codec == "libx264":
                return 0.3
            elif codec == "libx265":
                return 0.25
            elif codec == "libvpx-vp9":
                return 0.2
            else:
                return 0.3
        else:
            crf_diff = crf - min_crf
            max_diff = max_crf - min_crf
            
            if codec == "libx264":
                min_factor = 0.3
            elif codec == "libx265":
                min_factor = 0.25
            elif codec == "libvpx-vp9":
                min_factor = 0.2
            else:
                min_factor = 0.3
                
            factor = 1.0 * (min_factor / 1.0) ** (crf_diff / max_diff)
            return max(min_factor, factor)

    def get_video_info(self, input_path: str) -> dict:
        print(f"[DEBUG] Getting video info for: {input_path}")
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
                
                print(f"[ERROR] FFprobe failed with code {result.returncode}: {stderr_text}")
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
                print(f"[ERROR] No video stream found in file")
                return {"error": "Видеопоток не найден"}
            
            format_info = data.get("format", {})
            duration = float(format_info.get("duration", 0))
            
            try:
                size_bytes = os.path.getsize(input_path)
                print(f"[DEBUG] get_video_info: Actual file size from filesystem: {size_bytes} bytes")
            except Exception as e:
                print(f"[DEBUG] get_video_info: Error getting file size: {e}")
                size_bytes = int(format_info.get("size", 0))
            
            size_mb = size_bytes / (1024 * 1024)
            print(f"[DEBUG] get_video_info: File size in MB: {size_mb:.2f} MB")
            
            total_bitrate = int(format_info.get("bit_rate", 0))
            if total_bitrate == 0 and duration > 0:
                total_bitrate = int((size_bytes * 8) / duration)
            video_bitrate = int(video_stream.get("bit_rate", 0))
            if video_bitrate == 0:
                audio_streams = [s for s in data.get("streams", []) if s.get("codec_type") == "audio"]
                audio_bitrate = sum(int(s.get("bit_rate", 128000)) for s in audio_streams) if audio_streams else 128000
                video_bitrate = max(0, total_bitrate - audio_bitrate)
                print(f"[DEBUG] get_video_info: Used fallback for video_bitrate. Calculated: {video_bitrate} bit/s")
            audio_streams = [s for s in data.get("streams", []) if s.get("codec_type") == "audio"]
            audio_bitrate = sum(int(s.get("bit_rate", 128000)) for s in audio_streams) if audio_streams else 128000
            
            # Проверяем наличие субтитров
            subtitle_streams = [s for s in data.get("streams", []) if s.get("codec_type") == "subtitle"]
            has_subtitles = len(subtitle_streams) > 0
            
            print(f"[DEBUG] Video stream info:")
            print(f"[DEBUG]   Codec: {video_stream.get('codec_name', 'unknown')}")
            print(f"[DEBUG]   Resolution: {video_stream.get('width', 0)}x{video_stream.get('height', 0)}")
            print(f"[DEBUG]   Pixel format: {video_stream.get('pix_fmt', 'unknown')}")
            print(f"[DEBUG]   Frame rate: {video_stream.get('avg_frame_rate', 'unknown')}")
            print(f"[DEBUG]   Bitrate: {video_bitrate}")
            
            print(f"[DEBUG] Audio streams info:")
            for i, stream in enumerate(audio_streams):
                print(f"[DEBUG]   Stream {i}:")
                print(f"[DEBUG]     Codec: {stream.get('codec_name', 'unknown')}")
                print(f"[DEBUG]     Sample rate: {stream.get('sample_rate', 'unknown')}")
                print(f"[DEBUG]     Channels: {stream.get('channels', 0)}")
                print(f"[DEBUG]     Bitrate: {stream.get('bit_rate', 'unknown')}")
            
            print(f"[DEBUG] Subtitle streams info: {len(subtitle_streams)} found")
            
            fps_str = video_stream.get("avg_frame_rate", "0/1")
            num, den = map(int, fps_str.split('/'))
            fps = num / den if den != 0 else 0
            needs_vfr_fix = video_stream.get("r_frame_rate") in ["1000/1", "0/0"] or fps_str == "0/0"
            gpu_info = self.get_gpu_info()
            est_size = self.estimated_size_mb(video_bitrate, audio_bitrate, duration, 24, "libx264", needs_vfr_fix, False)
            
            is_hevc = video_stream.get("codec_name", "").lower() in ["hevc", "h265"]
            is_10bit = video_stream.get("pix_fmt", "").endswith("10le") or video_stream.get("pix_fmt", "").endswith("10be")
            
            return {
                "path": input_path,
                "duration": duration,
                "size_mb": size_mb,
                "video_bitrate": video_bitrate,
                "audio_bitrate": audio_bitrate,
                "estimated_size_mb": est_size,
                "gpu_info": gpu_info,
                "processing_mode": "GPU" if "Доступные GPU" in gpu_info else "CPU",
                "audio_tracks": self.get_audio_tracks(input_path),
                "width": int(video_stream.get("width", 0)),
                "height": int(video_stream.get("height", 0)),
                "fps": fps,
                "needs_vfr_fix": needs_vfr_fix,
                "is_hevc": is_hevc,
                "is_10bit": is_10bit,
                "video_codec": video_stream.get("codec_name", "unknown"),
                "pixel_format": video_stream.get("pix_fmt", "unknown"),
                "has_subtitles": has_subtitles
            }
        except Exception as e:
            print(f"[ERROR] Exception in get_video_info: {str(e)}")
            return {"error": f"Исключение при получении информации: {str(e)}"}

    def compress_video(self, input_path: str, output_format: str, codec: str, crf_value: int,
                    preset_value: str, force_vfr_fix: bool, use_hardware: bool = False, 
                    progress_callback: Optional[Callable] = None,
                    process_setter: Optional[Callable] = None,
                    output_dir: Optional[str] = None) -> str:
        print(f"[DEBUG] Starting compression:")
        print(f"[DEBUG]   Input: {input_path}")
        print(f"[DEBUG]   Output format: {output_format}")
        print(f"[DEBUG]   Codec: {codec}")
        print(f"[DEBUG]   CRF: {crf_value}")
        print(f"[DEBUG]   Preset: {preset_value}")
        print(f"[DEBUG]   Force VFR fix: {force_vfr_fix}")
        print(f"[DEBUG]   Hardware encoding: {use_hardware}")
        
        input_p = Path(input_path)
        if progress_callback: progress_callback(5, "Анализ видео...")
        video_info = self.get_video_info(input_path)
        if "error" in video_info: 
            print(f"[ERROR] Error getting video info: {video_info['error']}")
            raise Exception(video_info["error"])
        
        duration = video_info.get("duration", 0)
        if duration <= 0:
            print(f"[ERROR] Invalid video duration: {duration}")
            raise Exception("Некорректная длительность видео")
        
        needs_fix = force_vfr_fix or video_info["needs_vfr_fix"]
        
        if output_dir:
            output_path = Path(output_dir) / f"{input_p.stem}{COMPRESSED_VIDEO_SUFFIX}.{output_format}"
        else:
            output_path = input_p.with_name(f"{input_p.stem}{COMPRESSED_VIDEO_SUFFIX}.{output_format}")
        
        print(f"[DEBUG] Output file will be: {output_path}")
        
        if output_path.exists():
            try:
                output_path.unlink()
                print(f"[DEBUG] Deleted existing file: {output_path}")
            except Exception as e:
                print(f"[ERROR] Error deleting existing file: {e}")
        
        current_input = input_path
        try:
            if needs_fix:
                print(f"[DEBUG] VFR fix is needed")
                def vfr_progress(p, m): 
                    progress_callback(p, m) if progress_callback else None
                success, msg = self.fix_vfr_target_crf(current_input, str(output_path), output_format, codec, crf_value, preset_value, vfr_progress, duration, use_hardware, video_info, process_setter)
                if not success: 
                    print(f"[ERROR] VFR fix failed: {msg}")
                    raise Exception(f"Ошибка VFR-fix: {msg}")
                current_input = str(output_path)
            else:
                print(f"[DEBUG] No VFR fix needed, proceeding with compression")
                def compress_progress(p, m): 
                    progress_callback(p, m) if progress_callback else None
                success, msg = self.compress_video_core(current_input, str(output_path), output_format, codec, crf_value, preset_value, compress_progress, duration, video_info, use_hardware, process_setter)
                if not success: 
                    print(f"[ERROR] Compression failed: {msg}")
                    print(f"[DEBUG] Trying alternative method without subtitles...")
                    success, msg = self.compress_video_core_no_subtitles(current_input, str(output_path), output_format, codec, crf_value, preset_value, compress_progress, duration, video_info, use_hardware, process_setter)
                    if not success:
                        print(f"[ERROR] Alternative method failed: {msg}")
                        print(f"[DEBUG] Trying last method with full mapping but no data...")
                        success, msg = self.compress_video_core_full_map(current_input, str(output_path), output_format, codec, crf_value, preset_value, compress_progress, duration, video_info, use_hardware, process_setter)
                        if not success:
                            print(f"[ERROR] All methods failed: {msg}")
                            raise Exception(f"Ошибка сжатия: {msg}")
            if progress_callback: progress_callback(100, "Готово!")
            print(f"[DEBUG] Compression completed successfully")
            return str(output_path)
        except Exception as e:
            print(f"[ERROR] Exception during compression: {str(e)}")
            raise e

    def fix_vfr_target_crf(self, input_path: str, output_path: str,
                        output_format: str, codec: str, crf_value: int, preset_value: str,
                        progress_callback: Optional[Callable], duration_seconds: float, 
                        use_hardware: bool = False, video_info: dict = None,
                        process_setter: Optional[Callable] = None) -> tuple[bool, str]:
        print(f"[DEBUG] Starting VFR fix with compression:")
        print(f"[DEBUG]   Input: {input_path}")
        print(f"[DEBUG]   Output: {output_path}")
        print(f"[DEBUG]   Format: {output_format}")
        print(f"[DEBUG]   Codec: {codec}")
        print(f"[DEBUG]   CRF: {crf_value}")
        print(f"[DEBUG]   Preset: {preset_value}")
        
        gpu_info = self.get_gpu_info()
        has_nvenc = "NVIDIA NVENC" in gpu_info
        print(f"[DEBUG] GPU info: {gpu_info}")
        print(f"[DEBUG] Has NVENC: {has_nvenc}")
        
        cmd = [self.ffmpeg_path, "-y"]
        
        if video_info and video_info.get("is_hevc", False) and has_nvenc:
            cmd.extend(["-hwaccel", "cuda"])
            print(f"[DEBUG] Using CUDA hardware acceleration for HEVC decoding")
        
        cmd.extend(["-i", input_path])
        
        vf_filters = []
        vf_filters.append(f"fps={DEFAULT_FPS_FIX}")
        
        if video_info and video_info.get("is_10bit", False) and codec != "libx265":
            vf_filters.append("format=yuv420p")
            print(f"[DEBUG] Adding 10-bit to 8-bit conversion filter")
        
        if vf_filters:
            cmd.extend(["-vf", ",".join(vf_filters)])
            print(f"[DEBUG] Added video filters: {','.join(vf_filters)}")
        
        if codec == "libvpx-vp9":
            if use_hardware and has_nvenc:
                cmd.extend(["-c:v", "vp9_nvenc", "-crf", str(crf_value), "-b:v", "0"])
                print(f"[DEBUG] Using VP9 hardware encoder")
            else:
                cmd.extend(["-c:v", "libvpx-vp9", "-crf", str(crf_value), "-b:v", "0"])
                cmd.extend(["-deadline", "good", "-cpu-used", "2"])
                print(f"[DEBUG] Using VP9 software encoder")
            cmd.extend(["-c:a", "copy"])
            print(f"[DEBUG] Copying audio streams as-is")
        elif codec == "libx265":
            if use_hardware and has_nvenc:
                cmd.extend(["-c:v", "hevc_nvenc", "-crf", str(crf_value), "-preset", "p6", "-tune", "film"])
                print(f"[DEBUG] Using HEVC hardware encoder")
            else:
                cmd.extend(["-c:v", "libx265", "-crf", str(crf_value), "-preset", preset_value])
                print(f"[DEBUG] Using HEVC software encoder with preset: {preset_value}")
            cmd.extend(["-c:a", "copy"])
            print(f"[DEBUG] Copying audio streams as-is")
        else:  # libx264
            if use_hardware and has_nvenc:
                cmd.extend(["-c:v", "h264_nvenc", "-cq", str(crf_value), "-preset", "p6", "-tune", "film"])
                print(f"[DEBUG] Using H.264 hardware encoder")
            else:
                cmd.extend(["-c:v", "libx264", "-crf", str(crf_value), "-preset", preset_value])
                print(f"[DEBUG] Using H.264 software encoder with preset: {preset_value}")
            cmd.extend(["-c:a", "copy"])
            print(f"[DEBUG] Copying audio streams as-is")
        
        # Добавляем субтитры, только если они есть
        if video_info and video_info.get("has_subtitles", False):
            if output_format == "mp4":
                cmd.extend(["-c:s", "mov_text"])
                print(f"[DEBUG] Using mov_text for subtitles")
            else:
                cmd.extend(["-c:s", "copy"])
                print(f"[DEBUG] Copying subtitles as-is")
            
            cmd.extend(["-map", "0:V", "-map", "0:a", "-map", "0:s"])
            print(f"[DEBUG] Mapping video, audio and subtitle streams (excluding cover art)")
        else:
            cmd.extend(["-map", "0:V", "-map", "0:a"])
            print(f"[DEBUG] Mapping video and audio streams only (no subtitles found)")
        
        if output_format == "mp4":
            cmd.extend(["-movflags", "+faststart"])
            print(f"[DEBUG] Added faststart flag for MP4")
            
        cmd.extend(["-progress", "pipe:1", output_path])
        print(f"[DEBUG] Final command: {' '.join(cmd)}")
        
        return self._run_command_with_progress(cmd, progress_callback, duration_seconds, "VFR-fix+сжатие", process_setter)

    def compress_video_core(self, input_path: str, output_path: str, output_format: str, codec: str, crf_value: int,
                        preset_value: str, progress_callback: Optional[Callable], duration_seconds: float, 
                        video_info: dict = None, use_hardware: bool = False,
                        process_setter: Optional[Callable] = None) -> tuple[bool, str]:
        print(f"[DEBUG] Starting direct compression:")
        print(f"[DEBUG]   Input: {input_path}")
        print(f"[DEBUG]   Output: {output_path}")
        print(f"[DEBUG]   Format: {output_format}")
        print(f"[DEBUG]   Codec: {codec}")
        print(f"[DEBUG]   CRF: {crf_value}")
        print(f"[DEBUG]   Preset: {preset_value}")
        
        if video_info is None:
            video_info = self.get_video_info(input_path)
            if "error" in video_info:
                return False, video_info["error"]
        
        gpu_info = self.get_gpu_info()
        has_nvenc = "NVIDIA NVENC" in gpu_info
        print(f"[DEBUG] GPU info: {gpu_info}")
        print(f"[DEBUG] Has NVENC: {has_nvenc}")
        
        cmd = [self.ffmpeg_path, "-y"]
        
        if video_info.get("is_hevc", False) and has_nvenc:
            cmd.extend(["-hwaccel", "cuda"])
            print(f"[DEBUG] Using CUDA hardware acceleration for HEVC decoding")
        
        cmd.extend(["-i", input_path])
        
        vf_filters = []
        
        if video_info.get("is_10bit", False) and codec != "libx265":
            vf_filters.append("format=yuv420p")
            print(f"[DEBUG] Adding 10-bit to 8-bit conversion filter")
        
        if codec == "libx264" and not use_hardware:
            vf_filters.append("pad=ceil(iw/2)*2:ceil(ih/2)*2")
            print(f"[DEBUG] Adding pad filter for H.264")
        
        if vf_filters:
            cmd.extend(["-vf", ",".join(vf_filters)])
            print(f"[DEBUG] Added video filters: {','.join(vf_filters)}")
        
        if codec == "libvpx-vp9":
            if use_hardware and has_nvenc:
                cmd.extend(["-c:v", "vp9_nvenc", "-crf", str(crf_value), "-b:v", "0"])
                print(f"[DEBUG] Using VP9 hardware encoder")
            else:
                cmd.extend(["-c:v", "libvpx-vp9", "-crf", str(crf_value), "-b:v", "0"])
                cmd.extend(["-deadline", "good", "-cpu-used", "2"])
                print(f"[DEBUG] Using VP9 software encoder")
            cmd.extend(["-c:a", "aac", "-b:a", "320k"])
            print(f"[DEBUG] Converting audio to AAC 320k")
        elif codec == "libx265":
            if use_hardware and has_nvenc:
                cmd.extend(["-c:v", "hevc_nvenc", "-crf", str(crf_value), "-preset", "p6", "-tune", "film"])
                print(f"[DEBUG] Using HEVC hardware encoder")
            else:
                cmd.extend(["-c:v", "libx265", "-crf", str(crf_value), "-preset", preset_value])
                print(f"[DEBUG] Using HEVC software encoder with preset: {preset_value}")
            cmd.extend(["-c:a", "aac", "-b:a", "320k"])
            print(f"[DEBUG] Converting audio to AAC 320k")
        else:  # libx264
            if use_hardware and has_nvenc:
                cmd.extend([
                    "-c:v", "h264_nvenc",
                    "-cq", str(crf_value),
                    "-preset", "p6",
                    "-tune", "film",
                    "-spatial_aq", "1",
                    "-temporal_aq", "1",
                    "-rc-lookahead", "20",
                    "-aq-strength", "15"
                ])
                print(f"[DEBUG] Using H.264 hardware encoder")
            else:
                cmd.extend([
                    "-c:v", "libx264", 
                    "-crf", str(crf_value), 
                    "-preset", preset_value
                ])
                print(f"[DEBUG] Using H.264 software encoder with preset: {preset_value}")
            cmd.extend(["-c:a", "aac", "-b:a", "320k"])
            print(f"[DEBUG] Converting audio to AAC 320k")
            
        # Добавляем субтитры, только если они есть
        if video_info and video_info.get("has_subtitles", False):
            if output_format == "mp4":
                cmd.extend(["-c:s", "mov_text"])
                print(f"[DEBUG] Using mov_text for subtitles")
            else:
                cmd.extend(["-c:s", "copy"])
                print(f"[DEBUG] Copying subtitles as-is")
            
            cmd.extend(["-map", "0:V", "-map", "0:a", "-map", "0:s"])
            print(f"[DEBUG] Mapping video, audio and subtitle streams (excluding cover art)")
        else:
            cmd.extend(["-map", "0:V", "-map", "0:a"])
            print(f"[DEBUG] Mapping video and audio streams only (no subtitles found)")
        
        if output_format == "mp4":
            cmd.extend(["-movflags", "+faststart"])
            print(f"[DEBUG] Added faststart flag for MP4")
            
        cmd.extend(["-progress", "pipe:1", output_path])
        print(f"[DEBUG] Final command: {' '.join(cmd)}")
        
        return self._run_command_with_progress(cmd, progress_callback, duration_seconds, "Сжатие", process_setter)

    def compress_video_core_no_subtitles(self, input_path: str, output_path: str, output_format: str, codec: str, crf_value: int,
                        preset_value: str, progress_callback: Optional[Callable], duration_seconds: float, 
                        video_info: dict = None, use_hardware: bool = False,
                        process_setter: Optional[Callable] = None) -> tuple[bool, str]:
        print(f"[DEBUG] Starting compression without subtitles:")
        print(f"[DEBUG]   Input: {input_path}")
        print(f"[DEBUG]   Output: {output_path}")
        print(f"[DEBUG]   Format: {output_format}")
        print(f"[DEBUG]   Codec: {codec}")
        print(f"[DEBUG]   CRF: {crf_value}")
        print(f"[DEBUG]   Preset: {preset_value}")
        
        if video_info is None:
            video_info = self.get_video_info(input_path)
            if "error" in video_info:
                return False, video_info["error"]
        
        gpu_info = self.get_gpu_info()
        has_nvenc = "NVIDIA NVENC" in gpu_info
        print(f"[DEBUG] GPU info: {gpu_info}")
        print(f"[DEBUG] Has NVENC: {has_nvenc}")
        
        cmd = [self.ffmpeg_path, "-y"]
        
        if video_info.get("is_hevc", False) and has_nvenc:
            cmd.extend(["-hwaccel", "cuda"])
            print(f"[DEBUG] Using CUDA hardware acceleration for HEVC decoding")
        
        cmd.extend(["-i", input_path])
        
        vf_filters = []
        
        if video_info.get("is_10bit", False) and codec != "libx265":
            vf_filters.append("format=yuv420p")
            print(f"[DEBUG] Adding 10-bit to 8-bit conversion filter")
        
        if codec == "libx264" and not use_hardware:
            vf_filters.append("pad=ceil(iw/2)*2:ceil(ih/2)*2")
            print(f"[DEBUG] Adding pad filter for H.264")
        
        if vf_filters:
            cmd.extend(["-vf", ",".join(vf_filters)])
            print(f"[DEBUG] Added video filters: {','.join(vf_filters)}")
        
        if codec == "libvpx-vp9":
            if use_hardware and has_nvenc:
                cmd.extend(["-c:v", "vp9_nvenc", "-crf", str(crf_value), "-b:v", "0"])
                print(f"[DEBUG] Using VP9 hardware encoder")
            else:
                cmd.extend(["-c:v", "libvpx-vp9", "-crf", str(crf_value), "-b:v", "0"])
                cmd.extend(["-deadline", "good", "-cpu-used", "2"])
                print(f"[DEBUG] Using VP9 software encoder")
            cmd.extend(["-c:a", "aac", "-b:a", "320k"])
            print(f"[DEBUG] Converting audio to AAC 320k")
        elif codec == "libx265":
            if use_hardware and has_nvenc:
                cmd.extend(["-c:v", "hevc_nvenc", "-crf", str(crf_value), "-preset", "p6", "-tune", "film"])
                print(f"[DEBUG] Using HEVC hardware encoder")
            else:
                cmd.extend(["-c:v", "libx265", "-crf", str(crf_value), "-preset", preset_value])
                print(f"[DEBUG] Using HEVC software encoder with preset: {preset_value}")
            cmd.extend(["-c:a", "aac", "-b:a", "320k"])
            print(f"[DEBUG] Converting audio to AAC 320k")
        else:  # libx264
            if use_hardware and has_nvenc:
                cmd.extend([
                    "-c:v", "h264_nvenc",
                    "-cq", str(crf_value),
                    "-preset", "p6",
                    "-tune", "film",
                    "-spatial_aq", "1",
                    "-temporal_aq", "1",
                    "-rc-lookahead", "20",
                    "-aq-strength", "15"
                ])
                print(f"[DEBUG] Using H.264 hardware encoder")
            else:
                cmd.extend([
                    "-c:v", "libx264", 
                    "-crf", str(crf_value), 
                    "-preset", preset_value
                ])
                print(f"[DEBUG] Using H.264 software encoder with preset: {preset_value}")
            cmd.extend(["-c:a", "aac", "-b:a", "320k"])
            print(f"[DEBUG] Converting audio to AAC 320k")
            
        cmd.extend(["-map", "0:V", "-map", "0:a"])
        print(f"[DEBUG] Mapping video and audio streams only (excluding subtitles and cover art)")
        
        if output_format == "mp4":
            cmd.extend(["-movflags", "+faststart"])
            print(f"[DEBUG] Added faststart flag for MP4")
            
        cmd.extend(["-progress", "pipe:1", output_path])
        print(f"[DEBUG] Final command: {' '.join(cmd)}")
        
        return self._run_command_with_progress(cmd, progress_callback, duration_seconds, "Сжатие без субтитров", process_setter)

    def compress_video_core_full_map(self, input_path: str, output_path: str, output_format: str, codec: str, crf_value: int,
                        preset_value: str, progress_callback: Optional[Callable], duration_seconds: float, 
                        video_info: dict = None, use_hardware: bool = False,
                        process_setter: Optional[Callable] = None) -> tuple[bool, str]:
        print(f"[DEBUG] Starting compression with full mapping but no data:")
        print(f"[DEBUG]   Input: {input_path}")
        print(f"[DEBUG]   Output: {output_path}")
        print(f"[DEBUG]   Format: {output_format}")
        print(f"[DEBUG]   Codec: {codec}")
        print(f"[DEBUG]   CRF: {crf_value}")
        print(f"[DEBUG]   Preset: {preset_value}")
        
        if video_info is None:
            video_info = self.get_video_info(input_path)
            if "error" in video_info:
                return False, video_info["error"]
        
        gpu_info = self.get_gpu_info()
        has_nvenc = "NVIDIA NVENC" in gpu_info
        print(f"[DEBUG] GPU info: {gpu_info}")
        print(f"[DEBUG] Has NVENC: {has_nvenc}")
        
        cmd = [self.ffmpeg_path, "-y"]
        
        if video_info.get("is_hevc", False) and has_nvenc:
            cmd.extend(["-hwaccel", "cuda"])
            print(f"[DEBUG] Using CUDA hardware acceleration for HEVC decoding")
        
        cmd.extend(["-i", input_path])
        
        vf_filters = []
        
        if video_info.get("is_10bit", False) and codec != "libx265":
            vf_filters.append("format=yuv420p")
            print(f"[DEBUG] Adding 10-bit to 8-bit conversion filter")
        
        if codec == "libx264" and not use_hardware:
            vf_filters.append("pad=ceil(iw/2)*2:ceil(ih/2)*2")
            print(f"[DEBUG] Adding pad filter for H.264")
        
        if vf_filters:
            cmd.extend(["-vf", ",".join(vf_filters)])
            print(f"[DEBUG] Added video filters: {','.join(vf_filters)}")
        
        if codec == "libvpx-vp9":
            if use_hardware and has_nvenc:
                cmd.extend(["-c:v", "vp9_nvenc", "-crf", str(crf_value), "-b:v", "0"])
                print(f"[DEBUG] Using VP9 hardware encoder")
            else:
                cmd.extend(["-c:v", "libvpx-vp9", "-crf", str(crf_value), "-b:v", "0"])
                cmd.extend(["-deadline", "good", "-cpu-used", "2"])
                print(f"[DEBUG] Using VP9 software encoder")
            cmd.extend(["-c:a", "aac", "-b:a", "320k"])
            print(f"[DEBUG] Converting audio to AAC 320k")
        elif codec == "libx265":
            if use_hardware and has_nvenc:
                cmd.extend(["-c:v", "hevc_nvenc", "-crf", str(crf_value), "-preset", "p6", "-tune", "film"])
                print(f"[DEBUG] Using HEVC hardware encoder")
            else:
                cmd.extend(["-c:v", "libx265", "-crf", str(crf_value), "-preset", preset_value])
                print(f"[DEBUG] Using HEVC software encoder with preset: {preset_value}")
            cmd.extend(["-c:a", "aac", "-b:a", "320k"])
            print(f"[DEBUG] Converting audio to AAC 320k")
        else:  # libx264
            if use_hardware and has_nvenc:
                cmd.extend([
                    "-c:v", "h264_nvenc",
                    "-cq", str(crf_value),
                    "-preset", "p6",
                    "-tune", "film",
                    "-spatial_aq", "1",
                    "-temporal_aq", "1",
                    "-rc-lookahead", "20",
                    "-aq-strength", "15"
                ])
                print(f"[DEBUG] Using H.264 hardware encoder")
            else:
                cmd.extend([
                    "-c:v", "libx264", 
                    "-crf", str(crf_value), 
                    "-preset", preset_value
                ])
                print(f"[DEBUG] Using H.264 software encoder with preset: {preset_value}")
            cmd.extend(["-c:a", "aac", "-b:a", "320k"])
            print(f"[DEBUG] Converting audio to AAC 320k")
            
        cmd.extend(["-map", "0", "-map", "-0:d"])
        print(f"[DEBUG] Mapping all streams except data streams (cover art)")
        
        if output_format == "mp4":
            cmd.extend(["-movflags", "+faststart"])
            print(f"[DEBUG] Added faststart flag for MP4")
            
        cmd.extend(["-progress", "pipe:1", output_path])
        print(f"[DEBUG] Final command: {' '.join(cmd)}")
        
        return self._run_command_with_progress(cmd, progress_callback, duration_seconds, "Сжатие с полным маппингом", process_setter)