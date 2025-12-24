#!/usr/bin/env python

# import os
# import ffmpeg
#
# from utils import run_with_pb, remove_silence
#
# # def progress_handler(progress_info):
# #     print('{:.2f}'.format(progress_info['percentage']))
# # Основной код
# # input_folder = 'E:\Записи видео\MarvelRivals\Highlights'  # Папка с исходными видео
# # final_output = "E:\Записи видео\MarvelRivals\Highlights\\final_output.mp4"  # Итоговый объединенный файл
# #
# # files_list = f"file 'F:\\music\\cbs50.mp4'\nfile 'F:\\music\\cbs51.mp4'\n"
#
# # input_path = input("Введите файл:")
# input_path = 'E:\\Записи видео\\MarvelRivals\\Highlights\\ЕНОТ РАКЕТА_2025-01-08_05-55-02.mp4'
# # out_path = sys.argv[1]
# filename, file_extension = os.path.splitext(input_path)
# out_path = filename + '_test223' + file_extension

from moviepy.editor import VideoFileClip, concatenate_videoclips
import os

# Путь к папке с видео
folder_path = "E:\Записи видео\MarvelRivals\Highlights\S0"
final_output = "final_output.mp4"

# Получаем список всех видеофайлов в папке
video_files = [f for f in os.listdir(folder_path) if f.endswith(('.mp4', '.avi', '.mov', '.mkv'))]

# Список для хранения обрезанных видео
clips = []

for video_file in video_files:
    # Полный путь к видеофайлу
    video_path = os.path.join(folder_path, video_file)

    # Загружаем видео
    clip = VideoFileClip(video_path)

    # Обрезаем последние 3 секунды
    if clip.duration > 3:
        clip = clip.subclip(0, clip.duration - 3)

    # Добавляем обрезанное видео в список
    clips.append(clip)

# Склеиваем все видео в одно
final_clip = concatenate_videoclips(clips)

# Сохраняем результат
final_clip.write_videofile(f"{folder_path}\\{final_output}", codec="libx264")

# Закрываем все клипы
final_clip.close()
for clip in clips:
    clip.close()