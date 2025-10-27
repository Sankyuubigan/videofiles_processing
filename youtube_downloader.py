import yt_dlp
import os

# --- Новая, более мощная базовая конфигурация ---
# Эти опции помогают обойти большинство блокировок, имитируя мобильное устройство.
YDL_OPTS_BASE = {
    'quiet': True,
    'no_warnings': True,
    'no_check_certificate': True,
    # Имитируем Android-клиент YouTube. Это самый надежный способ на данный момент.
    'extractor_args': {
        'youtube': {
            'player_client': ['android'] 
        }
    },
    'postprocessors': [{
        'key': 'FFmpegVideoConvertor',
        'preferedformat': 'mp4',
    }],
}

def download_video(url: str, output_path: str):
    # Копируем базовые опции
    ydl_opts = YDL_OPTS_BASE.copy()
    # Добавляем специфичные для видео
    ydl_opts.update({
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best', # Сначала пробуем лучшее качество, потом любой mp4
        'outtmpl': output_path,
    })

    print(f"Начинаю скачивание видео: {url}")
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        print(f"Видео успешно скачано и сохранено в: {output_path}")
    except Exception as e:
        print(f"Произошла ошибка при скачивании видео: {e}")
        print("Попробуйте изменить формат на 'best', если ошибка повторяется.")

def download_playlist(playlist_url: str, output_folder: str):
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
        print(f"Создана папка: {output_folder}")

    output_template = os.path.join(output_folder, '%(title)s [%(id)s].%(ext)s')
    
    ydl_opts = YDL_OPTS_BASE.copy()
    ydl_opts.update({
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': output_template,
    })

    print(f"Начинаю скачивание плейлиста: {playlist_url}")
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([playlist_url])
        print(f"Плейлист успешно скачан. Видео сохранены в папке: {output_folder}")
    except Exception as e:
        print(f"Произошла ошибка при скачивании плейлиста: {e}")
        print("Попробуйте изменить формат на 'best', если ошибка повторяется.")

# --- Пример использования ---
if __name__ == "__main__":
    # Убедитесь, что вы выполнили Шаг 1 (обновление yt-dlp)
    
    video_url = "https://youtu.be/8-z9t7wmrWs"
    video_save_path = "./downloads/video.mp4"
    
    if not os.path.exists("./downloads"):
        os.makedirs("./downloads")
        
    download_video(video_url, video_save_path)

    # print("\n" + "="*40 + "\n")

    # playlist_url = "https://www.youtube.com/playlist?list=PL4o29bINVT4EG_y-k5jGoOu3-Am8Nvi10"
    # playlist_save_folder = "./downloads/my_playlist"
    
    # download_playlist(playlist_url, playlist_save_folder)