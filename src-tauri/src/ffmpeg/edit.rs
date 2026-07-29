use std::sync::Arc;
use std::sync::atomic::AtomicBool;

use super::core::{run_command_with_progress, run_command_simple, RunResult};
use super::probe::get_video_info_raw;

pub fn trim_video_core(
    input_path: &str, output_path: &str, start_time: f64, duration: f64,
    cancel_flag: Arc<AtomicBool>,
    progress_cb: Option<Arc<dyn Fn(i32, String) + Send + Sync>>,
) -> RunResult {
    let cmd = vec![
        "ffmpeg".to_string(), "-y".to_string(),
        "-ss".to_string(), start_time.to_string(),
        "-i".to_string(), input_path.to_string(),
        "-t".to_string(), duration.to_string(),
        "-c:v".to_string(), "libx264".to_string(),
        "-crf".to_string(), "23".to_string(),
        "-preset".to_string(), "medium".to_string(),
        "-c:a".to_string(), "aac".to_string(),
        "-b:a".to_string(), "192k".to_string(),
        "-progress".to_string(), "pipe:1".to_string(),
        output_path.to_string(),
    ];
    run_command_with_progress(&cmd, Some(duration), "Trim", cancel_flag, progress_cb)
}

pub fn normalize_audio_volume(
    input_path: &str, output_path: &str,
    cancel_flag: Arc<AtomicBool>,
    progress_cb: Option<Arc<dyn Fn(i32, String) + Send + Sync>>,
) -> RunResult {
    let info = match get_video_info_raw(input_path) {
        Ok(info) => Some(info),
        Err(e) => {
            log::warn!("Failed to get video info for normalize: {}: {}", input_path, e);
            None
        }
    };
    let duration = info.map(|i| i.duration).unwrap_or(0.0);
    let cmd = vec![
        "ffmpeg".to_string(), "-y".to_string(),
        "-i".to_string(), input_path.to_string(),
        "-af".to_string(), "dynaudnorm=f=150:m=100:s=12:g=15,loudnorm=I=-16:LRA=11:TP=-1.5".to_string(),
        "-c:v".to_string(), "copy".to_string(),
        "-progress".to_string(), "pipe:1".to_string(),
        output_path.to_string(),
    ];
    run_command_with_progress(&cmd, Some(duration), "Normalize volume", cancel_flag, progress_cb)
}

pub fn extract_frame(
    input_path: &str, output_path: &str, frame_number: usize, fps: f64,
    cancel_flag: Arc<AtomicBool>,
) -> RunResult {
    if fps <= 0.0 {
        return RunResult { success: false, message: "Invalid FPS".to_string() };
    }
    let timestamp = frame_number as f64 / fps;
    log::info!("Extracting frame #{} from {} -> {}", frame_number, input_path, output_path);
    let cmd = vec![
        "ffmpeg".to_string(), "-y".to_string(),
        "-ss".to_string(), format!("{:.6}", timestamp),
        "-i".to_string(), input_path.to_string(),
        "-frames:v".to_string(), "1".to_string(),
        "-update".to_string(), "1".to_string(),
        "-q:v".to_string(), "2".to_string(),
        output_path.to_string(),
    ];
    run_command_simple(&cmd, cancel_flag)
}
