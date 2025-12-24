#!/usr/bin/env python

import os
import ffmpeg

from utils import run_with_pb, remove_silence

# def progress_handler(progress_info):
#     print('{:.2f}'.format(progress_info['percentage']))


# input_path = input("Введите файл:")
input_path = 'E:\Downloads\\test залить на ютуб\тест шум старое видео_denoised.mp4'
# out_path = sys.argv[1]
filename, file_extension = os.path.splitext(input_path)
out_path = filename + '_test223' + file_extension


# input = ffmpeg.input(input_path)
# # stream=ffmpeg.filter(stream, 'a',)
# audio = input.audio.filter("arnndn", m='rnnoise-models/beguiling-drafter-2018-08-30/bd.rnnn')
# video = input.video
#
# out = ffmpeg.output(audio, video, out_path)
#
#
#
# run_with_pb(input_path,out)

# remove_silence(input_path,out_path)



