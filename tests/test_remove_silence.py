import subprocess
import re
import os
import sys

def auto_edit_video(input_file, ffmpeg_path):
    """
    input_file: путь к видео
    ffmpeg_path: путь к ffmpeg.exe (например, 'ffmpeg.exe' если он в той же папке)
    """
    
    # 1. Проверяем пути
    if not os.path.isfile(input_file):
        print(f"Ошибка: Файл видео '{input_file}' не найден.")
        return
    if not os.path.isfile(ffmpeg_path):
        print(f"Ошибка: Файл ffmpeg не найден по пути '{ffmpeg_path}'.")
        return

    # Настройки
    THRESHOLD = 0.005 # 0.5% громкости
    MARGIN = 0.2      # 0.2 сек отступа
    MIN_SILENCE_LEN = 0.1 

    base_name, ext = os.path.splitext(input_file)
    output_file = f"{base_name}_cut{ext}"
    list_file = f"{base_name}_segments.txt"

    print(f"--- Анализ файла: {input_file} ---")

    # 2. Команда для анализа (используем ваш локальный ffmpeg_path)
    cmd_detect = [
        ffmpeg_path,
        '-hide_banner',
        '-i', input_file,
        '-af', f'silencedetect=noise={THRESHOLD}:d={MIN_SILENCE_LEN}',
        '-f', 'null',
        '-'
    ]

    try:
        # Важно: encoding='utf-8' может вызвать ошибку на Windows с русскими буквами в консоли,
        # поэтому иногда безопаснее не указывать его или использовать 'cp1251', 
        # но для silencedetect обычно utf-8 или дефолт работает.
        result = subprocess.run(cmd_detect, stderr=subprocess.PIPE, text=True)
        output = result.stderr
    except Exception as e:
        print(f"Ошибка запуска FFmpeg: {e}")
        return

    # 3. Парсинг (без изменений)
    duration_match = re.search(r'Duration: (\d{2}):(\d{2}):(\d{2}\.\d{2})', output)
    if not duration_match:
        print("Не удалось определить длительность (возможно, путь к файлу содержит странные символы).")
        return
    
    h, m, s = map(float, duration_match.groups())
    total_duration = h * 3600 + m * 60 + s

    silence_starts = [float(x) for x in re.findall(r'silence_start: ([\d\.]+)', output)]
    silence_ends = [float(x) for x in re.findall(r'silence_end: ([\d\.]+)', output)]
    
    if len(silence_starts) > len(silence_ends):
        silence_ends.append(total_duration)

    silences = list(zip(silence_starts, silence_ends))
    
    if not silences:
        print("Тишина не найдена.")
        return

    # 4. Расчет сегментов (без изменений)
    keep_segments = []
    current_pos = 0.0

    for start_silence, end_silence in silences:
        cut_out_point = start_silence + MARGIN
        cut_in_point = end_silence - MARGIN

        if cut_out_point >= cut_in_point:
            continue

        if cut_out_point > current_pos:
            keep_segments.append((current_pos, cut_out_point))
        
        current_pos = max(0.0, cut_in_point)

    if current_pos < total_duration:
        keep_segments.append((current_pos, total_duration))

    print(f"Останется сегментов: {len(keep_segments)}")

    # 5. Создаем список для ffmpeg
    # Важно: абсолютный путь для concat файла лучше приводить к слешам /
    abs_input_path = os.path.abspath(input_file).replace('\\', '/')
    
    with open(list_file, 'w', encoding='utf-8') as f:
        for start, end in keep_segments:
            # Экранирование кавычек
            safe_path = abs_input_path.replace("'", "'\\''")
            f.write(f"file '{safe_path}'\n")
            f.write(f"inpoint {start:.3f}\n")
            f.write(f"outpoint {end:.3f}\n")

    # 6. Рендеринг (используем ваш локальный ffmpeg_path)
    cmd_render = [
        ffmpeg_path,
        '-y',
        '-hide_banner',
        '-v', 'error',
        '-stats',
        '-f', 'concat',
        '-safe', '0',
        '-i', list_file,
        '-c:v', 'libx264',
        '-preset', 'superfast', # Для тестов быстрее, для качества ставьте medium
        '-c:a', 'aac',
        '-b:a', '192k',
        output_file
    ]

    print(f"Рендеринг в {output_file}...")
    subprocess.run(cmd_render)

    if os.path.exists(list_file):
        os.remove(list_file)
    print("Готово.")

# --- Пример использования ---
if __name__ == "__main__":
    # Укажите путь к вашему exe. 
    # Если он лежит рядом со скриптом:
    LOCAL_FFMPEG = os.path.join(os.path.dirname(__file__), "ffmpeg.exe")
    
    # Или просто жестко задайте:
    # LOCAL_FFMPEG = r"C:\MyProject\bin\ffmpeg.exe"

    target_video = r"input.mp4" # Ваше видео

    auto_edit_video(target_video, LOCAL_FFMPEG)