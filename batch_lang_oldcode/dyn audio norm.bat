set /p "file_name=Enter ID: "
set normalized=%file_name:.mp4=%_dan.mp4
REM ffmpeg -i %file_name% -af "dynaudnorm=p=0.71:m=100:s=12:g=15" -vcodec copy %normalized%
ffmpeg -i %file_name% -af "dynaudnorm=f=150:m=100:s=12:g=15" -vcodec copy %normalized%
pause