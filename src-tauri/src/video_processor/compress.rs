use std::path::Path;
use std::sync::Arc;
use std::sync::atomic::AtomicBool;
use log::{error, warn, info};

use crate::config::COMPRESSED_VIDEO_SUFFIX;
use crate::crf_extractor::get_crf_from_file;
use crate::estimator::estimate_video_complexity;
use crate::ffmpeg::encode::{compress_video_core, compress_video_core_no_subtitles, compress_video_core_full_map, fix_vfr_target_crf};
use crate::ffmpeg::probe::{get_gpu_info, get_video_info_raw, VideoInfo};
use crate::video_processor::chunk_test::find_best_crf;

pub fn get_full_video_info(input_path: &str) -> Result<VideoInfo, String> {
    let mut info = get_video_info_raw(input_path)?;
    let gpu = get_gpu_info();
    let (complexity_score, complexity_desc) = estimate_video_complexity(&info);
    let crf_value = get_crf_from_file(input_path);
    info!("CRF for {}: {:?}", input_path, crf_value);
    info.gpu_info = gpu.clone();
    info.processing_mode = if gpu.contains("Available GPUs") { "GPU" } else { "CPU" }.to_string();
    info.complexity_score = complexity_score;
    info.complexity_desc = complexity_desc;
    info.crf_value = crf_value;
    Ok(info)
}

pub fn compress_video(
    input_path: &str, output_format: &str, codec: &str, crf_value: i32,
    preset_value: &str, force_vfr_fix: bool, use_hardware: bool,
    cancel_flag: Arc<AtomicBool>,
    progress_cb: Option<Arc<dyn Fn(i32, String) + Send + Sync>>,
    output_dir: Option<&str>,
    auto_crf: bool, target_vmaf: f64,
) -> Result<String, String> {
    let input_p = Path::new(input_path);
    let mut actual_crf = crf_value;

    if auto_crf {
        actual_crf = find_best_crf(input_path, codec, preset_value, use_hardware, target_vmaf, cancel_flag.clone(), progress_cb.clone(), force_vfr_fix);
        if let Some(ref cb) = progress_cb {
            cb(15, format!("Auto CRF: selected {}. Starting compress...", actual_crf));
        }
    } else if let Some(ref cb) = progress_cb {
        cb(5, "Analyzing video...".to_string());
    }

    let video_info = get_full_video_info(input_path).map_err(|e| {
        error!("Failed to get video info for {}: {}", input_path, e);
        e
    })?;
    let duration = video_info.duration;
    if duration <= 0.0 {
        error!("Invalid video duration for {}: {}", input_path, duration);
        return Err("Invalid video duration".to_string());
    }

    let needs_fix = force_vfr_fix || video_info.needs_vfr_fix;
    let stem = input_p.file_stem().map(|s| s.to_string_lossy().to_string()).unwrap_or_default();
    let ext = output_format;
    let output_path = if let Some(dir) = output_dir {
        Path::new(dir).join(format!("{}{}.{}", stem, COMPRESSED_VIDEO_SUFFIX, ext))
    } else {
        input_p.parent().unwrap_or(Path::new(".")).join(format!("{}{}.{}", stem, COMPRESSED_VIDEO_SUFFIX, ext))
    };
    let output_str = output_path.to_string_lossy().to_string();
    if output_path.exists() {
        if let Err(e) = std::fs::remove_file(&output_path) {
            warn!("Failed to remove existing output {:?}: {}", output_path, e);
        }
    }

    if needs_fix {
        let result = fix_vfr_target_crf(
            input_path, &output_str, output_format, codec, actual_crf,
            preset_value, duration, use_hardware, &video_info, cancel_flag.clone(), progress_cb.clone(),
        );
        if !result.success {
            error!("VFR-fix error for {}: {}", input_path, result.message);
            return Err(format!("VFR-fix error: {}", result.message));
        }
    } else {
        let result = compress_video_core(
            input_path, &output_str, output_format, codec, actual_crf,
            preset_value, duration, &video_info, use_hardware, cancel_flag.clone(), progress_cb.clone(),
        );
        if !result.success {
            warn!("First compress attempt failed for {}, trying without subtitles", input_path);
            let result2 = compress_video_core_no_subtitles(
                input_path, &output_str, output_format, codec, actual_crf,
                preset_value, duration, &video_info, use_hardware, cancel_flag.clone(), progress_cb.clone(),
            );
            if !result2.success {
                warn!("Second compress attempt failed for {}, trying full map", input_path);
                let final_cb = progress_cb.clone();
                let result3 = compress_video_core_full_map(
                    input_path, &output_str, output_format, codec, actual_crf,
                    preset_value, duration, cancel_flag, final_cb,
                );
                if !result3.success {
                    error!("All compress attempts failed for {}: {}", input_path, result3.message);
                    return Err(format!("Compress error: {}", result3.message));
                }
            }
        }
    }

    if let Some(cb) = progress_cb {
        cb(100, "Done!".to_string());
    }
    Ok(output_str)
}
