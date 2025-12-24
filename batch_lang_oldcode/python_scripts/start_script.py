#!/usr/bin/env python

import sys
import subprocess
import os
from pathlib import Path

import ffmpeg

from utils import run_with_pb

# input_path = input("Введите файл:")
input_path = sys.argv[1]
# out_path = sys.argv[1]
filename, file_extension = os.path.splitext(input_path)
out_path = filename + '_trimmed' + file_extension

ffin = ffmpeg.input(input_path)
# stream=ffmpeg.filter(stream, 'a',)
audio = ffin.audio.filter("arnndn", m='rnnoise-models/beguiling-drafter-2018-08-30/bd.rnnn')
video = ffin.video

ffout = ffmpeg.output(audio, video, out_path)

run_with_pb(input_path, ffout)

input('Press ENTER to exit')
