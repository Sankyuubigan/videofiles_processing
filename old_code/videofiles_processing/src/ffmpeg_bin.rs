use std::path::{Path, PathBuf};
use std::fs;
use std::env;
use std::sync::OnceLock;

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
        // Проверяем наличие бинарников в папке приложения
        let exe_dir = env::current_exe()?.parent().unwrap().to_path_buf();
        
        let ffmpeg_path = exe_dir.join("ffmpeg.exe");
        let ffprobe_path = exe_dir.join("ffprobe.exe");
        
        // Если бинарники существуют в папке приложения, используем их
        if ffmpeg_path.exists() && ffprobe_path.exists() {
            return Ok(Self {
                ffmpeg_path,
                ffprobe_path,
            });
        }
        
        // Иначе проверяем в OUT_DIR (для разработки)
        if let Ok(out_dir) = env::var("OUT_DIR") {
            let ffmpeg_dir = PathBuf::from(out_dir).join("ffmpeg");
            if ffmpeg_dir.exists() {
                let ffmpeg_path = ffmpeg_dir.join("ffmpeg.exe");
                let ffprobe_path = ffmpeg_dir.join("ffprobe.exe");
                
                if ffmpeg_path.exists() && ffprobe_path.exists() {
                    return Ok(Self {
                        ffmpeg_path,
                        ffprobe_path,
                    });
                }
            }
        }
        
        // Если бинарники не найдены, скачиваем их
        let app_dir = dirs::data_dir()
            .unwrap_or_else(|| env::current_dir().unwrap())
            .join("video_compressor");
        
        fs::create_dir_all(&app_dir)?;
        
        let ffmpeg_path = app_dir.join("ffmpeg.exe");
        let ffprobe_path = app_dir.join("ffprobe.exe");
        
        // Если бинарники уже существуют, используем их
        if ffmpeg_path.exists() && ffprobe_path.exists() {
            return Ok(Self {
                ffmpeg_path,
                ffprobe_path,
            });
        }
        
        // Скачиваем и распаковываем FFmpeg
        Self::download_ffmpeg(&app_dir)?;
        
        Ok(Self {
            ffmpeg_path,
            ffprobe_path,
        })
    }

    fn download_ffmpeg(app_dir: &Path) -> Result<(), Box<dyn std::error::Error>> {
        println!("Downloading FFmpeg binaries...");
        
        // URL для последней версии FFmpeg для Windows
        let url = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip";
        
        // Временный файл для архива
        let zip_path = app_dir.join("ffmpeg.zip");
        
        // Скачиваем архив
        let response = reqwest::blocking::get(url)?;
        let bytes = response.bytes()?;
        fs::write(&zip_path, bytes)?;
        
        // Распаковываем архив
        let file = fs::File::open(&zip_path)?;
        let mut archive = zip::ZipArchive::new(file)?;
        
        // Ищем бинарники в архиве
        for i in 0..archive.len() {
            let mut file = archive.by_index(i)?;
            let file_path = file.enclosed_name().unwrap();
            
            if file_path.ends_with("bin/ffmpeg.exe") || file_path.ends_with("bin/ffprobe.exe") {
                let out_path = app_dir.join(file_path.file_name().unwrap());
                let mut outfile = fs::File::create(&out_path)?;
                std::io::copy(&mut file, &mut outfile)?;
            }
        }
        
        // Удаляем временный файл
        fs::remove_file(zip_path)?;
        
        println!("FFmpeg binaries downloaded successfully");
        Ok(())
    }
}

pub fn get_ffmpeg_path() -> &'static PathBuf {
    &FFmpegPaths::get().ffmpeg_path
}

pub fn get_ffprobe_path() -> &'static PathBuf {
    &FFmpegPaths::get().ffprobe_path
}

pub fn is_ffmpeg_available() -> bool {
    let paths = FFmpegPaths::get();
    paths.ffmpeg_path.exists() && paths.ffprobe_path.exists()
}