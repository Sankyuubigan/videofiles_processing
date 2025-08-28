use std::env;
use std::fs;
use std::path::PathBuf;
use std::process::Command;

fn main() {
    println!("cargo:rerun-if-changed=build.rs");

    let target_os = env::var("CARGO_CFG_TARGET_OS").unwrap();
    
    // Только для Windows
    if target_os != "windows" {
        return;
    }

    let out_dir = PathBuf::from(env::var("OUT_DIR").unwrap());
    let ffmpeg_dir = out_dir.join("ffmpeg");

    if !ffmpeg_dir.exists() {
        fs::create_dir_all(&ffmpeg_dir).unwrap();
        
        // Скачиваем FFmpeg для Windows
        println!("cargo:warning=Downloading FFmpeg binaries...");
        
        // Используем curl если доступен, иначе PowerShell
        let download_result = if Command::new("curl").output().is_ok() {
            Command::new("curl")
                .args(&[
                    "-L", "-o", ffmpeg_dir.join("ffmpeg.zip").to_str().unwrap(),
                    "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
                ])
                .output()
        } else {
            Command::new("powershell")
                .args(&[
                    "-Command",
                    &format!(
                        "Invoke-WebRequest -Uri 'https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip' -OutFile '{}'",
                        ffmpeg_dir.join("ffmpeg.zip").display()
                    )
                ])
                .output()
        };

        match download_result {
            Ok(output) => {
                if output.status.success() {
                    println!("cargo:warning=FFmpeg downloaded successfully");
                    
                    // Распаковываем архив
                    let extract_result = if Command::new("tar").output().is_ok() {
                        Command::new("tar")
                            .args(&[
                                "-xf", ffmpeg_dir.join("ffmpeg.zip").to_str().unwrap(),
                                "-C", ffmpeg_dir.to_str().unwrap()
                            ])
                            .output()
                    } else {
                        Command::new("powershell")
                            .args(&[
                                "-Command",
                                &format!(
                                    "Expand-Archive -Path '{}' -DestinationPath '{}' -Force",
                                    ffmpeg_dir.join("ffmpeg.zip").display(),
                                    ffmpeg_dir.display()
                                )
                            ])
                            .output()
                    };
                    
                    match extract_result {
                        Ok(_) => {
                            println!("cargo:warning=FFmpeg extracted successfully");
                            
                            // Находим папку с бинарниками
                            let mut bin_dir = None;
                            for entry in fs::read_dir(&ffmpeg_dir).unwrap() {
                                let entry = entry.unwrap();
                                if entry.file_type().unwrap().is_dir() {
                                    let path = entry.path();
                                    if path.join("bin").exists() {
                                        bin_dir = Some(path.join("bin"));
                                        break;
                                    }
                                }
                            }
                            
                            if let Some(bin_dir) = bin_dir {
                                // Копируем бинарники в корневую папку
                                fs::copy(bin_dir.join("ffmpeg.exe"), ffmpeg_dir.join("ffmpeg.exe")).unwrap();
                                fs::copy(bin_dir.join("ffprobe.exe"), ffmpeg_dir.join("ffprobe.exe")).unwrap();
                                
                                println!("cargo:warning=FFmpeg binaries ready");
                            } else {
                                println!("cargo:warning=Could not find ffmpeg bin directory");
                            }
                        }
                        Err(e) => {
                            println!("cargo:warning=Failed to extract FFmpeg: {:?}", e);
                        }
                    }
                } else {
                    println!("cargo:warning=Download command failed with status: {}", output.status);
                    println!("cargo:warning=Stdout: {}", String::from_utf8_lossy(&output.stdout));
                    println!("cargo:warning=Stderr: {}", String::from_utf8_lossy(&output.stderr));
                }
            }
            Err(e) => {
                println!("cargo:warning=Failed to download FFmpeg: {:?}", e);
            }
        }
    }

    // Копируем бинарники в целевую директорию
    let target_dir = PathBuf::from(env::var("OUT_DIR").unwrap())
        .parent().unwrap().parent().unwrap().parent().unwrap()
        .join("release");
    
    if target_dir.exists() {
        if ffmpeg_dir.join("ffmpeg.exe").exists() {
            fs::copy(ffmpeg_dir.join("ffmpeg.exe"), target_dir.join("ffmpeg.exe")).ok();
        }
        if ffmpeg_dir.join("ffprobe.exe").exists() {
            fs::copy(ffmpeg_dir.join("ffprobe.exe"), target_dir.join("ffprobe.exe")).ok();
        }
    }
}