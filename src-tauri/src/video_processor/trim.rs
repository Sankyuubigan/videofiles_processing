use std::path::Path;
use std::sync::Arc;
use std::sync::atomic::AtomicBool;
use log::{error, warn};

use crate::config::TRIMMED_VIDEO_SUFFIX;
use crate::ffmpeg::edit::trim_video_core;
use crate::video_processor::compress::get_full_video_info;

pub fn trim_video(
    input_path: &str, seconds: f64, from_start: bool,
    cancel_flag: Arc<AtomicBool>,
    progress_cb: Option<Arc<dyn Fn(i32, String) + Send + Sync>>,
    output_dir: Option<&str>,
) -> Result<String, String> {
    let input_p = Path::new(input_path);
    if let Some(ref cb) = progress_cb {
        cb(5, "Analyzing duration...".to_string());
    }

    let video_info = get_full_video_info(input_path).map_err(|e| {
        error!("Failed to get video info for {}: {}", input_path, e);
        e
    })?;
    let total_duration = video_info.duration;
    if total_duration <= 0.0 {
        error!("Could not determine video duration for {}", input_path);
        return Err("Could not determine video duration".to_string());
    }
    if seconds >= total_duration {
        error!("Seconds to remove ({}) >= video duration ({}) for {}", seconds, total_duration, input_path);
        return Err("Seconds to remove >= video duration".to_string());
    }

    let (start_time, new_duration) = if from_start {
        (seconds, total_duration - seconds)
    } else {
        (0.0, total_duration - seconds)
    };

    let stem = input_p.file_stem().map(|s| s.to_string_lossy().to_string()).unwrap_or_default();
    let ext = input_p.extension().map(|s| format!(".{}", s.to_string_lossy())).unwrap_or_default();
    let output_path = if let Some(dir) = output_dir {
        Path::new(dir).join(format!("{}{}{}", stem, TRIMMED_VIDEO_SUFFIX, ext))
    } else {
        input_p.parent().unwrap_or(Path::new(".")).join(format!("{}{}{}", stem, TRIMMED_VIDEO_SUFFIX, ext))
    };
    let output_str = output_path.to_string_lossy().to_string();
    if output_path.exists() {
        if let Err(e) = std::fs::remove_file(&output_path) {
            warn!("Failed to remove existing output {:?}: {}", output_path, e);
        }
    }

    let result = trim_video_core(input_path, &output_str, start_time, new_duration, cancel_flag, progress_cb);
    if !result.success {
        error!("Trim error for {}: {}", input_path, result.message);
        return Err(format!("Trim error: {}", result.message));
    }
    Ok(output_str)
}
