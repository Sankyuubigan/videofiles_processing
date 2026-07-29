use std::path::Path;
use std::sync::Arc;
use std::sync::atomic::AtomicBool;
use log::{error, warn};

use crate::ffmpeg::edit::normalize_audio_volume as normalize_core;

pub fn normalize_audio(
    input_path: &str,
    cancel_flag: Arc<AtomicBool>,
    progress_cb: Option<Arc<dyn Fn(i32, String) + Send + Sync>>,
    output_dir: Option<&str>,
) -> Result<String, String> {
    let input_p = Path::new(input_path);
    let stem = input_p.file_stem().map(|s| s.to_string_lossy().to_string()).unwrap_or_default();
    let ext = input_p.extension().map(|s| format!(".{}", s.to_string_lossy())).unwrap_or_default();
    let output_path = if let Some(dir) = output_dir {
        Path::new(dir).join(format!("{}_volnorm{}", stem, ext))
    } else {
        input_p.parent().unwrap_or(Path::new(".")).join(format!("{}_volnorm{}", stem, ext))
    };
    let output_str = output_path.to_string_lossy().to_string();
    if output_path.exists() {
        if let Err(e) = std::fs::remove_file(&output_path) {
            warn!("Failed to remove existing output {:?}: {}", output_path, e);
        }
    }

    let result = normalize_core(input_path, &output_str, cancel_flag, progress_cb);
    if !result.success {
        error!("Normalize error for {}: {}", input_path, result.message);
        return Err(format!("Normalize error: {}", result.message));
    }
    Ok(output_str)
}
