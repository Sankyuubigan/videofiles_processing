set /p "file_name=Enter ID: "

ffmpeg -hide_banner -i %file_name% -filter:a volumedetect -f null /dev/null

set normalized=%file_name:.mp4=%_n.mp4

ffmpeg -i %file_name% -af loudnorm=I=-16:LRA=11:TP=-1.5 %normalized%

ffmpeg -hide_banner -i %normalized% -filter:a volumedetect -f null /dev/null

pause
