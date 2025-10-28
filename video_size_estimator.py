"""
Модуль для оценки размера видео после сжатия
"""
from config import CODECS


class VideoSizeEstimator:
    """Класс для оценки размера видео после сжатия"""
    
    def __init__(self):
        pass
    
    def get_min_effective_bitrate(self, width: int, height: int, crf: int, codec: str) -> int:
        """
        Возвращает минимальный эффективный битрейт для заданных параметров.
        Возвращает значение в битах в секунду (bps).
        """
        # Базовые значения для H.264 при CRF 23 (в кбит/с)
        if width >= 3840:  # 4K
            base_bitrate_kbps = 8000
        elif width >= 1920:  # 1080p
            base_bitrate_kbps = 2500
        elif width >= 1280:  # 720p
            base_bitrate_kbps = 1200
        else:  # <720p
            base_bitrate_kbps = 600
        
        # Корректировка в зависимости от CRF
        # Чем ниже CRF, тем выше минимальный битрейт
        crf_adjustment = 1.0 + (23 - crf) * 0.15
        
        # Корректировка в зависимости от кодека
        if codec == "libx265":
            codec_adjustment = 0.7  # H.265 эффективнее
        elif codec == "libvpx-vp9":
            codec_adjustment = 0.8
        else:  # libx264
            codec_adjustment = 1.0
        
        # Рассчитываем в кбит/с, затем конвертируем в бит/с
        min_bitrate_kbps = base_bitrate_kbps * crf_adjustment * codec_adjustment
        min_bitrate_bps = int(min_bitrate_kbps * 1000)
        
        print(f"[DEBUG] _get_min_effective_bitrate: width={width}, height={height}, crf={crf}, codec={codec}")
        print(f"[DEBUG] _get_min_effective_bitrate: base_bitrate_kbps={base_bitrate_kbps}, crf_adjustment={crf_adjustment}, codec_adjustment={codec_adjustment}")
        print(f"[DEBUG] _get_min_effective_bitrate: calculated min_bitrate_kbps={min_bitrate_kbps:.2f}, min_bitrate_bps={min_bitrate_bps}")
        
        return min_bitrate_bps
    
    def calculate_bitrate_efficiency(self, video_bitrate: int, duration: float) -> float:
        """
        Вычисляет эффективность битрейта видео.
        Возвращает коэффициент, который корректирует предсказание размера на основе реального битрейта.
        """
        # Для коротких видео (< 5 минут) эффективность битрейта ниже
        if duration < 300:  # 5 минут
            return 1.1  # Сжатие будет менее эффективным
        
        # Для очень длинных видео (> 2 часов) эффективность битрейта выше
        if duration > 7200:  # 2 часа
            return 0.9  # Сжатие будет более эффективным
        
        # Для среднего диапазона длительности, корректируем на основе битрейта
        # Высокий битрейт (> 8000 кбит/с) обычно указывает на низкую эффективность сжатия
        if video_bitrate > 8000000:  # 8000 кбит/с
            return 0.85  # Сжатие будет более эффективным
        
        # Низкий битрейт (< 2000 кбит/с) обычно указывает на уже сжатое видео
        if video_bitrate < 2000000:  # 2000 кбит/с
            return 1.15  # Сжатие будет менее эффективным
        
        # Для среднего битрейта корректировка минимальна
        return 1.0
    
    def get_preset_factor(self, codec: str, preset: str) -> float:
        """
        Возвращает поправочный коэффициент для пресета кодирования.
        """
        codec_info = CODECS.get(codec, None)
        if not codec_info:
            return 1.0
        
        preset_factors = codec_info.get("preset_factor", {})
        return preset_factors.get(preset, 1.0)
    
    def calculate_compression_factor(self, crf: int, codec: str, use_hardware: bool = False) -> float:
        """
        Вычисляет базовый коэффициент сжатия на основе CRF и кодека
        """
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
    
    def estimate_size_mb(self, video_bitrate: int, audio_bitrate: int, duration: float, crf: int, codec: str, 
                        needs_vfr_fix: bool = False, use_hardware: bool = False, preset: str = "medium", 
                        complexity_score: int = 5, width: int = 1920, height: int = 1080) -> float:
        """
        Улучшенная функция оценки размера файла после сжатия.
        Учитывает реальный битрейт видео, сложность видео, пресет кодирования и минимальные пороги.
        """
        if video_bitrate <= 0 or duration <= 0:
            print(f"[DEBUG] estimated_size_mb: Invalid input. video_bitrate={video_bitrate}, duration={duration}")
            return 0.0
        
        # Проверяем, не ниже ли текущий битрейт минимального эффективного
        min_effective_bitrate = self.get_min_effective_bitrate(width, height, crf, codec)
        print(f"[DEBUG] estimated_size_mb: Current bitrate={video_bitrate//1000} kbps, Min effective bitrate={min_effective_bitrate//1000} kbps")
        
        # Базовый размер файла на основе текущего битрейта
        total_bitrate = video_bitrate + audio_bitrate
        base_size = (total_bitrate * duration) / 8 / (1024 * 1024)  # в МБ
        
        print(f"[DEBUG] estimated_size_mb: Video bitrate={video_bitrate} bit/s, Audio bitrate={audio_bitrate} bit/s")
        print(f"[DEBUG] estimated_size_mb: Base size (MB): {base_size:.2f}")
        
        # НОВАЯ ЛОГИКА: Проверяем соотношение битрейтов
        bitrate_ratio = video_bitrate / min_effective_bitrate
        print(f"[DEBUG] estimated_size_mb: Bitrate ratio (current/min_effective) = {bitrate_ratio:.2f}")
        
        # Если битрейт близок к минимальному эффективному (менее чем на 30% выше)
        if bitrate_ratio < 1.3:
            print(f"[DEBUG] estimated_size_mb: WARNING - Bitrate is close to minimum effective threshold!")
            print(f"[DEBUG] estimated_size_mb: Re-encoding already compressed video may INCREASE size!")
            
            # При перекодировании уже сжатого видео размер может увеличиться на 5-20%
            # из-за потери эффективности сжатия
            
            # Аудио будет перекодировано в стандартный битрейт
            estimated_audio_bitrate = 192000  # Стандартный 192 kbps для AAC
            
            # Видео битрейт может измениться в зависимости от CRF
            # Для CRF 24 и битрейта близкого к минимуму, размер может увеличиться
            if crf <= 23:  # Низкий CRF - высокое качество
                estimated_video_bitrate = video_bitrate * 1.15  # Увеличение на 15%
            elif crf <= 26:  # Средний CRF
                estimated_video_bitrate = video_bitrate * 1.08  # Увеличение на 8%
            else:  # Высокий CRF - низкое качество
                estimated_video_bitrate = video_bitrate * 1.03  # Увеличение на 3%
            
            total_estimated_bitrate = estimated_video_bitrate + estimated_audio_bitrate
            estimated_size = (total_estimated_bitrate * duration) / 8 / (1024 * 1024)
            
            print(f"[DEBUG] estimated_size_mb: Estimated video bitrate: {estimated_video_bitrate//1000} kbps")
            print(f"[DEBUG] estimated_size_mb: Estimated audio bitrate: {estimated_audio_bitrate//1000} kbps")
            print(f"[DEBUG] estimated_size_mb: Estimated size with re-encoding penalty: {estimated_size:.2f} MB")
            return estimated_size
        
        # Если текущий битрейт значительно ниже минимального эффективного
        if video_bitrate < min_effective_bitrate:
            print(f"[DEBUG] estimated_size_mb: WARNING - Current bitrate is below minimum effective threshold!")
            # В этом случае предсказываем, что размер будет близок к исходному или немного больше
            estimated_video_bitrate = min_effective_bitrate * 0.95  # Немного ниже минимума
            estimated_audio_bitrate = max(audio_bitrate, 192000)  # Минимум 192k для аудио
            total_estimated_bitrate = estimated_video_bitrate + estimated_audio_bitrate
            
            # Добавляем небольшой запас (5%) для учета неэффективности
            total_estimated_bitrate = int(total_estimated_bitrate * 1.05)
            
            estimated_size = (total_estimated_bitrate * duration) / 8 / (1024 * 1024)
            print(f"[DEBUG] estimated_size_mb: Estimated size with low bitrate: {estimated_size:.2f} MB")
            return estimated_size
        
        # Для нормальных случаев - используем стандартную логику сжатия
        # Получаем базовый коэффициент сжатия для CRF
        target_factor = self.calculate_compression_factor(crf, codec, use_hardware)
        print(f"[DEBUG] estimated_size_mb: Target CRF={crf}, Base factor={target_factor:.4f}")
        
        # Корректируем коэффициент с учетом сложности видео
        complexity_adjustment = 1.0 + (complexity_score - 5) * 0.05  # от 0.75 до 1.25
        print(f"[DEBUG] estimated_size_mb: Complexity score={complexity_score}, Adjustment={complexity_adjustment:.4f}")
        
        # Корректируем коэффициент с учетом реального битрейта
        bitrate_efficiency = self.calculate_bitrate_efficiency(video_bitrate, duration)
        print(f"[DEBUG] estimated_size_mb: Bitrate efficiency factor={bitrate_efficiency:.4f}")
        
        # Применяем поправочный коэффициент для пресета
        preset_factor = self.get_preset_factor(codec, preset)
        print(f"[DEBUG] estimated_size_mb: Preset={preset}, Preset factor={preset_factor:.4f}")
        
        # Дополнительная корректировка для видео с низким/средним битрейтом
        if video_bitrate < 3000000:  # < 3000 кбит/с
            low_bitrate_penalty = 1.0 + (3000000 - video_bitrate) / 10000000  # от 1.0 до 1.3
            print(f"[DEBUG] estimated_size_mb: Low bitrate penalty factor: {low_bitrate_penalty:.4f}")
        else:
            low_bitrate_penalty = 1.0
        
        # Итоговый коэффициент сжатия
        final_factor = target_factor * complexity_adjustment * bitrate_efficiency * preset_factor * low_bitrate_penalty
        print(f"[DEBUG] estimated_size_mb: Final compression factor={final_factor:.4f}")
        
        # Расчетный размер
        estimated_size = base_size * final_factor
        
        # Если требуется VFR-fix, добавляем дополнительный этап сжатия
        if needs_vfr_fix:
            fix_crf = 15 if codec == "libvpx-vp9" else (20 if codec == "libx265" else 18)
            fix_factor = self.calculate_compression_factor(fix_crf, codec, use_hardware)
            print(f"[DEBUG] estimated_size_mb: VFR-fix needed. Fix CRF={fix_crf}, Fix factor={fix_factor:.4f}")
            # Для VFR-fix применяем те же корректировки, но с меньшим весом
            fix_final_factor = fix_factor * 1.05 * preset_factor  # Упрощенная формула для VFR-fix
            estimated_size = base_size * fix_final_factor * final_factor
            print(f"[DEBUG] estimated_size_mb: Estimated size with VFR-fix: {estimated_size:.2f} MB")
        else:
            print(f"[DEBUG] estimated_size_mb: Estimated size without VFR-fix: {estimated_size:.2f} MB")
            
        return max(0.1, estimated_size)
    
    def estimate_video_complexity(self, video_info: dict) -> tuple[int, str]:
        """
        Оценивает сложность видео по его техническим характеристикам.
        Возвращает кортеж (оценка от 1 до 10) и текстовое описание.
        """
        score = 0
        width = video_info.get("width", 0)
        height = video_info.get("height", 0)
        fps = video_info.get("fps", 0)
        duration = video_info.get("duration", 0)
        video_bitrate = video_info.get("video_bitrate", 0)
        video_codec = video_info.get("video_codec", "").lower()
        pixel_format = video_info.get("pixel_format", "")
        needs_vfr_fix = video_info.get("needs_vfr_fix", False)

        # 1. Базовая оценка по битрейту (самый важный фактор)
        # Сравниваем с типичным битрейтом для 1080p
        if width >= 3840: # 4K
            typical_bitrate = 15000
        elif width >= 1920: # 1080p
            typical_bitrate = 5000
        elif width >= 1280: # 720p
            typical_bitrate = 3000
        else: # <720p
            typical_bitrate = 1500

        if duration > 0:
            bitrate_ratio = video_bitrate / typical_bitrate
            if bitrate_ratio > 2.0:
                score += 4  # Очень высокий битрейт для разрешения
            elif bitrate_ratio > 1.2:
                score += 2  # Высокий битрейт
            elif bitrate_ratio < 0.5:
                score -= 2  # Низкий битрейт (уже сжато или простое)

        # 2. Наказатель за Variable Frame Rate (VFR)
        if needs_vfr_fix:
            score += 2

        # 3. Наказатель за высокое разрешение
        if width >= 3840: score += 2  # 4K
        elif width >= 2560: score += 1 # 2.5K

        # 4. Наказатель за высокую частоту кадров
        if fps > 50:
            score += 1

        # 5. Наказатель за "сырой" или неэффективный кодек
        if video_codec in ['mpeg2', 'mpeg4', 'dvvideo', 'h263', 'msmpeg4']:
            score += 2
        
        # 6. Наказатель за 10-битный цвет (обычно требует больше данных)
        if pixel_format.endswith('10le') or pixel_format.endswith('10be'):
            score += 1

        # Ограничиваем score в диапазоне 1-10
        score = max(1, min(10, score))

        if score <= 3:
            description = "Низкая"
        elif score <= 6:
            description = "Средняя"
        else:
            description = "Высокая"
            
        return score, description