"""
Модуль для оценки размера видео после сжатия
"""
import logging
from config import CODECS
import os


class VideoSizeEstimator:
    """Класс для оценки размера видео после сжатия"""
    
    def __init__(self):
        # Базовый эталон - Intel i7-10700K (средний игровой процессор)
        self.benchmark_cpu_score = 1000  # 1000 баллов для базового CPU
        self.cpu_score = self._detect_cpu_performance()
        logging.debug(f"Detected CPU performance score: {self.cpu_score}")
    
    def _detect_cpu_performance(self) -> int:
        """
        Определяет примерную производительность CPU на основе информации о системе
        Возвращает оценку производительности (1000 = средний игровой CPU)
        """
        try:
            # Пытаемся получить информацию о CPU
            if os.name == 'nt':  # Windows
                import platform
                import subprocess
                
                # Получаем информацию о процессоре через wmic
                result = subprocess.run(
                    ['wmic', 'cpu', 'get', 'name,NumberOfCores,MaxClockSpeed', '/format:list'],
                    capture_output=True, text=True, timeout=5
                )
                
                if result.returncode == 0:
                    cpu_info = result.stdout
                    # Парсим информацию
                    score = 0
                    
                    # Определяем модель процессора
                    if 'Intel' in cpu_info:
                        if 'i9' in cpu_info or 'Xeon' in cpu_info:
                            score = 1500  # Высокопроизводительный
                        elif 'i7' in cpu_info:
                            if '10900' in cpu_info or '11700' in cpu_info or '12700' in cpu_info or '13700' in cpu_info:
                                score = 1200  # Современный i7
                            elif '10700' in cpu_info or '9700' in cpu_info or '8700' in cpu_info:
                                score = 1000  # Средний i7
                            else:
                                score = 800  # Старый i7
                        elif 'i5' in cpu_info:
                            if '12600' in cpu_info or '13600' in cpu_info:
                                score = 900  # Современный i5
                            elif '10600' in cpu_info or '11400' in cpu_info or '12400' in cpu_info:
                                score = 700  # Средний i5
                            else:
                                score = 600  # Старый i5
                        elif 'i3' in cpu_info:
                            score = 400  # i3
                        else:
                            score = 500  # Другой Intel
                    
                    elif 'AMD' in cpu_info:
                        if 'Ryzen 9' in cpu_info:
                            score = 1400  # Высокопроизводительный Ryzen
                        elif 'Ryzen 7' in cpu_info:
                            if '5800' in cpu_info or '7700' in cpu_info or '7950' in cpu_info:
                                score = 1200  # Современный Ryzen 7
                            elif '5700' in cpu_info or '5600' in cpu_info:
                                score = 1000  # Средний Ryzen 7
                            else:
                                score = 800  # Старый Ryzen 7
                        elif 'Ryzen 5' in cpu_info:
                            if '7600' in cpu_info or '7500' in cpu_info:
                                score = 900  # Современный Ryzen 5
                            elif '5600' in cpu_info or '5500' in cpu_info:
                                score = 700  # Средний Ryzen 5
                            else:
                                score = 600  # Старый Ryzen 5
                        elif 'Ryzen 3' in cpu_info:
                            score = 500  # Ryzen 3
                        else:
                            score = 600  # Другой AMD
                    
                    # Корректировка на количество ядер
                    if 'NumberOfCores' in cpu_info:
                        try:
                            lines = cpu_info.split('\n')
                            for line in lines:
                                if 'NumberOfCores' in line:
                                    cores = int(line.split('=')[1].strip())
                                    if cores >= 16:
                                        score = int(score * 1.3)  # Многоядерные CPU быстрее
                                    elif cores >= 12:
                                        score = int(score * 1.2)
                                    elif cores >= 8:
                                        score = int(score * 1.1)
                                    elif cores <= 4:
                                        score = int(score * 0.8)  # Малоядерные медленнее
                                    break
                        except:
                            pass
                    
                    # Корректировка на частоту
                    if 'MaxClockSpeed' in cpu_info:
                        try:
                            lines = cpu_info.split('\n')
                            for line in lines:
                                if 'MaxClockSpeed' in line:
                                    mhz = int(line.split('=')[1].strip())
                                    ghz = mhz / 1000
                                    if ghz >= 5.0:
                                        score = int(score * 1.2)  # Высокая частота
                                    elif ghz >= 4.0:
                                        score = int(score * 1.1)
                                    elif ghz <= 2.5:
                                        score = int(score * 0.9)  # Низкая частота
                                    break
                        except:
                            pass
                    
                    logging.debug(f"CPU detection result: score={score}")
                    return score
            
            # Для Linux/Mac - используем platform.processor
            import platform
            cpu_name = platform.processor()
            
            if 'Intel' in cpu_name:
                if 'i9' in cpu_name or 'Xeon' in cpu_name:
                    return 1500
                elif 'i7' in cpu_name:
                    return 1000
                elif 'i5' in cpu_name:
                    return 700
                elif 'i3' in cpu_name:
                    return 400
                else:
                    return 600
            elif 'AMD' in cpu_name:
                if 'Ryzen 9' in cpu_name:
                    return 1400
                elif 'Ryzen 7' in cpu_name:
                    return 1000
                elif 'Ryzen 5' in cpu_name:
                    return 700
                elif 'Ryzen 3' in cpu_name:
                    return 500
                else:
                    return 600
            else:
                return 800  # По умолчанию для неизвестных CPU
                
        except Exception as e:
            logging.debug(f"CPU detection failed: {e}")
            return 800  # Значение по умолчанию при ошибке
    
    def estimate_compression_time(self, duration: float, width: int, height: int, preset: str, 
                                codec: str = "libx264", use_hardware: bool = False) -> float:
        """
        Оценивает время сжатия в секундах с учетом производительности CPU.
        """
        # Базовые коэффициенты времени для разных пресетов (для эталонного CPU)
        preset_time_factors = {
            "ultrafast": 0.02, "veryfast": 0.04, "faster": 0.06, "fast": 0.1,
            "medium": 0.15, "slow": 0.2, "slower": 0.25, "veryslow": 0.35
        }
        
        base_factor = preset_time_factors.get(preset, 0.15)
        
        # Корректировка в зависимости от разрешения
        resolution_factor = 1.5 if width >= 3840 else (1.0 if width >= 1920 else (0.7 if width >= 1280 else 0.5))
        
        # Корректировка в зависимости от кодека
        codec_factor = {"libx265": 1.2, "libvpx-vp9": 1.3}.get(codec, 1.0)
        
        # Аппаратное ускорение
        hardware_factor = 0.05 if use_hardware else 1.0
        
        # Корректировка на производительность CPU
        cpu_factor = self.benchmark_cpu_score / self.cpu_score
        
        # Дополнительная корректировка для очень длинных видео
        duration_factor = 0.9 if duration > 3600 else (0.95 if duration > 1800 else 1.0)
        
        total_factor = base_factor * resolution_factor * codec_factor * hardware_factor * cpu_factor * duration_factor
        estimated_time = duration * total_factor
        
        logging.debug(f"Estimating time: duration={duration:.1f}s, preset={preset}, codec={codec}, hw={use_hardware}")
        logging.debug(f"Factors: base={base_factor}, res={resolution_factor}, codec={codec_factor}, hw={hardware_factor}, cpu={cpu_factor:.2f}, dur={duration_factor}")
        logging.debug(f"Total factor: {total_factor:.2f}, Estimated time: {estimated_time:.1f}s")
        
        return estimated_time
    
    def format_duration(self, seconds: float) -> str:
        """Форматирует длительность в читаемый вид (ЧЧ:ММ:СС)"""
        if seconds < 60:
            return f"{int(seconds)}с"
        elif seconds < 3600:
            minutes, secs = divmod(int(seconds), 60)
            return f"{minutes}м {secs}с"
        else:
            hours, remainder = divmod(int(seconds), 3600)
            minutes, secs = divmod(remainder, 60)
            return f"{hours}ч {minutes}м {secs}с"

    def estimate_video_complexity(self, video_info: dict) -> tuple[int, str]:
        """Оценивает сложность видео по его техническим характеристикам."""
        score = 0
        width = video_info.get("width", 0)
        height = video_info.get("height", 0)
        fps = video_info.get("fps", 0)
        duration = video_info.get("duration", 0)
        video_bitrate = video_info.get("video_bitrate", 0)
        video_codec = video_info.get("video_codec", "").lower()
        pixel_format = video_info.get("pixel_format", "")
        needs_vfr_fix = video_info.get("needs_vfr_fix", False)

        # 1. Оценка по битрейту относительно разрешения
        typical_bitrate = 15000 if width >= 3840 else (5000 if width >= 1920 else (3000 if width >= 1280 else 1500))
        if duration > 0:
            bitrate_ratio = video_bitrate / typical_bitrate
            if bitrate_ratio > 2.0: score += 4
            elif bitrate_ratio > 1.2: score += 2
            elif bitrate_ratio < 0.5: score -= 2

        # 2. Наказатели за особенности видео
        if needs_vfr_fix: score += 2
        if width >= 3840: score += 2
        elif width >= 2560: score += 1
        if fps > 50: score += 1
        if video_codec in ['mpeg2', 'mpeg4', 'dvvideo', 'h263', 'msmpeg4']: score += 2
        if pixel_format.endswith('10le') or pixel_format.endswith('10be'): score += 1

        score = max(1, min(10, score))
        description = "Низкая" if score <= 3 else ("Средняя" if score <= 6 else "Высокая")
        return score, description

    def estimate_size_mb(self, video_bitrate: int, audio_bitrate: int, duration: float, crf: int, codec: str, 
                        needs_vfr_fix: False, use_hardware: bool = False, preset: str = "medium", 
                        complexity_score: int = 5, width: int = 1920, height: int = 1080) -> float:
        """
        Эмпирическая оценка размера файла, основанная на наблюдении за поведением кодировщика.
        """
        if video_bitrate <= 0 or duration <= 0:
            return 0.0

        logging.debug(f"--- Estimating size (Empirical Model) ---")
        logging.debug(f"Input: source_bitrate={video_bitrate//1000}kbps, duration={duration:.2f}s, codec={codec}, crf={crf}")

        # Эмпирические коэффициенты сжатия для libx264, основанные на ваших реальных данных для 4K видео.
        # Они показывают, какую долю от исходного битрейта займет итоговый файл.
        # CRF 24 для 4K видео дает итоговый размер ~2.3-2.4 ГБ из ~5.8-6.1 ГБ.
        # Это означает, что коэффициент ~0.38-0.42
        crf_ratios_h264_4k = {
            18: 0.90, 19: 0.80, 20: 0.70, 21: 0.60, 22: 0.55,
            23: 0.50, 24: 0.42, 25: 0.38, 26: 0.34, 27: 0.30,
            28: 0.26, 29: 0.23, 30: 0.20, 31: 0.18, 32: 0.16,
            33: 0.15, 34: 0.14, 35: 0.13
        }

        # Базовый коэффициент для H.264 (используем 4K как эталон)
        base_ratio = crf_ratios_h264_4k.get(crf, 0.42)
        
        # Корректируем в зависимости от разрешения.
        # Для 1080p и ниже, сжатие более эффективное, поэтому коэффициент выше.
        if width < 1920:
            base_ratio *= 1.2
        elif width < 1280:
            base_ratio *= 1.4

        # Корректируем в зависимости от эффективности кодека
        # H.265 и VP9 более эффективны, поэтому при том же CRF дадут меньший размер
        codec_adjustment = {"libx265": 0.85, "libvpx-vp9": 0.90}.get(codec, 1.0)
        
        # Итоговый коэффициент
        final_ratio = base_ratio * codec_adjustment
        
        # Рассчитываем целевой битрейт видео
        source_bitrate_kbps = video_bitrate / 1000
        target_video_bitrate_kbps = source_bitrate_kbps * final_ratio

        # Программа всегда перекодирует аудио в AAC 192kbps
        target_audio_bitrate_kbps = 192

        # Рассчитываем итоговый размер
        total_target_bitrate_kbps = target_video_bitrate_kbps + target_audio_bitrate_kbps
        estimated_size_mb = (total_target_bitrate_kbps * duration) / 8 / 1024

        logging.debug(f"CRF ratio: {final_ratio:.2f}, Target video bitrate: {target_video_bitrate_kbps:.0f} kbps")
        logging.debug(f"Final estimated size: {estimated_size_mb:.2f} MB")
        logging.debug(f"--- End of estimation ---")
        
        return max(0.1, estimated_size_mb)