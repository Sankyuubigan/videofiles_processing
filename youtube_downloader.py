import os
import yt_dlp

# --- НАСТРОЙКИ ПУТЕЙ ---
# Укажите пути к файлам. Скрипт должен лежать в той же папке.
COOKIE_FILE = "cookies.txt"
FFMPEG_FILE = "ffmpeg.exe"
DOWNLOAD_FOLDER = "downloads"

def download_video(url: str, quality: str = '1080p'):
    """
    Скачивает видео с YouTube используя cookies.txt и клиент 'tv'.
    """
    print("--- Начинаю скачивание ---")
    
    # 1. Проверяем, что все файлы на месте
    if not os.path.exists(COOKIE_FILE):
        print(f"!!! ОШИБКА: Файл {COOKIE_FILE} не найден! Смотрите инструкцию.")
        return
    if not os.path.exists(FFMPEG_FILE):
        print(f"!!! ОШИБКА: Файл {FFMPEG_FILE} не найден! Скачайте его.")
        return

    # 2. Создаем папку для загрузок
    if not os.path.exists(DOWNLOAD_FOLDER):
        os.makedirs(DOWNLOAD_FOLDER)
        print(f"--- Создана папка: {DOWNLOAD_FOLDER}")

    # 3. Настройки yt-dlp
    ydl_opts = {
        'cookiefile': COOKIE_FILE,  # Используем наш файл cookies
        'ffmpeg_location': FFMPEG_FILE, # Указываем, где лежит ffmpeg
        'format': f'bestvideo[height<={quality}]+bestaudio/best[height<={quality}]',
        'outtmpl': os.path.join(DOWNLOAD_FOLDER, '%(title)s.%(ext)s'),
        'merge_output_format': 'mp4',
        'noplaylist': True,
        # 'tv' клиент - самый стабильный, не требует PO токенов
        'extractor_args': {'youtube': {'player_client': ['tv']}},
    }

    # 4. Запуск скачивания
    try:
        print(f"--- Скачиваю видео: {url}")
        print(f"--- Качество: {quality} или лучшее доступное")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        print("\n✅ ГОТОВО! Видео скачано в папку 'downloads'")
    except Exception as e:
        print(f"\n❌ ПРОВАЛ! Произошла ошибка:")
        print(f"Причина: {e}")
        print("\nПопробуйте:")
        print("1. Обновить yt-dlp: pip install --upgrade yt-dlp")
        print("2. Проверить, что вы вошли в аккаунт при экспорте cookies.txt")
        print("3. Попробовать другое качество (например, '720p')")

if __name__ == '__main__':
    # --- ЗАПУСК ---
    # Вставьте сюда URL видео
    video_url = "https://youtu.be/8-z9t7wmrWs"
    
    # Запускаем функцию скачивания
    download_video(video_url, quality='1080p')