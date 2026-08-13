use std::path::Path;
use std::sync::Arc;
use std::sync::atomic::AtomicBool;
use log::{error, warn};

use crate::ffmpeg::encode::fix_vfr_only_core;
use crate::video_processor::compress::get_full_video_info;

pub fn fix_vfr_only(
    input_path: &str,
    cancel_flag: Arc<AtomicBool>,
    progress_cb: Option<Arc<dyn Fn(i32, String) + Send + Sync>>,
    output_dir: Option<&str>,
) -> Result<String, String> {
    let input_p = Path::new(input_path);
    let video_info = get_full_video_info(input_path).map_err(|e| {
        error!("Failed to get video info for {}: {}", input_path, e);
        e
    })?;
    if !video_info.needs_vfr_fix {
        warn!("VFR fix skipped for {}: video is already CFR", input_path);
        return Err("VFR fix not needed: video is already CFR".to_string());
    }
    if video_info.duration <= 0.0 {
        error!("Invalid video duration for {}: {}", input_path, video_info.duration);
        return Err("Invalid video duration".to_string());
    }

    let stem = input_p.file_stem().map(|s| s.to_string_lossy().to_string()).unwrap_or_default();
    let ext = input_p.extension().map(|s| format!(".{}", s.to_string_lossy())).unwrap_or_default();
    let output_path = if let Some(dir) = output_dir {
        Path::new(dir).join(format!("{}_vfrfixed{}", stem, ext))
    } else {
        input_p.parent().unwrap_or(Path::new(".")).join(format!("{}_vfrfixed{}", stem, ext))
    };
    let output_str = output_path.to_string_lossy().to_string();
    if output_path.exists() {
        if let Err(e) = std::fs::remove_file(&output_path) {
            warn!("Failed to remove existing output {:?}: {}", output_path, e);
        }
    }

    let result = fix_vfr_only_core(input_path, &output_str, video_info.duration, &video_info, cancel_flag, progress_cb, None);
    if !result.success {
        error!("VFR fix error for {}: {}", input_path, result.message);
        return Err(format!("VFR fix error: {}", result.message));
    }
    Ok(output_str)
}
