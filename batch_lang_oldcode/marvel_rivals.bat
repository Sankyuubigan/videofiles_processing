set /p "file_name=Enter ID: "

set cutted=%file_name:.mp4=%_cutted.mp4

ffprobe -i %file_name% -show_entries format=duration -v quiet -of csv="p=0"

rem ffmpeg -i %file_name% -t $(( $(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 %cutted% |cut -d\. -f1) - 3 ))

rem ffmpeg -i %file_name% -t $(echo "$(ffprobe -i %file_name% -show_entries format=duration -v quiet -of csv='p=0') - 3" | bc) -c copy %cutted%

pause