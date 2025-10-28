"""
Основной класс для обработки видео
"""
import logging
from pathlib import Path
from typing import Optional, Callable
from config import COMPRESSED_VIDEO_SUFFIX
from video_size_estimator import VideoSizeEstimator
from ffmpeg_handler import FFmpegHandler


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
        
        # Добавляем вычисленные поля в информацию
        video_info.update({
            "estimated_size_mb": est_size,
            "gpu_info": gpu_info,
            "processing_mode": "GPU" if "Доступные GPU" in gpu_info else "CPU",
            "complexity_score": complexity_score,
            "complexity_desc": complexity_desc
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