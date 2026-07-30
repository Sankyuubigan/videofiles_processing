use serde::{Deserialize, Serialize};
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::OnceLock;
use log::{info, warn};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Settings {
    pub ffmpeg_path: String,
    pub vmaf_subsample: usize,
    pub chunk_count: usize,
    pub chunk_duration: usize,
    #[serde(default = "default_locale")]
    pub locale: String,
    #[serde(default = "default_true")]
    pub skip_min_diff_enabled: bool,
    #[serde(default = "default_min_diff")]
    pub skip_min_diff_percent: f64,
    #[serde(default = "default_true")]
    pub skip_min_crf_enabled: bool,
    #[serde(default = "default_min_crf")]
    pub skip_min_crf_value: f64,
}

fn default_locale() -> String {
    "en".to_string()
}

fn default_true() -> bool {
    true
}

fn default_min_diff() -> f64 {
    5.0
}

fn default_min_crf() -> f64 {
    18.0
}

impl Default for Settings {
    fn default() -> Self {
        Self {
            ffmpeg_path: "./".to_string(),
            vmaf_subsample: 10,
            chunk_count: 5,
            chunk_duration: 2,
            locale: "en".to_string(),
            skip_min_diff_enabled: true,
            skip_min_diff_percent: 5.0,
            skip_min_crf_enabled: true,
            skip_min_crf_value: 18.0,
        }
    }
}

static SETTINGS_CACHE: OnceLock<Settings> = OnceLock::new();

fn settings_file_path() -> PathBuf {
    let exe_dir = match std::env::current_exe() {
        Ok(p) => p.parent().map(|p| p.to_path_buf()),
        Err(e) => {
            warn!("current_exe() failed, falling back to cwd: {}", e);
            None
        }
    }
    .unwrap_or_else(|| std::env::current_dir().unwrap_or_default());
    exe_dir.join("settings.json")
}

pub fn load_settings() -> Settings {
    if let Some(cached) = SETTINGS_CACHE.get() {
        return cached.clone();
    }
    let path = settings_file_path();
    info!("Loading settings from: {:?}", path);
    let settings = if path.exists() {
        let content = match fs::read_to_string(&path) {
            Ok(c) => c,
            Err(e) => {
                warn!("Failed to read settings file {:?}: {}", path, e);
                return Settings::default();
            }
        };
        match serde_json::from_str::<Settings>(&content) {
            Ok(s) => s,
            Err(e) => {
                warn!("Failed to parse settings file {:?}: {}", path, e);
                Settings::default()
            }
        }
    } else {
        Settings::default()
    };
    info!("Loaded settings: {:?}", settings);
    let _ = SETTINGS_CACHE.set(settings.clone());
    settings
}

pub fn save_settings(settings: &Settings) -> Result<(), String> {
    let path = settings_file_path();
    info!("Saving settings to {:?}: {:?}", path, settings);
    let json = serde_json::to_string_pretty(settings).map_err(|e| e.to_string())?;
    fs::write(&path, json).map_err(|e| e.to_string())?;
    Ok(())
}

pub fn get_actual_ffmpeg_path() -> String {
    let ext = if cfg!(target_os = "windows") { ".exe" } else { "" };
    let filename = format!("ffmpeg{}", ext);
    resolve_ffmpeg_binary(&filename)
}

pub fn get_ffprobe_path() -> String {
    let ext = if cfg!(target_os = "windows") { ".exe" } else { "" };
    let filename = format!("ffprobe{}", ext);
    resolve_ffmpeg_binary(&filename)
}

pub fn get_mediainfo_path() -> String {
    let ext = if cfg!(target_os = "windows") { ".exe" } else { "" };
    let filename = format!("mediainfo{}", ext);
    resolve_mediainfo_binary(&filename)
}

fn resolve_mediainfo_binary(filename: &str) -> String {
    let settings = load_settings();

    if settings.ffmpeg_path != "./" && settings.ffmpeg_path != "." {
        let custom = PathBuf::from(&settings.ffmpeg_path).join(filename);
        if custom.exists() {
            return custom.to_string_lossy().to_string();
        }
    }

    if let Some(exe_dir) = match std::env::current_exe() {
        Ok(p) => p.parent().map(|p| p.to_path_buf()),
        Err(e) => {
            warn!("current_exe() failed in resolve_mediainfo_binary: {}", e);
            None
        }
    }
    {
        let path = exe_dir.join(filename);
        if path.exists() {
            return path.to_string_lossy().to_string();
        }
        let sibling = exe_dir.join("ffmpeg").join(filename);
        if sibling.exists() {
            return sibling.to_string_lossy().to_string();
        }
    }

    if let Ok(cwd) = std::env::current_dir() {
        let path = cwd.join("ffmpeg").join(filename);
        if path.exists() {
            return path.to_string_lossy().to_string();
        }
        let path = cwd.join(filename);
        if path.exists() {
            return path.to_string_lossy().to_string();
        }
    }

    let fallback = match std::env::current_exe() {
        Ok(p) => p.parent().map(|p| p.to_path_buf()),
        Err(e) => {
            warn!("current_exe() fallback failed in resolve_mediainfo_binary: {}", e);
            None
        }
    }
    .unwrap_or_else(|| std::env::current_dir().unwrap_or_default());
    fallback.join(filename).to_string_lossy().to_string()
}

fn resolve_ffmpeg_binary(filename: &str) -> String {
    let settings = load_settings();

    if settings.ffmpeg_path != "./" && settings.ffmpeg_path != "." {
        let custom = PathBuf::from(&settings.ffmpeg_path).join(filename);
        if custom.exists() {
            return custom.to_string_lossy().to_string();
        }
    }

    if let Some(exe_dir) = match std::env::current_exe() {
        Ok(p) => p.parent().map(|p| p.to_path_buf()),
        Err(e) => {
            warn!("current_exe() failed in resolve_ffmpeg_binary: {}", e);
            None
        }
    }
    {
        let path = exe_dir.join(filename);
        if path.exists() {
            return path.to_string_lossy().to_string();
        }
        let sibling = exe_dir.join("ffmpeg").join(filename);
        if sibling.exists() {
            return sibling.to_string_lossy().to_string();
        }
    }

    if let Ok(cwd) = std::env::current_dir() {
        let path = cwd.join("ffmpeg").join(filename);
        if path.exists() {
            return path.to_string_lossy().to_string();
        }
        let path = cwd.join(filename);
        if path.exists() {
            return path.to_string_lossy().to_string();
        }
    }

    let fallback = match std::env::current_exe() {
        Ok(p) => p.parent().map(|p| p.to_path_buf()),
        Err(e) => {
            warn!("current_exe() fallback failed in resolve_ffmpeg_binary: {}", e);
            None
        }
    }
    .unwrap_or_else(|| std::env::current_dir().unwrap_or_default());
    fallback.join(filename).to_string_lossy().to_string()
}

pub fn check_ffmpeg_exists() -> bool {
    let ffmpeg = get_actual_ffmpeg_path();
    let ffprobe = get_ffprobe_path();
    Path::new(&ffmpeg).exists() && Path::new(&ffprobe).exists()
}
