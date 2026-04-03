"""
Основной класс для обработки видео
"""
import logging
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
        
        # Добавляем расчетные параметры
        gpu_info = self.get_gpu_info()
        complexity_score, complexity_desc = self.estimate_video_complexity(video_info)
        
        # Расчет примерного размера с учетом сложности и правильных параметров
        width = video_info.get("width", 1920)
        height = video_info.get("height", 1080)
        
        est_size = self.estimated_size_mb(
            video_bitrate=video_info.get("video_bitrate", 0), 
            audio_bitrate=video_info.get("audio_bitrate", 128000), 
            duration=video_info.get("duration", 0), 
            crf=24, 
            codec="libx264", 
            needs_vfr_fix=video_info.get("needs_vfr_fix", False), 
            use_hardware=False,
            preset="slow",  # Используем "slow" по умолчанию
            complexity_score=complexity_score,
            width=width,
            height=height
        )
        
        # Извлечение CRF из метаданных файла
        logging.debug(f"Вызов get_crf_from_file для: {input_path}")
        crf_value = get_crf_from_file(input_path)
        logging.info(f"Получено crf_value для {input_path}: {crf_value}")
        
        # Добавляем вычисленные поля в информацию
        video_info.update({
            "estimated_size_mb": est_size,
            "gpu_info": gpu_info,
            "processing_mode": "GPU" if "Доступные GPU" in gpu_info else "CPU",
            "complexity_score": complexity_score,
            "complexity_desc": complexity_desc,
            "crf_value": crf_value,
        })
        
        return video_info
    
    def compress_video(self, input_path: str, output_format: str, codec: str, crf_value: int,
                    preset_value: str, force_vfr_fix: bool, use_hardware: bool = False, 
                    progress_callback: Optional[Callable] = None,
                    process_setter: Optional[Callable] = None,
                    output_dir: Optional[str] = None) -> str:
        """Основной метод сжатия видео"""
        logging.debug(f"Starting compression:")
        logging.debug(f"   Input: {input_path}")
        logging.debug(f"   Output format: {output_format}")
        logging.debug(f"   Codec: {codec}")
        logging.debug(f"   CRF: {crf_value}")
        logging.debug(f"   Preset: {preset_value}")
        logging.debug(f"   Force VFR fix: {force_vfr_fix}")
        logging.debug(f"   Hardware encoding: {use_hardware}")
        
        input_p = Path(input_path)
        if progress_callback: 
            progress_callback(5, "Анализ видео...")
        
        video_info = self.get_video_info(input_path)
        if "error" in video_info: 
            logging.error(f"Error getting video info: {video_info['error']}")
            raise Exception(video_info["error"])
        
        duration = video_info.get("duration", 0)
        if duration <= 0:
            logging.error(f"Invalid video duration: {duration}")
            raise Exception("Некорректная длительность видео")
        
        needs_fix = force_vfr_fix or video_info["needs_vfr_fix"]
        
        if output_dir:
            output_path = Path(output_dir) / f"{input_p.stem}{COMPRESSED_VIDEO_SUFFIX}.{output_format}"
        else:
            output_path = input_p.with_name(f"{input_p.stem}{COMPRESSED_VIDEO_SUFFIX}.{output_format}")
        
        logging.debug(f"Output file will be: {output_path}")
        
        if output_path.exists():
            try:
                output_path.unlink()
                logging.debug(f"Deleted existing file: {output_path}")
            except Exception as e:
                logging.error(f"Error deleting existing file: {e}")
        
        current_input = input_path
        try:
            if needs_fix:
                logging.debug(f"VFR fix is needed")
                def vfr_progress(p, m): 
                    progress_callback(p, m) if progress_callback else None
                success, msg = self.ffmpeg_handler.fix_vfr_target_crf(
                    current_input, str(output_path), output_format, codec, crf_value, 
                    preset_value, vfr_progress, duration, use_hardware, video_info, process_setter
                )
                if not success: 
                    logging.error(f"VFR fix failed: {msg}")
                    raise Exception(f"Ошибка VFR-fix: {msg}")
                current_input = str(output_path)
            else:
                logging.debug(f"No VFR fix needed, proceeding with compression")
                def compress_progress(p, m): 
                    progress_callback(p, m) if progress_callback else None
                success, msg = self.ffmpeg_handler.compress_video_core(
                    current_input, str(output_path), output_format, codec, crf_value, 
                    preset_value, compress_progress, duration, video_info, use_hardware, process_setter
                )
                if not success: 
                    logging.error(f"Compression failed: {msg}")
                    logging.debug(f"Trying alternative method without subtitles...")
                    success, msg = self.ffmpeg_handler.compress_video_core_no_subtitles(
                        current_input, str(output_path), output_format, codec, crf_value, 
                        preset_value, compress_progress, duration, video_info, use_hardware, process_setter
                    )
                    if not success:
                        logging.error(f"Alternative method failed: {msg}")
                        logging.debug(f"Trying last method with full mapping but no data...")
                        success, msg = self.ffmpeg_handler.compress_video_core_full_map(
                            current_input, str(output_path), output_format, codec, crf_value, 
                            preset_value, compress_progress, duration, video_info, use_hardware, process_setter
                        )
                        if not success:
                            logging.error(f"All methods failed: {msg}")
                            raise Exception(f"Ошибка сжатия: {msg}")
            if progress_callback: 
                progress_callback(100, "Готово!")
            logging.debug(f"Compression completed successfully")
            return str(output_path)
        except Exception as e:
            logging.error(f"Exception during compression: {str(e)}")
            raise e

    def extract_frame(self, input_path: str, frame_number: int, output_path: str,
                      process_setter: Optional[Callable] = None) -> str:
        """
        Извлекает конкретный кадр из видео и сохраняет как изображение.
        
        Args:
            input_path: Путь к видеофайлу.
            frame_number: Номер кадра (начиная с 0).
            output_path: Путь для сохранения изображения.
            process_setter: Колбэк для установки ссылки на процесс.
            
        Returns:
            Путь к сохранённому изображению.
        """
        logging.info(f"Извлечение кадра #{frame_number} из {input_path}")
        
        logging.debug(f"Получение информации о видео: {input_path}")
        video_info = self.get_video_info(input_path)
        if "error" in video_info:
            logging.error(f"Ошибка получения информации о видео: {video_info['error']}")
            raise Exception(video_info["error"])
        
        fps = video_info.get("fps", 0)
        if fps <= 0:
            logging.error(f"Недопустимое значение fps={fps} для {input_path}")
            raise Exception("Не удалось определить частоту кадров видео")
        
        total_frames = int(video_info.get("duration", 0) * fps)
        if frame_number < 0:
            logging.error(f"Отрицательный номер кадра: {frame_number}")
            raise Exception("Номер кадра не может быть отрицательным")
        if frame_number >= total_frames:
            logging.error(f"Кадр #{frame_number} выходит за пределы (всего кадров: ~{total_frames})")
            raise Exception(f"Кадр #{frame_number} выходит за пределы видео (всего кадров: ~{total_frames})")
        
        logging.debug(f"Видео: fps={fps}, длительность={video_info.get('duration', 0)}с, всего кадров≈{total_frames}")
        logging.debug(f"Вызов ffmpeg_handler.extract_frame -> {output_path}")
        success, msg = self.ffmpeg_handler.extract_frame(
            input_path, output_path, frame_number, fps, process_setter
        )
        
        if not success:
            logging.error(f"Ошибка извлечения кадра: {msg}")
            raise Exception(f"Ошибка при извлечении кадра: {msg}")
        
        logging.info(f"Кадр #{frame_number} успешно сохранён в {output_path}")
        return output_path

    def trim_video(self, input_path: str, seconds: float, from_start: bool, 
                   progress_callback: Optional[Callable] = None,
                   process_setter: Optional[Callable] = None,
                   output_dir: Optional[str] = None) -> str:
        """Метод для сокращения видео"""
        logging.debug(f"Starting trim operation: remove {seconds}s from {'start' if from_start else 'end'}")
        
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
            
        # Рассчитываем параметры обрезки
        if from_start:
            # Удаляем с начала: старт сдвигается, длительность уменьшается
            start_time = seconds
            new_duration = total_duration - seconds
        else:
            # Удаляем с конца: старт 0, длительность уменьшается
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
                logging.error(f"Error deleting existing file: {e}")
        
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
        logging.debug(f"Starting audio volume normalization: {input_path}")
        
        input_p = Path(input_path)
        
        if output_dir:
            output_path = Path(output_dir) / f"{input_p.stem}_volnorm{input_p.suffix}"
        else:
            output_path = input_p.with_name(f"{input_p.stem}_volnorm{input_p.suffix}")
            
        if output_path.exists():
            try:
                output_path.unlink()
            except Exception as e:
                logging.error(f"Error deleting existing file: {e}")
        
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