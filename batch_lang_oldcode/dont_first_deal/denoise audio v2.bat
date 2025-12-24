@echo off

set /p "file_name=drag and swap file: "

ffmpeg -i %file_name% -af "highpass=f=200, lowpass=f=3000" %file_name:.=_deno2.% 

pause