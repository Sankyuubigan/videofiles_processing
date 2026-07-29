use std::io::Write;
use std::path::Path;
use log::warn;

pub const FFMPEG_URL: &str = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip";
pub const MEDIAINFO_URL: &str = "https://mediaarea.net/download/binary/mediainfo/26.05/MediaInfo_CLI_26.05_Windows_x64.zip";

pub async fn download_ffmpeg<F: Fn(String)>(progress_cb: F) -> Result<(), String> {
    progress_cb("Downloading FFmpeg...".to_string());
    let client = reqwest::Client::new();
    let response = client.get(FFMPEG_URL)
        .send()
        .await
        .map_err(|e| format!("Failed to start download: {}", e))?;

    let total_size = response.content_length().unwrap_or(0);
    let mut stream = response.bytes_stream();
    let mut downloaded: u64 = 0;

    let tmp_dir = std::env::temp_dir();
    let zip_path = tmp_dir.join("ffmpeg_download.zip");
    let mut file = std::fs::File::create(&zip_path)
        .map_err(|e| format!("Failed to create temp file: {}", e))?;

    use futures_util::StreamExt;
    while let Some(chunk) = stream.next().await {
        let chunk = chunk.map_err(|e| format!("Download error: {}", e))?;
        file.write_all(&chunk).map_err(|e| format!("Write error: {}", e))?;
        downloaded += chunk.len() as u64;
        if total_size > 0 {
            let pct = ((downloaded as f64 / total_size as f64) * 100.0) as i32;
            progress_cb(format!("Downloading FFmpeg: {}%", pct));
        }
    }
    if let Err(e) = file.flush() {
        warn!("Failed to flush ffmpeg download: {}", e);
    }

    progress_cb("Extracting FFmpeg...".to_string());
    let exe_dir = match std::env::current_exe() {
        Ok(p) => p.parent().map(|p| p.to_path_buf()),
        Err(e) => {
            warn!("current_exe() failed in download_ffmpeg: {}", e);
            None
        }
    }
    .unwrap_or_else(|| std::env::current_dir().unwrap_or_default());

    let zip_file = std::fs::File::open(&zip_path)
        .map_err(|e| format!("Failed to open zip: {}", e))?;
    let mut archive = zip::ZipArchive::new(zip_file)
        .map_err(|e| format!("Failed to read zip: {}", e))?;

    for i in 0..archive.len() {
        let mut entry = archive.by_index(i)
            .map_err(|e| format!("Failed to read zip entry: {}", e))?;
        let name = entry.name().to_string();
        if name.ends_with("ffmpeg.exe") {
            let out_path = exe_dir.join("ffmpeg.exe");
            let mut out_file = std::fs::File::create(&out_path)
                .map_err(|e| format!("Failed to create ffmpeg.exe: {}", e))?;
            std::io::copy(&mut entry, &mut out_file)
                .map_err(|e| format!("Failed to extract ffmpeg.exe: {}", e))?;
        } else if name.ends_with("ffprobe.exe") {
            let out_path = exe_dir.join("ffprobe.exe");
            let mut out_file = std::fs::File::create(&out_path)
                .map_err(|e| format!("Failed to create ffprobe.exe: {}", e))?;
            std::io::copy(&mut entry, &mut out_file)
                .map_err(|e| format!("Failed to extract ffprobe.exe: {}", e))?;
        }
    }

    if let Err(e) = std::fs::remove_file(&zip_path) {
        warn!("Failed to remove ffmpeg zip: {}", e);
    }

    // Cleanup extracted directories
    if let Ok(entries) = std::fs::read_dir(&exe_dir) {
        for entry in entries {
            let entry = match entry {
                Ok(e) => e,
                Err(e) => {
                    warn!("Failed to read directory entry during cleanup: {}", e);
                    continue;
                }
            };
            let name = entry.file_name().to_string_lossy().to_lowercase();
            if entry.path().is_dir() && name.contains("ffmpeg") {
                if let Err(e) = std::fs::remove_dir_all(entry.path()) {
                    warn!("Failed to remove ffmpeg directory {:?}: {}", entry.path(), e);
                }
            }
        }
    }

    if Path::new(&exe_dir.join("ffmpeg.exe")).exists() && Path::new(&exe_dir.join("ffprobe.exe")).exists() {
        progress_cb("FFmpeg downloaded successfully".to_string());
        Ok(())
    } else {
        Err("FFmpeg files not found after extraction".to_string())
    }
}

pub async fn download_mediainfo<F: Fn(String)>(progress_cb: F) -> Result<(), String> {
    let exe_dir = match std::env::current_exe() {
        Ok(p) => p.parent().map(|p| p.to_path_buf()),
        Err(e) => {
            warn!("current_exe() failed in download_mediainfo: {}", e);
            None
        }
    }
    .unwrap_or_else(|| std::env::current_dir().unwrap_or_default());

    let mediainfo_path = exe_dir.join("mediainfo.exe");
    if mediainfo_path.exists() {
        progress_cb("MediaInfo already present".to_string());
        return Ok(());
    }

    progress_cb("Downloading MediaInfo...".to_string());
    let client = reqwest::Client::new();
    let response = client.get(MEDIAINFO_URL)
        .send()
        .await
        .map_err(|e| format!("Failed to start MediaInfo download: {}", e))?;

    let total_size = response.content_length().unwrap_or(0);
    let mut stream = response.bytes_stream();
    let mut downloaded: u64 = 0;

    let tmp_dir = std::env::temp_dir();
    let zip_path = tmp_dir.join("mediainfo_download.zip");
    let mut file = std::fs::File::create(&zip_path)
        .map_err(|e| format!("Failed to create temp file: {}", e))?;

    use futures_util::StreamExt;
    while let Some(chunk) = stream.next().await {
        let chunk = chunk.map_err(|e| format!("Download error: {}", e))?;
        file.write_all(&chunk).map_err(|e| format!("Write error: {}", e))?;
        downloaded += chunk.len() as u64;
        if total_size > 0 {
            let pct = ((downloaded as f64 / total_size as f64) * 100.0) as i32;
            progress_cb(format!("Downloading MediaInfo: {}%", pct));
        }
    }
    if let Err(e) = file.flush() {
        warn!("Failed to flush mediainfo download: {}", e);
    }

    progress_cb("Extracting MediaInfo...".to_string());
    let zip_file = std::fs::File::open(&zip_path)
        .map_err(|e| format!("Failed to open zip: {}", e))?;
    let mut archive = zip::ZipArchive::new(zip_file)
        .map_err(|e| format!("Failed to read zip: {}", e))?;

    for i in 0..archive.len() {
        let mut entry = archive.by_index(i)
            .map_err(|e| format!("Failed to read zip entry: {}", e))?;
        let name = entry.name().to_string();
        if name.ends_with("MediaInfo.exe") || name.ends_with("mediainfo.exe") {
            let mut out_file = std::fs::File::create(&mediainfo_path)
                .map_err(|e| format!("Failed to create mediainfo.exe: {}", e))?;
            std::io::copy(&mut entry, &mut out_file)
                .map_err(|e| format!("Failed to extract mediainfo.exe: {}", e))?;
        }
    }

    if let Err(e) = std::fs::remove_file(&zip_path) {
        warn!("Failed to remove mediainfo zip: {}", e);
    }

    if mediainfo_path.exists() {
        progress_cb("MediaInfo downloaded successfully".to_string());
        Ok(())
    } else {
        Err("mediainfo.exe not found after extraction".to_string())
    }
}
