set /p "file_name=Enter ID: "

ffmpeg -y -i %file_name% -filter_complex "[0:v]pad=iw:ih*2:0:0,crop=iw/2:ih:0:0[leftside];[0:v]scale=iw:-1,crop=iw/2:ih:iw/2:0[rightside];[leftside][rightside]overlay=0:1080" %file_name:.mp4=%_vertical.mp4

pause