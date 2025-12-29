@echo off
setlocal enabledelayedexpansion

REM Проверяем наличие ffmpeg
ffmpeg -version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo FFmpeg не установлен или не в PATH.
    echo Пожалуйста, установите FFmpeg и добавьте его в PATH.
    pause
    exit /b 1
)

REM Проверяем, передан ли путь к файлу
if "%~1"=="" (
    echo Использование: %~nx0 "путь\к\видео\файлу"
    echo Пример: %~nx0 "C:\Videos\myvideo.mp4"
    pause
    exit /b 1
)

REM Проверяем существование входного файла
if not exist "%~1" (
    echo Ошибка: Входной файл не существует.
    echo Файл: "%~1"
    pause
    exit /b 1
)

REM Получаем информацию о файле
set "input_file=%~1"
set "input_dir=%~dp1"
set "input_filename=%~n1"

REM Создаем имя выходного файла
set "output_file=%input_dir%%input_filename%_compressed.mp4"

REM Выводим информацию
echo ========================================
echo CompressO-style Video Compression
echo ========================================
echo Входной файл: %input_file%
echo Выходной файл: %output_file%
echo.
echo Будет выполнена компрессия видео с максимальным качеством
echo с сохранением всех аудиодорожек и конвертацией в MP4.
echo Субтитры будут конвертированы в совместимый формат.
echo ========================================
echo.

REM Запускаем ffmpeg с правильным маппингом потоков
ffmpeg -i "%input_file%" -c:v libx264 -preset veryslow -crf 24 -vf "pad=ceil(iw/2)*2:ceil(ih/2)*2" -c:a aac -b:a 320k -c:s mov_text -map 0:V -map 0:a -map 0:s "%output_file%"

REM Проверяем успешность
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Ошибка: Компрессия не удалась.
    echo Пробуем альтернативный метод без субтитров...
    echo.
    
    REM Пробуем без субтитров
    ffmpeg -i "%input_file%" -c:v libx264 -preset veryslow -crf 24 -vf "pad=ceil(iw/2)*2:ceil(ih/2)*2" -c:a aac -b:a 320k -map 0:V -map 0:a "%output_file%"
    
    if %ERRORLEVEL% NEQ 0 (
        echo.
        echo Ошибка: Компрессия снова не удалась.
        echo Пробуем последний метод...
        echo.
        
        REM Пробуем с другим подходом
        ffmpeg -i "%input_file%" -c:v libx264 -preset veryslow -crf 24 -vf "pad=ceil(iw/2)*2:ceil(ih/2)*2" -c:a aac -b:a 320k -map 0 -map -0:d "%output_file%"
        
        if %ERRORLEVEL% NEQ 0 (
            echo.
            echo Ошибка: Все методы компрессии не сработали.
            echo Проверьте сообщения об ошибках выше.
            pause
            exit /b 1
        )
    )
)

echo.
echo ========================================
echo Компрессия успешно завершена!
echo Файл сохранен в: %output_file%
echo ========================================
pause