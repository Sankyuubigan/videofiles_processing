@echo off
REM Dev build script for VideoFile Pro
REM ASCII only, CRLF line endings
REM Fast build without installer generation

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

REM Build frontend
echo Building frontend...
call npm run build
if %errorlevel% neq 0 (
    echo [ERROR] Frontend build failed
    pause >nul
    exit /b 1
)

REM Build Rust backend
echo Building Rust backend...
pushd src-tauri
cargo build
set RUST_RESULT=%errorlevel%
popd
if %RUST_RESULT% neq 0 (
    echo [ERROR] Rust build failed
    pause >nul
    exit /b 1
)

REM Copy NN models next to the executable
echo Copying NN models...
if not exist "src-tauri\target\debug\nn_models" mkdir "src-tauri\target\debug\nn_models"
copy /y "src-tauri\nn_models\content_classifier_b0.onnx" "src-tauri\target\debug\nn_models\content_classifier_b0.onnx" >nul

REM Launch application (start closes with console)
echo Launching application...
start "" "src-tauri\target\debug\videofile-pro.exe"
