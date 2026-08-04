@echo off
REM Installer build script for VideoFile Pro
REM ASCII only, CRLF line endings
REM Full release build with .exe installer

REM Kill existing process if running
taskkill /f /im videofile-pro.exe 2>nul

REM Initialize MSVC environment
echo Initializing MSVC environment...
call "D:\Programs\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvarsall.bat" x64
if %errorlevel% neq 0 (
    echo [ERROR] Failed to initialize MSVC environment
    echo Check path: D:\Programs\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvarsall.bat
    pause >nul
    exit /b 1
)

REM Reset environment variables for clean build
set CC=
set CXX=
set CMAKE_C_COMPILER_LAUNCHER=
set RUSTC_WRAPPER=
set CARGO_BUILD_RUSTC_WRAPPER=

REM Sync version (YY.M.P) across tauri.conf.json, Cargo.toml, package.json
echo Syncing version (YY.M.P)...
set "APP_VERSION="
for /f "usebackq delims=" %%V in (`powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\sync_version.ps1"`) do set "APP_VERSION=%%V"
if not defined APP_VERSION (
    echo [ERROR] Version sync failed
    pause >nul
    exit /b 1
)
echo Version: %APP_VERSION%

REM Install npm dependencies if needed
if not exist "node_modules" (
    echo Installing npm dependencies...
    call npm install
    if %errorlevel% neq 0 (
        echo [ERROR] npm install failed
        pause >nul
        exit /b 1
    )
)

REM Run Tauri build (release build with installer)
echo Building installer...
call npx tauri build

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Build failed with exit code %errorlevel%
    pause >nul
    exit /b 1
)

echo.
echo Build completed successfully!
echo Installer located in: src-tauri\target\release\bundle\nsis\
pause >nul
