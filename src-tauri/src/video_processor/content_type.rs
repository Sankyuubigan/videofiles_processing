use std::collections::HashMap;
use std::path::Path;
use std::process::Command;
use std::sync::Mutex;
use log::{info, warn};

use crate::ffmpeg::probe::VideoType;
use crate::nn_quality::content_type::{classify_frames, RgbFrame};

const FRAME_COUNT: usize = 10;

/// User overrides for content type, persisted next to settings.json:
/// path -> "Animation" | "LiveAction". Applied before NN detection so manual
/// corrections survive re-detection during compression.
static OVERRIDE_CACHE: Mutex<Option<HashMap<String, VideoType>>> = Mutex::new(None);

pub fn detect_content_type(input_path: &str, duration: f64) -> VideoType {
    info!("Content type detection: classifying {} frames from {}", FRAME_COUNT, input_path);

    if let Some(overridden) = get_override(input_path) {
        info!("Content type override found for {}: {:?}", input_path, overridden);
        return overridden;
    }

    let timestamps = generate_timestamps(duration);
    let path = input_path.to_string();

    let handles: Vec<_> = timestamps.into_iter().map(|ts| {
        let p = path.clone();
        std::thread::spawn(move || extract_frame(&p, ts).ok())
    }).collect();

    let mut frames = Vec::new();
    for h in handles {
        if let Ok(Some(frame)) = h.join() {
            frames.push(frame);
        }
    }

    if frames.is_empty() {
        warn!("Content type: no frames extracted, defaulting to LiveAction");
        return VideoType::LiveAction;
    }

    match classify_frames(&frames) {
        Ok(vt) => {
            info!("Content type result: {:?}", vt);
            vt
        }
        Err(e) => {
            warn!("Content type: NN classification failed ({}), defaulting to LiveAction", e);
            VideoType::LiveAction
        }
    }
}

/// Persist a manual content type override for a file path.
pub fn set_override(input_path: &str, video_type: &VideoType) -> Result<(), String> {
    let mut overrides = load_overrides();
    let canonical = canonicalize(input_path);
    overrides.insert(canonical.clone(), video_type.clone());
    save_overrides(&overrides)?;
    info!("Content type override saved for {}: {:?}", canonical, video_type);
    Ok(())
}

/// Remove a manual content type override for a file path.
pub fn clear_override(input_path: &str) -> Result<(), String> {
    let mut overrides = load_overrides();
    let canonical = canonicalize(input_path);
    if overrides.remove(&canonical).is_some() {
        save_overrides(&overrides)?;
        info!("Content type override cleared for {}", canonical);
    }
    Ok(())
}

fn get_override(input_path: &str) -> Option<VideoType> {
    let canonical = canonicalize(input_path);
    load_overrides().get(&canonical).cloned()
}

fn canonicalize(input_path: &str) -> String {
    match Path::new(input_path).canonicalize() {
        Ok(p) => p.to_string_lossy().to_string(),
        Err(_) => input_path.to_string(),
    }
}

fn overrides_file_path() -> std::path::PathBuf {
    let exe_dir = match std::env::current_exe() {
        Ok(p) => p.parent().map(|p| p.to_path_buf()),
        Err(e) => {
            warn!("current_exe() failed, falling back to cwd: {}", e);
            None
        }
    }
    .unwrap_or_else(|| std::env::current_dir().unwrap_or_default());
    exe_dir.join("content_type_overrides.json")
}

fn load_overrides() -> HashMap<String, VideoType> {
    if let Ok(guard) = OVERRIDE_CACHE.lock() {
        if let Some(ref cached) = *guard {
            return cached.clone();
        }
    }
    let path = overrides_file_path();
    let overrides = if path.exists() {
        match std::fs::read_to_string(&path) {
            Ok(content) => match serde_json::from_str::<HashMap<String, VideoType>>(&content) {
                Ok(map) => map,
                Err(e) => {
                    warn!("Failed to parse overrides file {:?}: {}", path, e);
                    HashMap::new()
                }
            },
            Err(e) => {
                warn!("Failed to read overrides file {:?}: {}", path, e);
                HashMap::new()
            }
        }
    } else {
        HashMap::new()
    };
    if let Ok(mut guard) = OVERRIDE_CACHE.lock() {
        *guard = Some(overrides.clone());
    }
    overrides
}

fn save_overrides(overrides: &HashMap<String, VideoType>) -> Result<(), String> {
    let path = overrides_file_path();
    let json = serde_json::to_string_pretty(overrides).map_err(|e| e.to_string())?;
    std::fs::write(&path, json).map_err(|e| e.to_string())?;
    if let Ok(mut guard) = OVERRIDE_CACHE.lock() {
        *guard = Some(overrides.clone());
    }
    Ok(())
}

fn generate_timestamps(duration: f64) -> Vec<f64> {
    if duration <= 0.0 {
        return vec![0.0];
    }
    if duration < 5.0 {
        return vec![duration * 0.5];
    }

    let step = duration / (FRAME_COUNT as f64 + 1.0);
    (1..=FRAME_COUNT).map(|i| step * i as f64).collect()
}

/// Extract a single frame as raw RGB via ffmpeg PPM pipe.
/// Scaling matches the validated pipeline: width 320, bicubic.
fn extract_frame(input_path: &str, timestamp: f64) -> Result<RgbFrame, String> {
    let ffmpeg_path = crate::settings::get_actual_ffmpeg_path();
    let mut cmd = Command::new(&ffmpeg_path);
    cmd.args([
        "-y", "-ss", &format!("{:.3}", timestamp),
        "-i", input_path,
        "-vf", "scale=320:-1:flags=bicubic",
        "-frames:v", "1",
        "-f", "image2pipe", "-vcodec", "ppm", "-",
    ]);
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x08000000);
    }
    let output = cmd.output()
        .map_err(|e| format!("ffmpeg launch failed: {}", e))?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(format!("ffmpeg exited with {}: {}", output.status, stderr.lines().last().unwrap_or("unknown error")));
    }

    let img = image::load_from_memory(&output.stdout)
        .map_err(|e| format!("failed to decode PPM frame: {}", e))?;
    let rgb = img.to_rgb8();
    let (w, h) = rgb.dimensions();
    let data = rgb.into_raw();
    Ok(RgbFrame { width: w, height: h, data })
}
