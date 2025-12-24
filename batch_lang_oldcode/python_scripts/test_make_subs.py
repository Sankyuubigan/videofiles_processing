import os
import subprocess
import wave
import numpy as np
from moviepy.editor import VideoFileClip
from pydub import AudioSegment
from transformers import pipeline


def extract_audio_from_video(video_path, audio_path):
    video_clip = VideoFileClip(video_path)
    video_clip.audio.write_audiofile(audio_path, codec='pcm_s16le')


def transcribe_audio(audio_path):
    # Используем модель Wav2Vec2 для распознавания речи
    asr_pipeline = pipeline("automatic-speech-recognition", model="facebook/wav2vec2-large-960h")
    with open(audio_path, "rb") as audio_file:
        transcript = asr_pipeline(audio_file.read())
    return transcript['text']


def write_srt(transcript, srt_path):
    import re
    import datetime

    def time_format(seconds):
        return str(datetime.timedelta(seconds=seconds))

    # Разделяем транскрипт на предложения
    sentences = re.split(r'(?<=[.!?]) +', transcript)
    with open(srt_path, 'w', encoding='utf-8') as srt_file:
        start_time = 0
        for i, sentence in enumerate(sentences, start=1):
            # Оцениваем длительность предложения
            duration = len(sentence) / 100 * 1.5  # Простая эвристика
            end_time = start_time + duration
            srt_file.write(f"{i}\n")
            srt_file.write(f"{time_format(start_time)} --> {time_format(end_time)}\n")
            srt_file.write(f"{sentence}\n\n")
            start_time = end_time


def main(video_path, output_audio_path, output_srt_path):
    # Шаг 1: Извлечение аудио из видео
    extract_audio_from_video(video_path, output_audio_path)

    # Шаг 2: Распознавание речи
    transcript = transcribe_audio(output_audio_path)

    # Шаг 3: Создание файла субтитров SRT
    write_srt(transcript, output_srt_path)


if __name__ == "__main__":
    video_path = "path_to_your_video.mp4"
    output_audio_path = "output_audio.wav"
    output_srt_path = "output_subtitles.srt"

    main(video_path, output_audio_path, output_srt_path)