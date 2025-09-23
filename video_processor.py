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
    def __init__(self):  # Исправлено: __init__ вместо init
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
            universal_newlines=True,
            startupinfo=startupinfo,
            encoding='utf-8',
            errors='replace'
        )
        
        # Передаем процесс в WorkerThread для возможности остановки
        if process_setter:
            process_setter(process)
        
        output_log = []
        error_lines = []
        for line in iter(process.stdout.readline, ''):
            output_log.append(line)
            # Сохраняем строки с ошибками для детального анализа
            if any(keyword in line.lower() for keyword in ['error', 'failed', 'invalid', 'cannot', 'unable']):
                error_lines.append(line.strip())
            if progress_callback and duration_seconds:
                percent = self._parse_ffmpeg_progress_line(line, duration_seconds)
                if percent != -1:
                    progress_callback(percent, f"{stage_name}: {percent}%")
        process.stdout.close()
        return_code = process.wait()
        full_output_message = "".join(output_log)
        
        # Детальное логирование при ошибке
        if return_code != 0:
            print(f"[ERROR] FFmpeg failed with return code: {return_code}")
            print(f"[ERROR] Command: {' '.join(cmd)}")
            print(f"[ERROR] Error lines found:")
            for error_line in error_lines:
                print(f"[ERROR] {error_line}")
            
            # Дополнительная информация о контейнере и потоках
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
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, startupinfo=self._get_platform_specific_startupinfo())
            if result.returncode == 0:
                data = json.loads(result.stdout)
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
        """
        Рассчитывает примерный размер сжатого файла.
        Использует битрейт видеопотока из ffprobe для более точной базы.
        """
        if video_bitrate <= 0 or duration <= 0:
            print(f"[DEBUG] estimated_size_mb: Invalid input. video_bitrate={video_bitrate}, duration={duration}")
            return 0.0
        # Базовый размер на основе битрейта видео и аудио
        total_bitrate = video_bitrate + audio_bitrate
        base = (total_bitrate * duration) / 8 / (1024 * 1024)
        print(f"[DEBUG] estimated_size_mb: Video bitrate={video_bitrate} bit/s, Audio bitrate={audio_bitrate} bit/s, Total bitrate={total_bitrate} bit/s")
        print(f"[DEBUG] estimated_size_mb: Base size (MB): {base:.2f}")
        # Рассчитываем коэффициент сжатия для целевого CRF
        target_factor = self._calculate_compression_factor(crf, codec, use_hardware)
        print(f"[DEBUG] estimated_size_mb: Target CRF={crf}, Target factor={target_factor:.4f}")
        if needs_vfr_fix:
            # Для VFR-fix: предполагаем минимальные потери при конвертации в CFR
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
        """
        Рассчитывает коэффициент сжатия на основе CRF и кодека.
        """
        codec_info = CODECS.get(codec, None)
        if not codec_info:
            # Если кодек не найден, используем стандартные значения для H.264
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
        
        # Используем фактор из словаря CODECS, если он доступен
        factor_dict = codec_info.get("factor", None)
        if factor_dict and crf in factor_dict:
            return factor_dict[crf]
        
        # Если фактор не найден в словаре, рассчитываем его
        min_crf = codec_info["crf_min"]
        max_crf = codec_info["crf_max"]
        
        if crf <= min_crf:
            return 1.0
        elif crf >= max_crf:
            # Разные минимальные факторы для разных кодеков
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
            
            # Разные минимальные факторы для разных кодеков
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
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, startupinfo=self._get_platform_specific_startupinfo())
            if result.returncode != 0: 
                print(f"[ERROR] FFprobe failed with code {result.returncode}: {result.stderr}")
                return {"error": f"Ошибка ffprobe: {result.stderr}"}
            
            data = json.loads(result.stdout)
            video_stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
            if not video_stream: 
                print(f"[ERROR] No video stream found in file")
                return {"error": "Видеопоток не найден"}
            
            format_info = data.get("format", {})
            duration = float(format_info.get("duration", 0))
            
            # Получаем точный размер файла напрямую из файловой системы
            try:
                size_bytes = os.path.getsize(input_path)
                print(f"[DEBUG] get_video_info: Actual file size from filesystem: {size_bytes} bytes")
            except Exception as e:
                print(f"[DEBUG] get_video_info: Error getting file size: {e}")
                size_bytes = int(format_info.get("size", 0))
            
            size_mb = size_bytes / (1024 * 1024)
            print(f"[DEBUG] get_video_info: File size in MB: {size_mb:.2f} MB")
            
            # Получаем битрейт из формата, если он доступен
            total_bitrate = int(format_info.get("bit_rate", 0))
            # Если битрейт в формате не указан, рассчитываем его вручную
            if total_bitrate == 0 and duration > 0:
                total_bitrate = int((size_bytes * 8) / duration)
            # Получаем битрейт из видеопотока, если он доступен
            video_bitrate = int(video_stream.get("bit_rate", 0))
            # Если битрейт видео не указан, рассчитываем его
            if video_bitrate == 0:
                # Получаем все аудио потоки и их битрейты
                audio_streams = [s for s in data.get("streams", []) if s.get("codec_type") == "audio"]
                audio_bitrate = sum(int(s.get("bit_rate", 128000)) for s in audio_streams) if audio_streams else 128000
                # Рассчитываем битрейт видео, вычитая аудио битрейт из общего
                video_bitrate = max(0, total_bitrate - audio_bitrate)
                print(f"[DEBUG] get_video_info: Used fallback for video_bitrate. Calculated: {video_bitrate} bit/s")
            # Получаем аудио-битрейт для оценки
            audio_streams = [s for s in data.get("streams", []) if s.get("codec_type") == "audio"]
            audio_bitrate = sum(int(s.get("bit_rate", 128000)) for s in audio_streams) if audio_streams else 128000
            
            # Выводим детальную информацию о потоках для диагностики
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
            
            fps_str = video_stream.get("avg_frame_rate", "0/1")
            num, den = map(int, fps_str.split('/'))
            fps = num / den if den != 0 else 0
            needs_vfr_fix = video_stream.get("r_frame_rate") in ["1000/1", "0/0"] or fps_str == "0/0"
            gpu_info = self.get_gpu_info()
            # Рассчитываем оценку, используя новый метод
            est_size = self.estimated_size_mb(video_bitrate, audio_bitrate, duration, 24, "libx264", needs_vfr_fix, False)
            
            # Проверяем, является ли видео HEVC
            is_hevc = video_stream.get("codec_name", "").lower() in ["hevc", "h265"]
            
            # Проверяем, является ли видео 10-битным
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
            }
        except Exception as e:
            print(f"[ERROR] Exception in get_video_info: {str(e)}")
            return {"error": f"Исключение при получении информации: {str(e)}"}

    def compress_video(self, input_path: str, output_format: str, codec: str, crf_value: int,
                    force_vfr_fix: bool, use_hardware: bool = False, 
                    progress_callback: Optional[Callable] = None,
                    process_setter: Optional[Callable] = None) -> str:
        print(f"[DEBUG] Starting compression:")
        print(f"[DEBUG]   Input: {input_path}")
        print(f"[DEBUG]   Output format: {output_format}")
        print(f"[DEBUG]   Codec: {codec}")
        print(f"[DEBUG]   CRF: {crf_value}")
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
        # Формируем имя выходного файла
        output_file = input_p.with_name(f"{input_p.stem}{COMPRESSED_VIDEO_SUFFIX}.{output_format}")
        print(f"[DEBUG] Output file will be: {output_file}")
        
        # Проверяем, существует ли файл, и если да - удаляем его
        if output_file.exists():
            try:
                output_file.unlink()
                print(f"[DEBUG] Deleted existing file: {output_file}")
            except Exception as e:
                print(f"[ERROR] Error deleting existing file: {e}")
        
        current_input = input_path
        try:
            if needs_fix:
                print(f"[DEBUG] VFR fix is needed")
                def vfr_progress(p, m): 
                    progress_callback(10 + int(p * 0.4), m) if progress_callback else None
                success, msg = self.fix_vfr_target_crf(current_input, str(output_file), output_format, codec, crf_value, vfr_progress, duration, use_hardware, video_info, process_setter)
                if not success: 
                    print(f"[ERROR] VFR fix failed: {msg}")
                    raise Exception(f"Ошибка VFR-fix: {msg}")
                current_input = str(output_file)
            else:
                print(f"[DEBUG] No VFR fix needed, proceeding with compression")
                def compress_progress(p, m): 
                    progress_callback(50 + int(p * 0.45), m) if progress_callback else None
                success, msg = self.compress_video_core(current_input, str(output_file), output_format, codec, crf_value, compress_progress, duration, video_info, use_hardware, process_setter)
                if not success: 
                    print(f"[ERROR] Compression failed: {msg}")
                    # Пробуем альтернативный метод без субтитров
                    print(f"[DEBUG] Trying alternative method without subtitles...")
                    success, msg = self.compress_video_core_no_subtitles(current_input, str(output_file), output_format, codec, crf_value, compress_progress, duration, video_info, use_hardware, process_setter)
                    if not success:
                        print(f"[ERROR] Alternative method failed: {msg}")
                        # Пробуем последний метод с полным маппингом, но без данных
                        print(f"[DEBUG] Trying last method with full mapping but no data...")
                        success, msg = self.compress_video_core_full_map(current_input, str(output_file), output_format, codec, crf_value, compress_progress, duration, video_info, use_hardware, process_setter)
                        if not success:
                            print(f"[ERROR] All methods failed: {msg}")
                            raise Exception(f"Ошибка сжатия: {msg}")
            if progress_callback: progress_callback(100, "Готово!")
            print(f"[DEBUG] Compression completed successfully")
            return str(output_file)
        except Exception as e:
            print(f"[ERROR] Exception during compression: {str(e)}")
            raise e

    def fix_vfr_target_crf(self, input_path: str, output_path: str,
                        output_format: str, codec: str, crf_value: int,
                        progress_callback: Optional[Callable], duration_seconds: float, 
                        use_hardware: bool = False, video_info: dict = None,
                        process_setter: Optional[Callable] = None) -> tuple[bool, str]:
        print(f"[DEBUG] Starting VFR fix with compression:")
        print(f"[DEBUG]   Input: {input_path}")
        print(f"[DEBUG]   Output: {output_path}")
        print(f"[DEBUG]   Format: {output_format}")
        print(f"[DEBUG]   Codec: {codec}")
        print(f"[DEBUG]   CRF: {crf_value}")
        
        gpu_info = self.get_gpu_info()
        has_nvenc = "NVIDIA NVENC" in gpu_info
        print(f"[DEBUG] GPU info: {gpu_info}")
        print(f"[DEBUG] Has NVENC: {has_nvenc}")
        
        # Формируем базовую команду FFmpeg
        cmd = [self.ffmpeg_path, "-y"]
        
        # Добавляем аппаратное ускорение декодирования ДО указания входного файла
        if video_info and video_info.get("is_hevc", False) and has_nvenc:
            cmd.extend(["-hwaccel", "cuda"])
            print(f"[DEBUG] Using CUDA hardware acceleration for HEVC decoding")
        
        # Теперь добавляем входной файл
        cmd.extend(["-i", input_path])
        
        # Добавляем фильтр для исправления VFR и преобразования формата пикселей при необходимости
        vf_filters = []
        vf_filters.append(f"fps={DEFAULT_FPS_FIX}")
        
        # Если исходное видео 10-битное, а кодек не поддерживает 10 бит, добавляем преобразование
        if video_info and video_info.get("is_10bit", False) and codec != "libx265":
            vf_filters.append("format=yuv420p")
            print(f"[DEBUG] Adding 10-bit to 8-bit conversion filter")
        
        if vf_filters:
            cmd.extend(["-vf", ",".join(vf_filters)])
            print(f"[DEBUG] Added video filters: {','.join(vf_filters)}")
        
        # Настраиваем кодеки в зависимости от выбранного кодека и наличия GPU
        if codec == "libvpx-vp9":
            if use_hardware and has_nvenc:
                cmd.extend(["-c:v", "vp9_nvenc", "-crf", str(crf_value), "-b:v", "0"])
                print(f"[DEBUG] Using VP9 hardware encoder")
            else:
                cmd.extend(["-c:v", "libvpx-vp9", "-crf", str(crf_value), "-b:v", "0"])
                print(f"[DEBUG] Using VP9 software encoder")
            cmd.extend(["-c:a", "copy"])  # Копируем аудио без конвертации
            print(f"[DEBUG] Copying audio streams as-is")
        elif codec == "libx265":
            if use_hardware and has_nvenc:
                cmd.extend(["-c:v", "hevc_nvenc", "-crf", str(crf_value), "-preset", "p6", "-tune", "film"])
                print(f"[DEBUG] Using HEVC hardware encoder")
            else:
                cmd.extend(["-c:v", "libx265", "-crf", str(crf_value), "-preset", "medium"])
                print(f"[DEBUG] Using HEVC software encoder")
            cmd.extend(["-c:a", "copy"])  # Копируем аудио без конвертации
            print(f"[DEBUG] Copying audio streams as-is")
        else:  # libx264
            if use_hardware and has_nvenc:
                cmd.extend(["-c:v", "h264_nvenc", "-cq", str(crf_value), "-preset", "p6", "-tune", "film"])
                print(f"[DEBUG] Using H.264 hardware encoder")
            else:
                cmd.extend(["-c:v", "libx264", "-crf", str(crf_value), "-preset", "slow"])
                print(f"[DEBUG] Using H.264 software encoder")
            cmd.extend(["-c:a", "copy"])  # Копируем аудио без конвертации
            print(f"[DEBUG] Copying audio streams as-is")
        
        # Для MP4 добавляем обработку субтитров
        if output_format == "mp4":
            cmd.extend(["-c:s", "mov_text"])
            print(f"[DEBUG] Using mov_text for subtitles")
        else:
            cmd.extend(["-c:s", "copy"])  # Для других форматов копируем субтитры как есть
            print(f"[DEBUG] Copying subtitles as-is")
            
        # Добавляем map для видеопотоков, аудиопотоков и субтитров, исключая обложку
        cmd.extend(["-map", "0:V", "-map", "0:a", "-map", "0:s"])
        print(f"[DEBUG] Mapping video, audio and subtitle streams (excluding cover art)")
        
        # Для MP4 добавляем флаг быстрого старта
        if output_format == "mp4":
            cmd.extend(["-movflags", "+faststart"])
            print(f"[DEBUG] Added faststart flag for MP4")
            
        cmd.extend(["-progress", "pipe:1", output_path])
        print(f"[DEBUG] Final command: {' '.join(cmd)}")
        
        return self._run_command_with_progress(cmd, progress_callback, duration_seconds, "VFR-fix+сжатие", process_setter)

    def compress_video_core(self, input_path: str, output_path: str, output_format: str, codec: str, crf_value: int,
                        progress_callback: Optional[Callable], duration_seconds: float, 
                        video_info: dict = None, use_hardware: bool = False,
                        process_setter: Optional[Callable] = None) -> tuple[bool, str]:
        print(f"[DEBUG] Starting direct compression:")
        print(f"[DEBUG]   Input: {input_path}")
        print(f"[DEBUG]   Output: {output_path}")
        print(f"[DEBUG]   Format: {output_format}")
        print(f"[DEBUG]   Codec: {codec}")
        print(f"[DEBUG]   CRF: {crf_value}")
        
        # Получаем информацию о битрейте, если она не была передана
        if video_info is None:
            video_info = self.get_video_info(input_path)
            if "error" in video_info:
                return False, video_info["error"]
        
        gpu_info = self.get_gpu_info()
        has_nvenc = "NVIDIA NVENC" in gpu_info
        print(f"[DEBUG] GPU info: {gpu_info}")
        print(f"[DEBUG] Has NVENC: {has_nvenc}")
        
        # Формируем базовую команду FFmpeg
        cmd = [self.ffmpeg_path, "-y"]
        
        # Добавляем аппаратное ускорение декодирования ДО указания входного файла
        if video_info.get("is_hevc", False) and has_nvenc:
            cmd.extend(["-hwaccel", "cuda"])
            print(f"[DEBUG] Using CUDA hardware acceleration for HEVC decoding")
        
        # Теперь добавляем входной файл
        cmd.extend(["-i", input_path])
        
        # Добавляем фильтры при необходимости
        vf_filters = []
        
        # Если исходное видео 10-битное, а кодек не поддерживает 10 бит, добавляем преобразование
        if video_info.get("is_10bit", False) and codec != "libx265":
            vf_filters.append("format=yuv420p")
            print(f"[DEBUG] Adding 10-bit to 8-bit conversion filter")
        
        # Для H.264 добавляем фильтр выравнивания размеров
        if codec == "libx264" and not use_hardware:
            vf_filters.append("pad=ceil(iw/2)*2:ceil(ih/2)*2")
            print(f"[DEBUG] Adding padding filter for H.264")
        
        if vf_filters:
            cmd.extend(["-vf", ",".join(vf_filters)])
            print(f"[DEBUG] Added video filters: {','.join(vf_filters)}")
        
        # Настраиваем кодеки в зависимости от выбранного кодека и наличия GPU
        if codec == "libvpx-vp9":
            if use_hardware and has_nvenc:
                cmd.extend(["-c:v", "vp9_nvenc", "-crf", str(crf_value), "-b:v", "0"])
                print(f"[DEBUG] Using VP9 hardware encoder")
            else:
                cmd.extend(["-c:v", "libvpx-vp9", "-crf", str(crf_value), "-b:v", "0"])
                cmd.extend(["-deadline", "good", "-cpu-used", "2"])
                print(f"[DEBUG] Using VP9 software encoder")
            cmd.extend(["-c:a", "copy"])  # Копируем аудио без конвертации
            print(f"[DEBUG] Copying audio streams as-is")
        elif codec == "libx265":
            if use_hardware and has_nvenc:
                cmd.extend(["-c:v", "hevc_nvenc", "-crf", str(crf_value), "-preset", "p6", "-tune", "film"])
                print(f"[DEBUG] Using HEVC hardware encoder")
            else:
                cmd.extend(["-c:v", "libx265", "-crf", str(crf_value), "-preset", "medium"])
                print(f"[DEBUG] Using HEVC software encoder")
            cmd.extend(["-c:a", "copy"])  # Копируем аудио без конвертации
            print(f"[DEBUG] Copying audio streams as-is")
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
                    "-preset", "slow",
                    "-pix_fmt", "yuv420p", 
                    "-tune", "film"
                ])
                print(f"[DEBUG] Using H.264 software encoder")
            cmd.extend(["-c:a", "copy"])  # Копируем аудио без конвертации
            print(f"[DEBUG] Copying audio streams as-is")
            
        # Для MP4 добавляем обработку субтитров
        if output_format == "mp4":
            cmd.extend(["-c:s", "mov_text"])
            print(f"[DEBUG] Using mov_text for subtitles")
        else:
            cmd.extend(["-c:s", "copy"])  # Для других форматов копируем субтитры как есть
            print(f"[DEBUG] Copying subtitles as-is")
            
        # Добавляем map для видеопотоков, аудиопотоков и субтитров, исключая обложку
        cmd.extend(["-map", "0:V", "-map", "0:a", "-map", "0:s"])
        print(f"[DEBUG] Mapping video, audio and subtitle streams (excluding cover art)")
        
        # Для MP4 добавляем флаг быстрого старта
        if output_format == "mp4":
            cmd.extend(["-movflags", "+faststart"])
            print(f"[DEBUG] Added faststart flag for MP4")
            
        cmd.extend(["-progress", "pipe:1", output_path])
        print(f"[DEBUG] Final command: {' '.join(cmd)}")
        
        return self._run_command_with_progress(cmd, progress_callback, duration_seconds, "Сжатие", process_setter)

    def compress_video_core_no_subtitles(self, input_path: str, output_path: str, output_format: str, codec: str, crf_value: int,
                        progress_callback: Optional[Callable], duration_seconds: float, 
                        video_info: dict = None, use_hardware: bool = False,
                        process_setter: Optional[Callable] = None) -> tuple[bool, str]:
        print(f"[DEBUG] Starting compression without subtitles:")
        print(f"[DEBUG]   Input: {input_path}")
        print(f"[DEBUG]   Output: {output_path}")
        print(f"[DEBUG]   Format: {output_format}")
        print(f"[DEBUG]   Codec: {codec}")
        print(f"[DEBUG]   CRF: {crf_value}")
        
        # Получаем информацию о битрейте, если она не была передана
        if video_info is None:
            video_info = self.get_video_info(input_path)
            if "error" in video_info:
                return False, video_info["error"]
        
        gpu_info = self.get_gpu_info()
        has_nvenc = "NVIDIA NVENC" in gpu_info
        print(f"[DEBUG] GPU info: {gpu_info}")
        print(f"[DEBUG] Has NVENC: {has_nvenc}")
        
        # Формируем базовую команду FFmpeg
        cmd = [self.ffmpeg_path, "-y"]
        
        # Добавляем аппаратное ускорение декодирования ДО указания входного файла
        if video_info.get("is_hevc", False) and has_nvenc:
            cmd.extend(["-hwaccel", "cuda"])
            print(f"[DEBUG] Using CUDA hardware acceleration for HEVC decoding")
        
        # Теперь добавляем входной файл
        cmd.extend(["-i", input_path])
        
        # Добавляем фильтры при необходимости
        vf_filters = []
        
        # Если исходное видео 10-битное, а кодек не поддерживает 10 бит, добавляем преобразование
        if video_info.get("is_10bit", False) and codec != "libx265":
            vf_filters.append("format=yuv420p")
            print(f"[DEBUG] Adding 10-bit to 8-bit conversion filter")
        
        # Для H.264 добавляем фильтр выравнивания размеров
        if codec == "libx264" and not use_hardware:
            vf_filters.append("pad=ceil(iw/2)*2:ceil(ih/2)*2")
            print(f"[DEBUG] Adding padding filter for H.264")
        
        if vf_filters:
            cmd.extend(["-vf", ",".join(vf_filters)])
            print(f"[DEBUG] Added video filters: {','.join(vf_filters)}")
        
        # Настраиваем кодеки в зависимости от выбранного кодека и наличия GPU
        if codec == "libvpx-vp9":
            if use_hardware and has_nvenc:
                cmd.extend(["-c:v", "vp9_nvenc", "-crf", str(crf_value), "-b:v", "0"])
                print(f"[DEBUG] Using VP9 hardware encoder")
            else:
                cmd.extend(["-c:v", "libvpx-vp9", "-crf", str(crf_value), "-b:v", "0"])
                cmd.extend(["-deadline", "good", "-cpu-used", "2"])
                print(f"[DEBUG] Using VP9 software encoder")
            cmd.extend(["-c:a", "copy"])  # Копируем аудио без конвертации
            print(f"[DEBUG] Copying audio streams as-is")
        elif codec == "libx265":
            if use_hardware and has_nvenc:
                cmd.extend(["-c:v", "hevc_nvenc", "-crf", str(crf_value), "-preset", "p6", "-tune", "film"])
                print(f"[DEBUG] Using HEVC hardware encoder")
            else:
                cmd.extend(["-c:v", "libx265", "-crf", str(crf_value), "-preset", "medium"])
                print(f"[DEBUG] Using HEVC software encoder")
            cmd.extend(["-c:a", "copy"])  # Копируем аудио без конвертации
            print(f"[DEBUG] Copying audio streams as-is")
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
                    "-preset", "slow",
                    "-pix_fmt", "yuv420p", 
                    "-tune", "film"
                ])
                print(f"[DEBUG] Using H.264 software encoder")
            cmd.extend(["-c:a", "copy"])  # Копируем аудио без конвертации
            print(f"[DEBUG] Copying audio streams as-is")
            
        # Добавляем map только для видеопотоков и аудиопотоков, исключая субтитры и обложку
        cmd.extend(["-map", "0:V", "-map", "0:a"])
        print(f"[DEBUG] Mapping video and audio streams only (excluding subtitles and cover art)")
        
        # Для MP4 добавляем флаг быстрого старта
        if output_format == "mp4":
            cmd.extend(["-movflags", "+faststart"])
            print(f"[DEBUG] Added faststart flag for MP4")
            
        cmd.extend(["-progress", "pipe:1", output_path])
        print(f"[DEBUG] Final command: {' '.join(cmd)}")
        
        return self._run_command_with_progress(cmd, progress_callback, duration_seconds, "Сжатие без субтитров", process_setter)

    def compress_video_core_full_map(self, input_path: str, output_path: str, output_format: str, codec: str, crf_value: int,
                        progress_callback: Optional[Callable], duration_seconds: float, 
                        video_info: dict = None, use_hardware: bool = False,
                        process_setter: Optional[Callable] = None) -> tuple[bool, str]:
        print(f"[DEBUG] Starting compression with full mapping but no data:")
        print(f"[DEBUG]   Input: {input_path}")
        print(f"[DEBUG]   Output: {output_path}")
        print(f"[DEBUG]   Format: {output_format}")
        print(f"[DEBUG]   Codec: {codec}")
        print(f"[DEBUG]   CRF: {crf_value}")
        
        # Получаем информацию о битрейте, если она не была передана
        if video_info is None:
            video_info = self.get_video_info(input_path)
            if "error" in video_info:
                return False, video_info["error"]
        
        gpu_info = self.get_gpu_info()
        has_nvenc = "NVIDIA NVENC" in gpu_info
        print(f"[DEBUG] GPU info: {gpu_info}")
        print(f"[DEBUG] Has NVENC: {has_nvenc}")
        
        # Формируем базовую команду FFmpeg
        cmd = [self.ffmpeg_path, "-y"]
        
        # Добавляем аппаратное ускорение декодирования ДО указания входного файла
        if video_info.get("is_hevc", False) and has_nvenc:
            cmd.extend(["-hwaccel", "cuda"])
            print(f"[DEBUG] Using CUDA hardware acceleration for HEVC decoding")
        
        # Теперь добавляем входной файл
        cmd.extend(["-i", input_path])
        
        # Добавляем фильтры при необходимости
        vf_filters = []
        
        # Если исходное видео 10-битное, а кодек не поддерживает 10 бит, добавляем преобразование
        if video_info.get("is_10bit", False) and codec != "libx265":
            vf_filters.append("format=yuv420p")
            print(f"[DEBUG] Adding 10-bit to 8-bit conversion filter")
        
        # Для H.264 добавляем фильтр выравнивания размеров
        if codec == "libx264" and not use_hardware:
            vf_filters.append("pad=ceil(iw/2)*2:ceil(ih/2)*2")
            print(f"[DEBUG] Adding padding filter for H.264")
        
        if vf_filters:
            cmd.extend(["-vf", ",".join(vf_filters)])
            print(f"[DEBUG] Added video filters: {','.join(vf_filters)}")
        
        # Настраиваем кодеки в зависимости от выбранного кодека и наличия GPU
        if codec == "libvpx-vp9":
            if use_hardware and has_nvenc:
                cmd.extend(["-c:v", "vp9_nvenc", "-crf", str(crf_value), "-b:v", "0"])
                print(f"[DEBUG] Using VP9 hardware encoder")
            else:
                cmd.extend(["-c:v", "libvpx-vp9", "-crf", str(crf_value), "-b:v", "0"])
                cmd.extend(["-deadline", "good", "-cpu-used", "2"])
                print(f"[DEBUG] Using VP9 software encoder")
            cmd.extend(["-c:a", "copy"])  # Копируем аудио без конвертации
            print(f"[DEBUG] Copying audio streams as-is")
        elif codec == "libx265":
            if use_hardware and has_nvenc:
                cmd.extend(["-c:v", "hevc_nvenc", "-crf", str(crf_value), "-preset", "p6", "-tune", "film"])
                print(f"[DEBUG] Using HEVC hardware encoder")
            else:
                cmd.extend(["-c:v", "libx265", "-crf", str(crf_value), "-preset", "medium"])
                print(f"[DEBUG] Using HEVC software encoder")
            cmd.extend(["-c:a", "copy"])  # Копируем аудио без конвертации
            print(f"[DEBUG] Copying audio streams as-is")
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
                    "-preset", "slow",
                    "-pix_fmt", "yuv420p", 
                    "-tune", "film"
                ])
                print(f"[DEBUG] Using H.264 software encoder")
            cmd.extend(["-c:a", "copy"])  # Копируем аудио без конвертации
            print(f"[DEBUG] Copying audio streams as-is")
            
        # Добавляем map для всех потоков, но исключаем данные (обложки и т.д.)
        cmd.extend(["-map", "0", "-map", "-0:d"])
        print(f"[DEBUG] Mapping all streams except data streams (cover art)")
        
        # Для MP4 добавляем флаг быстрого старта
        if output_format == "mp4":
            cmd.extend(["-movflags", "+faststart"])
            print(f"[DEBUG] Added faststart flag for MP4")
            
        cmd.extend(["-progress", "pipe:1", output_path])
        print(f"[DEBUG] Final command: {' '.join(cmd)}")
        
        return self._run_command_with_progress(cmd, progress_callback, duration_seconds, "Сжатие с полным маппингом", process_setter)

    def _calculate_target_bitrate(self, original_bitrate: int, crf_value: int, codec: str, use_hardware: bool = False) -> int:
        """
        Рассчитывает целевой битрейт на основе оригинального битрейта и CRF значения.
        """
        if original_bitrate <= 0:
            # Если не удалось определить оригинальный битрейт, используем значения по умолчанию
            if codec == "libvpx-vp9":
                return 1500
            else:
                return 2000
        
        # Базовый коэффициент сжатия на основе CRF и кодека
        if codec == "libx264":
            # Для libx264 используем стандартные значения
            base_factor = 0.7
            # Каждый шаг CRF изменяет коэффициент примерно на 5%
            crf_adjustment = (23 - crf_value) * 0.05
        elif codec == "libx265":
            # Для libx265 используем стандартные значения
            base_factor = 0.6
            # Каждый шаг CRF изменяет коэффициент примерно на 4%
            crf_adjustment = (28 - crf_value) * 0.04
        else:  # libvpx-vp9
            # Для libvpx-vp9 используем стандартные значения
            base_factor = 0.6
            # Каждый шаг CRF изменяет коэффициент примерно на 4%
            crf_adjustment = (28 - crf_value) * 0.04
            
        # Рассчитываем целевой битрейт
        target_factor = max(0.2, min(1.0, base_factor + crf_adjustment))
        target_bitrate = int(original_bitrate * target_factor / 1000)  # Конвертируем в кбит/с
        
        # Ограничиваем минимальный и максимальный битрейт
        if codec == "libvpx-vp9":
            min_bitrate = 300
            max_bitrate = 8000
        else:
            min_bitrate = 500
            max_bitrate = 10000
            
        return max(min_bitrate, min(max_bitrate, target_bitrate))