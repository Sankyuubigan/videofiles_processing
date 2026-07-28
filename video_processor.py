"""
Основной класс для обработки видео
"""
import logging
import time
import tempfile
import os
from pathlib import Path
from typing import Optional, Callable
from config import COMPRESSED_VIDEO_SUFFIX, TRIMMED_VIDEO_SUFFIX, CODECS
from video_size_estimator import VideoSizeEstimator
from ffmpeg_handler import FFmpegHandler
from crf_extractor import get_crf_from_file
from settings_manager import load_settings


class VideoProcessor:
    """Основной класс для обработки видео"""
    
    def __init__(self):
        self.ffmpeg_handler = FFmpegHandler()
        self.size_estimator = VideoSizeEstimator()
    
    def get_gpu_info(self) -> str:
        return self.ffmpeg_handler.get_gpu_info()
    
    def get_audio_tracks(self, input_path: str) -> list:
        return self.ffmpeg_handler.get_audio_tracks(input_path)
    
    def estimate_video_complexity(self, video_info: dict) -> tuple[int, str]:
        return self.size_estimator.estimate_video_complexity(video_info)
    
    def estimated_size_mb(self, video_bitrate: int, audio_bitrate: int, duration: float, crf: int, codec: str, 
                         needs_vfr_fix: bool = False, use_hardware: bool = False, preset: str = "medium", 
                         complexity_score: int = 5, width: int = 1920, height: int = 1080) -> float:
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
    
    def find_best_crf(self, input_path: str, codec: str, preset_value: str, use_hardware: bool, target_vmaf: float, process_setter: Optional[Callable] = None, progress_callback: Optional[Callable] = None, force_vfr_fix: bool = False) -> int:
        """Бинарный поиск идеального CRF по целевому VMAF (полное совпадение с ручным тестом)."""
        video_info = self.get_video_info(input_path)
        width = video_info.get("width", 1920)
        duration = video_info.get("duration", 0)
        
        codec_info = CODECS.get(codec, CODECS["libx264"])
        crf_low = codec_info["crf_min"]
        crf_high = codec_info["crf_max"]
        
        settings = load_settings()
        vmaf_subsample = settings.get("vmaf_subsample", 5)
        # Теперь Авто-CRF берет настройки прямо из ваших параметров, чтобы оценки на 100% совпадали с ручным тестом
        chunk_count = settings.get("chunk_count", 3)
        chunk_duration = settings.get("chunk_duration", 10)
        
        if duration < 30:
            chunk_count = 1
            chunk_duration = min(chunk_duration, duration * 0.5)
            timestamps = [duration * 0.5]
        else:
            if chunk_count == 1: timestamps = [duration * 0.5]
            elif chunk_count == 2: timestamps = [duration * 0.2, duration * 0.8]
            elif chunk_count == 3: timestamps = [duration * 0.1, duration * 0.5, duration * 0.8]
            elif chunk_count == 4: timestamps = [duration * 0.1, duration * 0.35, duration * 0.6, duration * 0.85]
            else: timestamps = [duration * 0.1, duration * 0.3, duration * 0.5, duration * 0.7, duration * 0.9]
        
        best_crf_closest = codec_info["crf_default"]
        min_diff = 100.0
        best_crf_acceptable = -1
        
        temp_dir = tempfile.gettempdir()
        
        # Полноценный бинарный поиск (6 шагов гарантируют проверку всего диапазона 18-35 без пропусков)
        for step in range(6):
            if crf_low > crf_high:
                break
                
            mid_crf = (crf_low + crf_high) // 2
            if progress_callback:
                progress_callback(10 + step * 10, f"Авто CRF: тест CRF {mid_crf}...")
                
            vmaf_scores = []
            libvmaf_missing = False
            
            for i, ts in enumerate(timestamps):
                chunk_path = os.path.join(temp_dir, f"auto_crf_{os.getpid()}_{int(time.time())}_{i}.mp4")
                success, msg = self.ffmpeg_handler.encode_chunk(
                    input_path, chunk_path, ts, chunk_duration, codec, mid_crf, preset_value, use_hardware, video_info, force_vfr_fix, process_setter
                )
                
                if not success:
                    logging.warning(f"Ошибка при Авто CRF encode (фрагмент {i}): {msg}")
                    break
                    
                vmaf = self.ffmpeg_handler.calculate_vmaf(
                    input_path, chunk_path, ts, chunk_duration, vmaf_subsample, width, video_info, force_vfr_fix, process_setter
                )
                
                if os.path.exists(chunk_path):
                    try: os.remove(chunk_path)
                    except: pass
                    
                if vmaf < 0:
                    libvmaf_missing = True
                    break
                
                vmaf_scores.append(vmaf)
                
            if libvmaf_missing or not vmaf_scores:
                logging.warning("VMAF вернул ошибку, прерываем поиск CRF.")
                break
                
            avg_vmaf = sum(vmaf_scores) / len(vmaf_scores)
            diff = abs(avg_vmaf - target_vmaf)
            
            logging.debug(f"Auto CRF: шаг {step+1}, тестируем CRF {mid_crf}, Avg VMAF={avg_vmaf:.2f}, Цель={target_vmaf}")
            
            # Ищем максимально возможный CRF (минимальный размер файла), который выдает VMAF >= Target
            # Допуск 0.1 балла на погрешность (чтобы не браковать 89.9 при цели 90.0)
            if avg_vmaf >= (target_vmaf - 0.1):
                if mid_crf > best_crf_acceptable:
                    best_crf_acceptable = mid_crf
            
            # Сохраняем запасной вариант (наименьшая разница), если ни один CRF не дотянул до цели
            if diff < min_diff:
                min_diff = diff
                best_crf_closest = mid_crf
                
            if avg_vmaf < target_vmaf:
                # Качество ниже цели -> нужен меньший CRF (лучшее качество)
                crf_high = mid_crf - 1
            else:
                # Качество выше цели -> можем позволить себе больший CRF (меньший размер файла)
                crf_low = mid_crf + 1
                
        final_crf = best_crf_acceptable if best_crf_acceptable != -1 else best_crf_closest
        
        if progress_callback:
            progress_callback(60, f"Авто CRF завершен: выбран CRF {final_crf}")
            
        return final_crf
    
    def run_chunk_test(self, input_path: str, codec: str, crf_value: int, preset_value: str,
                       use_hardware: bool, process_setter: Optional[Callable] = None,
                       auto_crf: bool = False, target_vmaf: float = 95.0, force_vfr_fix: bool = False) -> dict:
        logging.info(f"Запуск алгоритма Chunk Test для {input_path}")
        
        if auto_crf:
            crf_value = self.find_best_crf(input_path, codec, preset_value, use_hardware, target_vmaf, process_setter, progress_callback=None, force_vfr_fix=force_vfr_fix)
            logging.info(f"Chunk Test: Auto CRF определил лучшее значение {crf_value} для цели VMAF {target_vmaf}")
            
        video_info = self.get_video_info(input_path)
        if "error" in video_info:
            raise Exception(video_info["error"])

        duration = video_info.get("duration", 0)
        width = video_info.get("width", 1920)
        
        settings = load_settings()
        chunk_count = settings.get("chunk_count", 3)
        chunk_duration = settings.get("chunk_duration", 10)
        vmaf_subsample = settings.get("vmaf_subsample", 5)

        if duration < 30:
            chunk_count = 1
            chunk_duration = min(10, duration * 0.5)
            timestamps = [duration * 0.5]
        else:
            if chunk_count == 1: timestamps = [duration * 0.5]
            elif chunk_count == 2: timestamps = [duration * 0.2, duration * 0.8]
            elif chunk_count == 3: timestamps = [duration * 0.1, duration * 0.5, duration * 0.8]
            elif chunk_count == 4: timestamps = [duration * 0.1, duration * 0.35, duration * 0.6, duration * 0.85]
            else: timestamps = [duration * 0.1, duration * 0.3, duration * 0.5, duration * 0.7, duration * 0.9]

        temp_dir = tempfile.gettempdir()
        total_size_bytes = 0
        vmaf_scores = []
        libvmaf_missing = False
        encode_time_total = 0.0

        for i, ts in enumerate(timestamps):
            out_path = os.path.join(temp_dir, f"chunk_test_{i}.mp4")
            
            start_encode = time.time()
            success, msg = self.ffmpeg_handler.encode_chunk(
                input_path, out_path, ts, chunk_duration, codec, crf_value, preset_value, use_hardware, video_info, force_vfr_fix, process_setter
            )
            encode_time_total += (time.time() - start_encode)
            
            if not success:
                raise Exception(f"Ошибка при кодировании фрагмента {i+1}: {msg}")
            
            if os.path.exists(out_path):
                if not libvmaf_missing:
                    vmaf = self.ffmpeg_handler.calculate_vmaf(input_path, out_path, ts, chunk_duration, vmaf_subsample, width, video_info, force_vfr_fix, process_setter)
                    if vmaf == -2.0:
                        libvmaf_missing = True
                    elif vmaf >= 0:
                        vmaf_scores.append(vmaf)
                
                total_size_bytes += os.path.getsize(out_path)
                os.remove(out_path)

        total_chunk_duration = chunk_duration * len(timestamps)

        chunk_bitrate_bps = (total_size_bytes * 8) / total_chunk_duration
        est_size_mb = (chunk_bitrate_bps * duration) / 8 / (1024 * 1024)
        
        if encode_time_total > 0:
            speed_multiplier = total_chunk_duration / encode_time_total
            est_time_sec = duration / speed_multiplier
        else:
            est_time_sec = 0

        orig_size_mb = video_info.get("size_mb", 0)
        diff_percent = 0
        if orig_size_mb > 0:
            diff_percent = ((orig_size_mb - est_size_mb) / orig_size_mb) * 100

        if diff_percent > 0: diff_str = f"-{diff_percent:.1f}%"
        else: diff_str = f"+{abs(diff_percent):.1f}%"
            
        avg_vmaf = sum(vmaf_scores) / len(vmaf_scores) if vmaf_scores else -1.0
        if libvmaf_missing: avg_vmaf = -2.0

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
                    output_dir: Optional[str] = None,
                    auto_crf: bool = False, target_vmaf: float = 95.0) -> str:
        input_p = Path(input_path)
        
        if auto_crf:
            crf_value = self.find_best_crf(input_path, codec, preset_value, use_hardware, target_vmaf, process_setter, progress_callback, force_vfr_fix)
            if progress_callback: progress_callback(15, f"Авто CRF: выбрано значение {crf_value}. Начинаем сжатие...")
            logging.info(f"Для файла {input_p.name} автоматически выбран CRF {crf_value} (целевой VMAF {target_vmaf})")
        else:
            if progress_callback: progress_callback(5, "Анализ видео...")
        
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
            try: output_path.unlink()
            except Exception as e: logging.error(f"Error deleting existing file: {e}")
        
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
            try: output_path.unlink()
            except Exception as e: pass
        
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
        input_p = Path(input_path)
        if output_dir:
            output_path = Path(output_dir) / f"{input_p.stem}_volnorm{input_p.suffix}"
        else:
            output_path = input_p.with_name(f"{input_p.stem}_volnorm{input_p.suffix}")
            
        if output_path.exists():
            try: output_path.unlink()
            except Exception as e: pass
        
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