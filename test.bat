@echo off
REM Test script for VideoFile Pro
REM ASCII only, CRLF line endings
REM Initializes MSVC environment and runs cargo test (no GUI launch)

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

echo Running cargo test...
pushd src-tauri
cargo test
set TEST_RESULT=%errorlevel%
popd
if %TEST_RESULT% neq 0 (
    echo [ERROR] Tests failed
    pause >nul
    exit /b 1
)

echo [OK] All tests passed
exit /b 0
