@echo off
setlocal enabledelayedexpansion

REM Check if ffmpeg is installed
ffmpeg -version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo FFmpeg is not installed or not in PATH.
    echo Please install FFmpeg and add it to your PATH.
    pause
    exit /b 1
)

REM Check if a file path was provided
if "%~1"=="" (
    echo Usage: %~nx0 "path\to\video\file"
    echo Example: %~nx0 "C:\Users\Username\Videos\myvideo.mp4"
    pause
    exit /b 1
)

REM Check if the input file exists
if not exist "%~1" (
    echo Error: Input file does not exist.
    echo File: "%~1"
    pause
    exit /b 1
)

REM Get input file information
set "input_file=%~1"
set "input_dir=%~dp1"
set "input_filename=%~n1"

REM Create output filename with .mp4 extension
set "output_file=%input_dir%%input_filename%_compressed.mp4"

REM Display compression information
echo ========================================
echo CompressO-style Video Compression
echo ========================================
echo Input file: %input_file%
echo Output file: %output_file%
echo.
echo This will compress the video with maximum quality
echo while preserving all audio tracks and converting to MP4 format.
echo Subtitles will be converted to a compatible format.
echo ========================================
echo.

REM Run ffmpeg with maximum quality settings for MP4 output
ffmpeg -i "%input_file%" -c:v libx264 -preset veryslow -crf 24 -vf "pad=ceil(iw/2)*2:ceil(ih/2)*2" -c:a aac -b:a 320k -c:s mov_text -map 0 "%output_file%"

REM Check if compression was successful
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Error: Compression failed.
    echo Trying alternative method without subtitles...
    echo.
    
    REM Try again without subtitles
    ffmpeg -i "%input_file%" -c:v libx264 -preset veryslow -crf 24 -vf "pad=ceil(iw/2)*2:ceil(ih/2)*2" -c:a aac -b:a 320k -map 0:v -map 0:a "%output_file%"
    
    if %ERRORLEVEL% NEQ 0 (
        echo.
        echo Error: Compression failed again.
        echo Please check the error messages above.
        pause
        exit /b 1
    )
)

echo.
echo ========================================
echo Compression completed successfully!
echo Output saved to: %output_file%
echo ========================================
pause