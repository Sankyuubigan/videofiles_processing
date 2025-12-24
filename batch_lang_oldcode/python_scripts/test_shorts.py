import srt
import torch
from transformers import pipeline
from moviepy.video.io.ffmpeg_tools import ffmpeg_extract_subclip
from moviepy.editor import VideoFileClip

# Загрузка модели для определения важности текста
summary_model = pipeline("summarization", model="facebook/bart-large-cnn")


def load_subtitles(srt_file):
    with open(srt_file, 'r', encoding='utf-8') as f:
        subtitles = list(srt.parse(f.read()))
    return subtitles


def summarize_subtitles(subtitles, max_length=60):
    """
    Функция для выделения ключевых моментов в субтитрах.
    Возвращает список временных меток ключевых фрагментов.
    """
    full_text = " ".join([sub.content for sub in subtitles])

    # Использование модели для суммаризации
    summary = summary_model(full_text, max_length=max_length, min_length=30, do_sample=False)

    # Поиск ключевых фрагментов в субтитрах
    summary_text = summary[0]['summary_text']
    key_subs = []

    for sub in subtitles:
        if any(phrase in sub.content for phrase in summary_text.split()):
            key_subs.append(sub)

    return key_subs


def cut_video_by_subtitles(video_file, key_subs, output_file):
    """
    Нарезает видео на основе временных меток ключевых субтитров.
    """
    clip = VideoFileClip(video_file)

    for i, sub in enumerate(key_subs):
        start_time = sub.start.total_seconds()
        end_time = sub.end.total_seconds()

        # Ограничиваем длительность фрагмента 60 секундами
        if end_time - start_time > 60:
            end_time = start_time + 60

        output_clip_name = f"{output_file}_clip_{i + 1}.mp4"
        ffmpeg_extract_subclip(video_file, start_time, end_time, targetname=output_clip_name)
        print(f"Вырезан фрагмент: {output_clip_name}")


# Основная функция
def process_video(video_file, srt_file, output_file):
    # Шаг 1: Загрузка субтитров
    subtitles = load_subtitles(srt_file)

    # Шаг 2: Определение ключевых моментов
    key_subs = summarize_subtitles(subtitles)

    # Шаг 3: Нарезка видео по ключевым моментам
    cut_video_by_subtitles(video_file, key_subs, output_file)



# Пример использования
video_file = 'E:\Downloads\\test залить на ютуб\тест антарктиду, купол и замысел создателя_res.mp4'
srt_file = 'E:\Downloads\создателя [DownSub.com].srt'
output_file = 'E:\Downloads\\test залить на ютуб\\123'

process_video(video_file, srt_file, output_file)