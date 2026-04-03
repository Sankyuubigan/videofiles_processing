"""
Модуль для извлечения CRF (Constant Rate Factor) из видеофайлов через pymediainfo.
"""
import logging
import re
from typing import Optional

try:
    from pymediainfo import MediaInfo
    _MEDIAINFO_AVAILABLE = True
except ImportError:
    _MEDIAINFO_AVAILABLE = False
    logging.warning("pymediainfo не установлена. CRF не будет определяться.")


def get_crf_from_file(file_path: str) -> Optional[float]:
    """
    Извлекает CRF значение из метаданных видеофайла.
    
    Args:
        file_path: Путь к видеофайлу.
        
    Returns:
        CRF значение (float) если найдено, иначе None.
    """
    logging.debug(f"Начало извлечения CRF из файла: {file_path}")
    
    if not _MEDIAINFO_AVAILABLE:
        logging.debug("pymediainfo недоступна, пропуск извлечения CRF")
        return None
    
    try:
        media_info = MediaInfo.parse(file_path)
        logging.debug(f"MediaInfo успешно распарсил файл: {file_path}")
    except Exception as e:
        logging.warning(f"Не удалось распарсить файл через pymediainfo: {file_path}. Ошибка: {e}")
        return None
    
    video_tracks_found = False
    for track in media_info.tracks:
        if track.track_type == "Video":
            video_tracks_found = True
            encoding_settings = getattr(track, 'encoding_settings', None)
            
            if encoding_settings:
                logging.debug(f"Найдена строка encoding_settings для {file_path}: {encoding_settings}")
                # Ищем параметр crf=число (целое или дробное)
                match = re.search(r'crf=(\d+\.?\d*)', encoding_settings, re.IGNORECASE)
                if match:
                    crf_value = float(match.group(1))
                    logging.info(f"CRF найден для {file_path}: {crf_value}")
                    return crf_value
                else:
                    logging.debug(f"CRF не найден в encoding_settings для {file_path}")
            else:
                logging.debug(f"encoding_settings отсутствует для {file_path} (метаданные удалены или не записаны)")
    
    if not video_tracks_found:
        logging.warning(f"Видеодорожки не найдены в файле: {file_path}")
    
    logging.debug(f"CRF не найден в файле: {file_path}")
    return None


def format_crf_display(crf_value: Optional[float]) -> str:
    """
    Форматирует CRF значение для отображения в таблице.
    
    Args:
        crf_value: CRF значение или None.
        
    Returns:
        Строка для отображения: "нет" если CRF не найден, иначе строковое представление.
    """
    if crf_value is not None:
        # Если целое число — показываем без десятичной части
        if crf_value == int(crf_value):
            return str(int(crf_value))
        return f"{crf_value:.1f}"
    return "нет"
