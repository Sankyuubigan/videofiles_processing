set /p "file_name=Enter ID: "
set normalized=%file_name:.mp4=%_changed.mp4
ffmpeg -i %file_name% -af asetrate=44100*0.9,aresample=44100,atempo=1/0.9 %normalized%
pause