use log::{info, error};
use crate::settings::{load_settings, save_settings, check_ffmpeg_exists, Settings};

#[tauri::command]
pub fn load_settings_cmd() -> Result<Settings, String> {
    let s = load_settings();
    info!("load_settings_cmd: {:?}", s);
    Ok(s)
}

#[tauri::command]
pub fn save_settings_cmd(settings: Settings) -> Result<(), String> {
    info!("save_settings_cmd: {:?}", settings);
    save_settings(&settings).map_err(|e| {
        error!("Failed to save settings: {}", e);
        e
    })
}

#[tauri::command]
pub fn check_ffmpeg_cmd() -> Result<bool, String> {
    let exists = check_ffmpeg_exists();
    info!("check_ffmpeg_cmd: {}", exists);
    Ok(exists)
}

#[tauri::command]
pub async fn download_ffmpeg_cmd() -> Result<(), String> {
    info!("download_ffmpeg_cmd: starting download");
    crate::ffmpeg::downloader::download_ffmpeg(|msg| {
        info!("{}", msg);
    }).await.map_err(|e| {
        error!("FFmpeg download failed: {}", e);
        e
    })
}

#[tauri::command]
pub async fn download_mediainfo_cmd() -> Result<(), String> {
    info!("download_mediainfo_cmd: starting download");
    crate::ffmpeg::downloader::download_mediainfo(|msg| {
        info!("{}", msg);
    }).await.map_err(|e| {
        error!("MediaInfo download failed: {}", e);
        e
    })
}
