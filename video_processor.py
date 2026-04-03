"""
Основной класс для обработки видео
"""
import logging
import time
import tempfile
import os
from pathlib import Path
from typing import Optional, Callable
from config import COMPRESSED_VIDEO_SUFFIX, TRIMMED_VIDEO_SUFFIX
from video_size_estimator import VideoSizeEstimator
from ffmpeg_handler import FFmpegHandler
from crf_extractor import get_crf_from_file


class VideoProcessor:
    """Основной класс для обработки видео"""
    
    def __init__(self):
        self.ffmpeg_handler = FFmpegHandler()
        self.size_estimator = VideoSizeEstimator()
    
    def get_gpu_info(self) -> str:
        """Получает информацию о доступных GPU"""
        return self.ffmpeg_handler.get_gpu_info()
    
    def get_audio_tracks(self, input_path: str) -> list:
        """Получает информацию об аудиодорожках"""
        return self.ffmpeg_handler.get_audio_tracks(input_path)
    
    def estimate_video_complexity(self, video_info: dict) -> tuple[int, str]:
        """Оценивает сложность видео"""
        return self.size_estimator.estimate_video_complexity(video_info)
    
    def estimated_size_mb(self, video_bitrate: int, audio_bitrate: int, duration: float, crf: int, codec: str, 
                         needs_vfr_fix: bool = False, use_hardware: bool = False, preset: str = "medium", 
                         complexity_score: int = 5, width: int = 1920, height: int = 1080) -> float:
        """Оценивает размер файла после сжатия"""
        return self.size_estimator.estimate_size_mb(
            video_bitrate=video_bitrate,
            audio_bitrate=audio_bitrate,
            duration=duration,
            crf=crf,
            codec=codec,
            needs_vfr_fix=needs_vfr_fix,
            use_hardware=use_hardware,
            preset=preset,
            complexity_score=complexity_score,
            width=width,
            height=height
        )
    
    def get_video_info(self, input_path: str) -> dict:
        """Получает полную информацию о видео файле"""
        video_info = self.ffmpeg_handler.get_video_info(input_path)
        
        if "error" in video_info:
            return video_info
        
        gpu_info = self.get_gpu_info()
        complexity_score, complexity_desc = self.estimate_video_complexity(video_info)
        
        crf_value = get_crf_from_file(input_path)
        
        video_info.update({
            "gpu_info": gpu_info,
            "processing_mode": "GPU" if "Доступные GPU" in gpu_info else "CPU",
            "complexity_score": complexity_score,
            "complexity_desc": complexity_desc,
            "crf_value": crf_value,
        })
        
        return video_info
    
    def run_chunk_test(self, input_path: str, codec: str, crf_value: int, preset_value: str,
                       use_hardware: bool, process_setter: Optional[Callable] = None) -> dict:
        """Алгоритм тестовых фрагментов (Chunk Testing) для точного определения выгоды сжатия."""
        logging.info(f"Запуск алгоритма Chunk Test для {input_path}")
        video_info = self.get_video_info(input_path)
        if "error" in video_info:
            raise Exception(video_info["error"])

        duration = video_info.get("duration", 0)
        if duration < 30:
            raise Exception("Видео слишком короткое для теста (нужно минимум 30 секунд)")

        # Нарезаем 3 куска по 10 секунд (на 10%, 50% и 80% длительности фильма)
        chunk_duration = 10
        timestamps = [duration * 0.1, duration * 0.5, duration * 0.8]
        temp_dir = tempfile.gettempdir()
        total_size_bytes = 0
        
        vmaf_scores = []
        libvmaf_missing = False
        
        start_time = time.time()

        for i, ts in enumerate(timestamps):
            out_path = os.path.join(temp_dir, f"chunk_test_{i}.mp4")
            logging.debug(f"Кодирование фрагмента {i+1}/3 на отметке {ts:.1f} сек...")
            success, msg = self.ffmpeg_handler.encode_chunk(
                input_path, out_path, ts, chunk_duration, codec, crf_value, preset_value, use_hardware, process_setter
            )
            if not success:
                raise Exception(f"Ошибка при кодировании фрагмента {i+1}: {msg}")
            
            if os.path.exists(out_path):
                # Считаем VMAF
                if not libvmaf_missing:
                    logging.debug(f"Расчет VMAF для фрагмента {i+1}...")
                    vmaf = self.ffmpeg_handler.calculate_vmaf(input_path, out_path, ts, chunk_duration, process_setter)
                    if vmaf == -2.0:
                        libvmaf_missing = True
                    elif vmaf >= 0:
                        vmaf_scores.append(vmaf)
                
                total_size_bytes += os.path.getsize(out_path)
                os.remove(out_path) # Удаляем временный файл сразу

        total_time_taken = time.time() - start_time
        total_chunk_duration = chunk_duration * len(timestamps) # 30 секунд

        # Математика экстраполяции
        chunk_bitrate_bps = (total_size_bytes * 8) / total_chunk_duration
        est_size_mb = (chunk_bitrate_bps * duration) / 8 / (1024 * 1024)
        
        speed_multiplier = total_chunk_duration / total_time_taken
        est_time_sec = duration / speed_multiplier

        orig_size_mb = video_info.get("size_mb", 0)
        diff_percent = 0
        if orig_size_mb > 0:
            diff_percent = ((orig_size_mb - est_size_mb) / orig_size_mb) * 100

        # Форматирование вывода
        if diff_percent > 0:
            diff_str = f"-{diff_percent:.1f}%"
        else:
            diff_str = f"+{abs(diff_percent):.1f}%"
            
        avg_vmaf = sum(vmaf_scores) / len(vmaf_scores) if vmaf_scores else -1.0
        if libvmaf_missing:
            avg_vmaf = -2.0

        logging.info(f"Chunk Test завершен: выгода {diff_str}, примерный размер {est_size_mb:.1f} МБ, VMAF: {avg_vmaf:.1f}")

        return {
            "file_path": input_path,
            "test_diff": diff_str,
            "test_est_size": f"{est_size_mb:.1f} МБ",
            "test_est_time": self.size_estimator.format_duration(est_time_sec),
            "test_vmaf": avg_vmaf,
            "is_profitable": diff_percent > 0
        }

    def compress_video(self, input_path: str, output_format: str, codec: str, crf_value: int,
                    preset_value: str, force_vfr_fix: bool, use_hardware: bool = False, 
                    progress_callback: Optional[Callable] = None,
                    process_setter: Optional[Callable] = None,
                    output_dir: Optional[str] = None) -> str:
        """Основной метод сжатия видео"""
        input_p = Path(input_path)
        if progress_callback: 
            progress_callback(5, "Анализ видео...")
        
        video_info = self.get_video_info(input_path)
        if "error" in video_info: 
            raise Exception(video_info["error"])
        
        duration = video_info.get("duration", 0)
        if duration <= 0:
            raise Exception("Некорректная длительность видео")
        
        needs_fix = force_vfr_fix or video_info["needs_vfr_fix"]
        
        if output_dir:
            output_path = Path(output_dir) / f"{input_p.stem}{COMPRESSED_VIDEO_SUFFIX}.{output_format}"
        else:
            output_path = input_p.with_name(f"{input_p.stem}{COMPRESSED_VIDEO_SUFFIX}.{output_format}")
        
        if output_path.exists():
            try:
                output_path.unlink()
            except Exception as e:
                logging.error(f"Error deleting existing file: {e}")
        
        current_input = input_path
        try:
            if needs_fix:
                def vfr_progress(p, m): 
                    progress_callback(p, m) if progress_callback else None
                success, msg = self.ffmpeg_handler.fix_vfr_target_crf(
                    current_input, str(output_path), output_format, codec, crf_value, 
                    preset_value, vfr_progress, duration, use_hardware, video_info, process_setter
                )
                if not success: 
                    raise Exception(f"Ошибка VFR-fix: {msg}")
                current_input = str(output_path)
            else:
                def compress_progress(p, m): 
                    progress_callback(p, m) if progress_callback else None
                success, msg = self.ffmpeg_handler.compress_video_core(
                    current_input, str(output_path), output_format, codec, crf_value, 
                    preset_value, compress_progress, duration, video_info, use_hardware, process_setter
                )
                if not success: 
                    success, msg = self.ffmpeg_handler.compress_video_core_no_subtitles(
                        current_input, str(output_path), output_format, codec, crf_value, 
                        preset_value, compress_progress, duration, video_info, use_hardware, process_setter
                    )
                    if not success:
                        success, msg = self.ffmpeg_handler.compress_video_core_full_map(
                            current_input, str(output_path), output_format, codec, crf_value, 
                            preset_value, compress_progress, duration, video_info, use_hardware, process_setter
                        )
                        if not success:
                            raise Exception(f"Ошибка сжатия: {msg}")
            if progress_callback: 
                progress_callback(100, "Готово!")
            return str(output_path)
        except Exception as e:
            raise e

    def extract_frame(self, input_path: str, frame_number: int, output_path: str,
                      process_setter: Optional[Callable] = None) -> str:
        """Извлекает конкретный кадр из видео и сохраняет как изображение."""
        video_info = self.get_video_info(input_path)
        if "error" in video_info:
            raise Exception(video_info["error"])
        
        fps = video_info.get("fps", 0)
        if fps <= 0:
            raise Exception("Не удалось определить частоту кадров видео")
        
        total_frames = int(video_info.get("duration", 0) * fps)
        if frame_number < 0:
            raise Exception("Номер кадра не может быть отрицательным")
        if frame_number >= total_frames:
            raise Exception(f"Кадр #{frame_number} выходит за пределы видео (всего кадров: ~{total_frames})")
        
        success, msg = self.ffmpeg_handler.extract_frame(
            input_path, output_path, frame_number, fps, process_setter
        )
        
        if not success:
            raise Exception(f"Ошибка при извлечении кадра: {msg}")
        
        return output_path

    def trim_video(self, input_path: str, seconds: float, from_start: bool, 
                   progress_callback: Optional[Callable] = None,
                   process_setter: Optional[Callable] = None,
                   output_dir: Optional[str] = None) -> str:
        """Метод для сокращения видео"""
        input_p = Path(input_path)
        if progress_callback:
            progress_callback(5, "Анализ длительности...")
            
        video_info = self.get_video_info(input_path)
        if "error" in video_info:
            raise Exception(video_info["error"])
            
        total_duration = video_info.get("duration", 0)
        if total_duration <= 0:
            raise Exception("Не удалось определить длительность видео")
            
        if seconds >= total_duration:
            raise Exception("Количество удаляемых секунд больше или равно длительности видео")
            
        if from_start:
            start_time = seconds
            new_duration = total_duration - seconds
        else:
            start_time = 0
            new_duration = total_duration - seconds
            
        if output_dir:
            output_path = Path(output_dir) / f"{input_p.stem}{TRIMMED_VIDEO_SUFFIX}{input_p.suffix}"
        else:
            output_path = input_p.with_name(f"{input_p.stem}{TRIMMED_VIDEO_SUFFIX}{input_p.suffix}")
            
        if output_path.exists():
            try:
                output_path.unlink()
            except Exception as e:
                pass
        
        def trim_progress(p, m):
            progress_callback(p, m) if progress_callback else None
            
        success, msg = self.ffmpeg_handler.trim_video_core(
            input_path, str(output_path), start_time, new_duration,
            trim_progress, new_duration, process_setter
        )
        
        if not success:
            raise Exception(f"Ошибка при сокращении видео: {msg}")
            
        if progress_callback:
            progress_callback(100, "Готово!")
            
        return str(output_path)

    def normalize_audio_volume(self, input_path: str,
                                progress_callback: Optional[Callable] = None,
                                process_setter: Optional[Callable] = None,
                                output_dir: Optional[str] = None) -> str:
        """Метод для нормализации громкости аудио"""
        input_p = Path(input_path)
        if output_dir:
            output_path = Path(output_dir) / f"{input_p.stem}_volnorm{input_p.suffix}"
        else:
            output_path = input_p.with_name(f"{input_p.stem}_volnorm{input_p.suffix}")
            
        if output_path.exists():
            try:
                output_path.unlink()
            except Exception as e:
                pass
        
        def norm_progress(p, m):
            progress_callback(p, m) if progress_callback else None
            
        success, msg = self.ffmpeg_handler.normalize_audio_volume(
            input_path, str(output_path), norm_progress, process_setter
        )
        
        if not success:
            raise Exception(f"Ошибка при нормализации громкости: {msg}")
            
        if progress_callback:
            progress_callback(100, "Готово!")
            
        return str(output_path)