@echo off
REM Build check script for VideoFile Pro (no GUI launch)
REM ASCII only, CRLF line endings
REM Same MSVC init as build.bat, but does NOT start the app, so it can be
REM run from automation/CI and returns a non-zero exit code on failure.

REM Initialize MSVC environment
echo Initializing MSVC environment...
call "D:\Programs\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvarsall.bat" x64
if %errorlevel% neq 0 (
    echo [ERROR] Failed to initialize MSVC environment
    echo Check path: D:\Programs\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvarsall.bat
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
        exit /b 1
    )
)

REM Build frontend
echo Building frontend...
call npm run build
if %errorlevel% neq 0 (
    echo [ERROR] Frontend build failed
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
    exit /b 1
)

echo [OK] Build finished
exit /b 0
