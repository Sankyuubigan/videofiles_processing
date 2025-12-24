
set /p "file_name1=drag and swap file1: "
set /p "file_name2=drag and swap file2: "

ffmpeg -i %file_name1% -i %file_name2% -filter_complex "[0:v][0:a][1:v][1:a] concat=n=2:v=1:a=1 [outv] [outa]" -map "[outv]" -map "[outa]" %file_name2:.mp4=_res.mp4%




pause

rem concat: конкатенировать фильтр, соединяющий потоки
rem n: количество входных сегментов (= синхронизированные аудио-видео потоки, или только аудио, или только видео)
rem v: количество выходных видеопотоков
rem a: количество выходных аудиопотоков
rem -vn: отключить видео (-an отключит аудио)
rem -y: перезаписать выходные файлы без подсказок