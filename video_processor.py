import subprocess
import json
import os
import platform
from pathlib import Path
from typing import Optional, Callable, List, Dict
from config import (OUTPUT_EXTENSIONS, TEMP_FIXED_VIDEO_SUFFIX,
COMPRESSED_VIDEO_SUFFIX, FFMPEG_PATH, FFPROBE_PATH,
DEFAULT_FPS_FIX, DEFAULT_FIX_CRF_H264, DEFAULT_FIX_CRF_VP9,
H264_CRF_FACTOR, VP9_CRF_FACTOR, DEFAULT_CRF_H264)

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

    def _run_command_with_progress(self, cmd: list, progress_callback: Optional[Callable[[int, str], None]], duration_seconds: Optional[float], stage_name: str) -> tuple[bool, str]:
        print(f"Executing: {' '.join(cmd)}")
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
        output_log = []
        for line in iter(process.stdout.readline, ''):
            output_log.append(line)
            if progress_callback and duration_seconds:
                percent = self._parse_ffmpeg_progress_line(line, duration_seconds)
                if percent != -1:
                    progress_callback(percent, f"{stage_name}: {percent}%")
        process.stdout.close()
        return_code = process.wait()
        full_output_message = "".join(output_log)
        if return_code == 0:
            return True, "Команда FFmpeg успешно выполнена."
        else:
            error_summary = "\n".join(full_output_message.strip().split('\n')[-15:])
            error_message = f"Ошибка FFmpeg (код {return_code}).\nЛог:\n{error_summary}"
            print(error_message)
            return False, error_message

    def get_gpu_info(self) -> str:
        try:
            cmd = [self.ffmpeg_path, "-hide_banner", "-encoders"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10, startupinfo=self._get_platform_specific_startupinfo())
            if result.returncode == 0:
                encoders = result.stdout
                gpu_encoders = []
                if "h264_nvenc" in encoders: gpu_encoders.append("NVIDIA NVENC (H.264)")
                if "hevc_nvenc" in encoders: gpu_encoders.append("NVIDIA NVENC (HEVC)")
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
            fix_crf = 15 if codec == "libvpx-vp9" else 18
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
        if codec == "libx264":
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
        elif codec == "libvpx-vp9":
            min_crf = 15
            max_crf = 50
            if crf <= min_crf:
                return 1.0
            elif crf >= max_crf:
                return 0.2
            else:
                crf_diff = crf - min_crf
                max_diff = max_crf - min_crf
                factor = 1.0 * (0.2 / 1.0) ** (crf_diff / max_diff)
                return max(0.2, factor)
        else:
            return max(0.3, 1.0 - (crf - 18) * 0.05)

    def get_video_info(self, input_path: str) -> dict:
        cmd = [self.ffprobe_path, "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", input_path]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, startupinfo=self._get_platform_specific_startupinfo())
            if result.returncode != 0: return {"error": f"Ошибка ffprobe: {result.stderr}"}
            data = json.loads(result.stdout)
            video_stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
            if not video_stream: return {"error": "Видеопоток не найден"}
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
            fps_str = video_stream.get("avg_frame_rate", "0/1")
            num, den = map(int, fps_str.split('/'))
            fps = num / den if den != 0 else 0
            needs_vfr_fix = video_stream.get("r_frame_rate") in ["1000/1", "0/0"] or fps_str == "0/0"
            gpu_info = self.get_gpu_info()
            # Рассчитываем оценку, используя новый метод
            est_size = self.estimated_size_mb(video_bitrate, audio_bitrate, duration, DEFAULT_CRF_H264, "libx264", needs_vfr_fix, False)
            
            # Проверяем, является ли видео HEVC
            is_hevc = video_stream.get("codec_name", "").lower() in ["hevc", "h265"]
            
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
            }
        except Exception as e:
            return {"error": f"Исключение при получении информации: {str(e)}"}

    def compress_video(self, input_path: str, output_format: str, crf_value: int,
                    force_vfr_fix: bool, use_hardware: bool = False, progress_callback: Optional[Callable] = None) -> str:
        input_p = Path(input_path)
        if progress_callback: progress_callback(5, "Анализ видео...")
        video_info = self.get_video_info(input_path)
        if "error" in video_info: 
            print(f"[ERROR] Ошибка при получении информации о видео: {video_info['error']}")
            raise Exception(video_info["error"])
        duration = video_info.get("duration", 0)
        if duration <= 0:
            print(f"[ERROR] Некорректная длительность видео: {duration}")
            raise Exception("Некорректная длительность видео")
        needs_fix = force_vfr_fix or video_info["needs_vfr_fix"]
        # Формируем имя выходного файла
        output_file = input_p.with_name(f"{input_p.stem}{COMPRESSED_VIDEO_SUFFIX}.{output_format}")
        # Проверяем, существует ли файл, и если да - удаляем его
        if output_file.exists():
            try:
                output_file.unlink()
                print(f"Удален существующий файл: {output_file}")
            except Exception as e:
                print(f"Ошибка при удалении существующего файла: {e}")
        current_input = input_path
        try:
            if needs_fix:
                def vfr_progress(p, m): 
                    progress_callback(10 + int(p * 0.4), m) if progress_callback else None
                success, msg = self.fix_vfr_target_crf(current_input, str(output_file), output_format, crf_value, vfr_progress, duration, use_hardware, video_info)
                if not success: 
                    print(f"[ERROR] Ошибка при исправлении VFR: {msg}")
                    raise Exception(f"Ошибка VFR-fix: {msg}")
                current_input = str(output_file)
            else:
                def compress_progress(p, m): 
                    progress_callback(50 + int(p * 0.45), m) if progress_callback else None
                success, msg = self.compress_video_core(current_input, str(output_file), output_format, crf_value, compress_progress, duration, video_info, use_hardware)
                if not success: 
                    print(f"[ERROR] Ошибка при сжатии видео: {msg}")
                    raise Exception(f"Ошибка сжатия: {msg}")
            if progress_callback: progress_callback(100, "Готово!")
            return str(output_file)
        except Exception as e:
            print(f"[ERROR] Исключение в процессе сжатия: {str(e)}")
            raise e

    def fix_vfr_target_crf(self, input_path: str, output_path: str,
                        output_format: str, crf_value: int,
                        progress_callback: Optional[Callable], duration_seconds: float, use_hardware: bool = False, video_info: dict = None) -> tuple[bool, str]:
        gpu_info = self.get_gpu_info()
        has_nvenc = "NVIDIA NVENC" in gpu_info
        # Формируем базовую команду FFmpeg
        cmd = [self.ffmpeg_path, "-y", "-i", input_path]
        
        # Для HEVC видео добавляем дополнительные параметры для корректного декодирования
        if video_info and video_info.get("is_hevc", False):
            cmd.extend(["-c:v", "hevc_cuvid"])  # Используем аппаратный декодер HEVC, если доступно
        
        # Добавляем фильтр для исправления VFR
        cmd.extend(["-vf", f"fps={DEFAULT_FPS_FIX}"])
        
        # Настраиваем кодеки в зависимости от формата и наличия GPU
        if output_format == "webm":
            if use_hardware and has_nvenc:
                cmd.extend(["-c:v", "vp9_nvenc", "-crf", str(crf_value), "-b:v", "0"])
            else:
                cmd.extend(["-c:v", "libvpx-vp9", "-crf", str(crf_value), "-b:v", "0"])
            cmd.extend(["-c:a", "libopus"])  # Для WebM используем Opus
        else:  # mp4 или mkv
            if use_hardware and has_nvenc:
                cmd.extend(["-c:v", "h264_nvenc", "-cq", str(crf_value), "-preset", "p6", "-tune", "film"])
            else:
                cmd.extend(["-c:v", "libx264", "-crf", str(crf_value), "-preset", "medium"])
            cmd.extend(["-c:a", "aac", "-b:a", "320k"])  # Для MP4/MKV используем AAC
        
        # Для MP4 добавляем обработку субтитров
        if output_format == "mp4":
            cmd.extend(["-c:s", "mov_text"])
        else:
            cmd.extend(["-c:s", "copy"])  # Для других форматов копируем субтитры как есть
            
        # Добавляем map для всех потоков, как в рабочем батнике
        cmd.extend(["-map", "0"])
        
        # Для MP4 добавляем флаг быстрого старта
        if output_format == "mp4":
            cmd.extend(["-movflags", "+faststart"])
            
        cmd.extend(["-progress", "pipe:1", output_path])
        return self._run_command_with_progress(cmd, progress_callback, duration_seconds, "VFR-fix+сжатие")

    def compress_video_core(self, input_path: str, output_path: str, output_format: str, crf_value: int,
                        progress_callback: Optional[Callable], duration_seconds: float, video_info: dict = None, use_hardware: bool = False) -> tuple[bool, str]:
        # Получаем информацию о битрейте, если она не была передана
        if video_info is None:
            video_info = self.get_video_info(input_path)
            if "error" in video_info:
                return False, video_info["error"]
        gpu_info = self.get_gpu_info()
        has_nvenc = "NVIDIA NVENC" in gpu_info
        
        # Формируем базовую команду FFmpeg
        cmd = [self.ffmpeg_path, "-y", "-i", input_path]
        
        # Для HEVC видео добавляем дополнительные параметры для корректного декодирования
        if video_info.get("is_hevc", False):
            cmd.extend(["-c:v", "hevc_cuvid"])  # Используем аппаратный декодер HEVC, если доступно
        
        # Настраиваем кодеки в зависимости от формата и наличия GPU
        if output_format == "webm":
            if use_hardware and has_nvenc:
                cmd.extend(["-c:v", "vp9_nvenc", "-crf", str(crf_value), "-b:v", "0"])
            else:
                cmd.extend(["-c:v", "libvpx-vp9", "-crf", str(crf_value), "-b:v", "0"])
                cmd.extend(["-deadline", "good", "-cpu-used", "2"])
            cmd.extend(["-c:a", "libopus"])  # Для WebM используем Opus
        else:  # mp4 или mkv (H.264)
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
            else:
                cmd.extend([
                    "-c:v", "libx264", 
                    "-crf", str(crf_value), 
                    "-preset", "slow",
                    "-pix_fmt", "yuv420p", 
                    "-tune", "film"
                ])
                cmd.extend(["-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2"])
            cmd.extend(["-c:a", "aac", "-b:a", "320k"])  # Для MP4/MKV используем AAC
            
        # Для MP4 добавляем обработку субтитров
        if output_format == "mp4":
            cmd.extend(["-c:s", "mov_text"])
        else:
            cmd.extend(["-c:s", "copy"])  # Для других форматов копируем субтитры как есть
            
        # Добавляем map для всех потоков, как в рабочем батнике
        cmd.extend(["-map", "0"])
        
        # Для MP4 добавляем флаг быстрого старта
        if output_format == "mp4":
            cmd.extend(["-movflags", "+faststart"])
            
        cmd.extend(["-progress", "pipe:1", output_path])
        return self._run_command_with_progress(cmd, progress_callback, duration_seconds, "Сжатие")

    def _calculate_target_bitrate(self, original_bitrate: int, crf_value: int, output_format: str, use_hardware: bool = False) -> int:
        """
        Рассчитывает целевой битрейт на основе оригинального битрейта и CRF значения.
        """
        if original_bitrate <= 0:
            # Если не удалось определить оригинальный битрейт, используем значения по умолчанию
            return 2000 if output_format == "mp4" else 1500
        # Базовый коэффициент сжатия на основе CRF
        if output_format == "mp4":
            # Для libx264 используем стандартные значения
            base_factor = 0.7
            # Каждый шаг CRF изменяет коэффициент примерно на 5%
            crf_adjustment = (23 - crf_value) * 0.05
        else:  # webm
            # Для libvpx-vp9 используем стандартные значения
            base_factor = 0.6
            # Каждый шаг CRF изменяет коэффициент примерно на 4%
            crf_adjustment = (28 - crf_value) * 0.04
        # Рассчитываем целевой битрейт
        target_factor = max(0.2, min(1.0, base_factor + crf_adjustment))
        target_bitrate = int(original_bitrate * target_factor / 1000)  # Конвертируем в кбит/с
        # Ограничиваем минимальный и максимальный битрейт
        min_bitrate = 500 if output_format == "mp4" else 300
        max_bitrate = 10000 if output_format == "mp4" else 8000
        return max(min_bitrate, min(max_bitrate, target_bitrate))