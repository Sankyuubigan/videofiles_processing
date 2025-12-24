set /p "file_name1=Enter 1: "
set /p "file_name2=Enter 2: "
ffmpeg -i %file_name1% -i %file_name2% -filter_complex amerge=inputs=2 -ac 2 output_merged.mp3


