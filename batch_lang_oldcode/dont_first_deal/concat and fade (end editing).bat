@echo off

@REM данный файл делает бутерброд с затемнением . итоговое редактирование файла перед заливкой на ютуб

set /p "file_name=drag and swap file: "
set intro="disclaimer.mp4"
set outro="outro.mp4"
set file_name_faded=%file_name:.=_faded.%
set len=2

ffprobe -v error -select_streams v:0 -show_entries stream=duration -of default=nw=1:nk=1 %file_name% > tmp.txt
set /p duration=<tmp.txt
set /a d=duration-len
 
ffmpeg -hide_banner -v error -stats -i %file_name% -vf fade=in:d=%len%,fade=out:st=%d%:d=%len% %file_name_faded%

rem -af "afade=in:d=%len%,afade=out:st=%d%:d=%len%"

ffmpeg -i %intro% -i %file_name_faded% -i %outro% -filter_complex "[0:v][0:a][1:v][1:a][2:v][2:a] concat=n=3:v=1:a=1 [outv] [outa]" -map "[outv]" -map "[outa]" %file_name:.mp4=_res.mp4%

del %file_name_faded%

pause