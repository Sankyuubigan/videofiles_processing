use std::path::Path;
use std::sync::Arc;
use std::sync::atomic::AtomicBool;
use log::error;

use crate::config::EXTRACTED_FRAME_SUFFIX;
use crate::ffmpeg::edit::extract_frame as extract_core;
use crate::video_processor::compress::get_full_video_info;

pub fn extract_frame(
    input_path: &str, frame_number: usize,
    cancel_flag: Arc<AtomicBool>,
    output_dir: Option<&str>,
) -> Result<String, String> {
    let video_info = get_full_video_info(input_path).map_err(|e| {
        error!("Failed to get video info for {}: {}", input_path, e);
        e
    })?;
    let fps = video_info.fps;
    if fps <= 0.0 {
        error!("Could not determine video FPS for {}", input_path);
        return Err("Could not determine video FPS".to_string());
    }
    let total_frames = (video_info.duration * fps) as usize;
    if frame_number >= total_frames {
        error!("Frame #{} exceeds video (total: ~{}) for {}", frame_number, total_frames, input_path);
        return Err(format!("Frame #{} exceeds video (total frames: ~{})", frame_number, total_frames));
    }

    let input_p = Path::new(input_path);
    let stem = input_p.file_stem().map(|s| s.to_string_lossy().to_string()).unwrap_or_default();
    let codec_short = video_info.video_codec.replace("hevc", "h265");
    let crf_str = video_info.crf_value.map(|v| format!("{}", v as i32)).unwrap_or_else(|| "na".to_string());
    let output_name = format!("{}{}_{}_crf{}_frame{:06}.jpg", stem, EXTRACTED_FRAME_SUFFIX, codec_short, crf_str, frame_number);
    let output_path = if let Some(dir) = output_dir {
        Path::new(dir).join(&output_name)
    } else {
        input_p.parent().unwrap_or(Path::new(".")).join(&output_name)
    };
    let output_str = output_path.to_string_lossy().to_string();

    let result = extract_core(input_path, &output_str, frame_number, fps, cancel_flag);
    if !result.success {
        error!("Frame extraction error for {}: {}", input_path, result.message);
        return Err(format!("Frame extraction error: {}", result.message));
    }
    Ok(output_str)
}
