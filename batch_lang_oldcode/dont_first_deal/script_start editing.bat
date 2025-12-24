@echo off

set /p "file_name=Enter ID: "

REM ffmpeg -hide_banner -i %file_name% -filter:a volumedetect -f null /dev/null
REM set name=%file_name:~0,-4% 
REM ffmpeg-normalize %file_name% -c:a aac -b:a 192k -o %new_file%
REM asetrate=43200,atempo=1.00,aresample=43200,

set deno=%file_name:.=_deno.%
ffmpeg -i %file_name% -af "arnndn=m='rnnoise-models/beguiling-drafter-2018-08-30/bd.rnnn'" %deno%

REM убираем тишину
set ws=%file_name:.mp4=_ws.mp4%
auto-editor %deno% --no-open --edit audio:threshold=0.005 -o %ws%
rem auto-editor %file_name% --no-open --edit "(or audio:0.04 motion:0)" -o %ws%
REM -c:v hevc -b:v auto --no-open -o %ws%
rem --edit_based_on not_motion 

REM выравниваем все голоса и звуки на один уровень громкости
set dynaudnorm=%file_name:.mp4=_dynaudnorm.mp4%
ffmpeg -hide_banner -i %ws% -af "dynaudnorm=f=150:m=100:s=12:g=15" -vcodec copy %dynaudnorm%

REM устанавливаем стандарт громкости звука
ffmpeg -hide_banner -i %dynaudnorm% -af loudnorm=I=-16:LRA=11:TP=-1.5 %file_name:.mp4=_trimmed.mp4%

REM ffmpeg -hide_banner -i %loudnorm% -filter:a volumedetect -f null /dev/null




if %ERRORLEVEL% neq 0 (
	ECHO Errors ! 
)
if %ERRORLEVEL% == 0 (
  del %dynaudnorm%
  del %ws% 
  del %deno%
  pause
  goto :eof
)

pause

REM обновить программу "pip install auto-editor --upgrade"
