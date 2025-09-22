use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::OnceLock;
use std::env;

static FFMPEG_PATHS: OnceLock<FFmpegPaths> = OnceLock::new();

pub struct FFmpegPaths {
    pub ffmpeg_path: PathBuf,
    pub ffprobe_path: PathBuf,
}

impl FFmpegPaths {
    pub fn get() -> &'static Self {
        FFMPEG_PATHS.get_or_init(|| {
            Self::initialize().expect("Failed to initialize FFmpeg paths")
        })
    }

    fn initialize() -> Result<Self, Box<dyn std::error::Error>> {
        // Сначала проверяем OUT_DIR (для сборки)
        if let Ok(out_dir) = env::var("OUT_DIR") {
            let ffmpeg_dir = PathBuf::from(out_dir).join("ffmpeg");
            if ffmpeg_dir.exists() {
                return Ok(Self {
                    ffmpeg_path: ffmpeg_dir.join("ffmpeg.exe"),
                    ffprobe_path: ffmpeg_dir.join("ffprobe.exe"),
                });
            }
        }

        // Затем проверяем локальную папку
        let local_dir = PathBuf::from("ffmpeg");
        if local_dir.exists() {
            return Ok(Self {
                ffmpeg_path: local_dir.join("ffmpeg.exe"),
                ffprobe_path: local_dir.join("ffprobe.exe"),
            });
        }

        // Наконец, проверяем системный PATH
        if let Ok(ffmpeg_path) = which::which("ffmpeg") {
            let ffprobe_path = ffmpeg_path.parent().unwrap().join("ffprobe.exe");
            if ffprobe_path.exists() {
                return Ok(Self {
                    ffmpeg_path,
                    ffprobe_path,
                });
            }
        }

        Err("FFmpeg not found".into())
    }
}

pub fn get_ffmpeg_path() -> &'static PathBuf {
    &FFmpegPaths::get().ffmpeg_path
}

pub fn get_ffprobe_path() -> &'static PathBuf {
    &FFmpegPaths::get().ffprobe_path
}

pub fn is_ffmpeg_available() -> bool {
    FFmpegPaths::get().ffmpeg_path.exists() && FFmpegPaths::get().ffprobe_path.exists()
}