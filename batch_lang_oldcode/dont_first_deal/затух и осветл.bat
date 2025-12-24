@echo off
setlocal EnableDelayedExpansion

:: 1. Получаем имя файла (работает и через drag-n-drop %1, и через ввод)
set "INPUT=%~1"
if "%INPUT%"=="" set /p "INPUT=Drag and drop file here: "

:: Убираем кавычки, если они есть, для корректной обработки
set "INPUT=%INPUT:"=%"

:: 2. Формируем имя выходного файла (имя + _fade + расширение)
:: %~n1 - имя без расширения, %~x1 - расширение
set "OUTPUT=%~dpn1_fade%~x1"

set LEN=2

:: 3. Получаем длительность.
:: Хитрость: мы используем 'for /f', чтобы разбить число 120.567 по точке (.)
:: и берем только первую часть (120), так как 'set /a' не понимает дроби.
for /f "tokens=1 delims=." %%a in ('ffprobe -v error -select_streams v:0 -show_entries stream^=duration -of default^=nw^=1:nk^=1 "%INPUT%"') do (
    set "DURATION_INT=%%a"
)

:: 4. Вычисляем момент начала затухания
set /a START_FADE=DURATION_INT-LEN

echo Input: "%INPUT%"
echo Duration (int): %DURATION_INT% sec
echo Fade starts at: %START_FADE% sec

:: 5. Запускаем FFmpeg
ffmpeg -hide_banner -v error -stats -i "%INPUT%" ^
  -vf "fade=in:d=%LEN%,fade=out:st=%START_FADE%:d=%LEN%" ^
  -af "afade=in:d=%LEN%,afade=out:st=%START_FADE%:d=%LEN%" ^
  "%OUTPUT%"

echo.
echo Done! Saved as "%OUTPUT%"
pause