set /p "file_name=Enter ID: "
@REM ffmpeg -hide_banner -i %file_name% -filter:a volumedetect -f null /dev/null
set normalized=%file_name:.mp3=%_n.mp3
ffmpeg -i %file_name% -af loudnorm=I=-16:LRA=11:TP=-1.5 %normalized%
@REM ffmpeg -hide_banner -i %normalized% -filter:a volumedetect -f null /dev/null
pause