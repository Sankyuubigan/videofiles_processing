use std::path::Path;
use std::sync::Arc;
use std::sync::atomic::AtomicBool;
use log::{error, warn, info};

use crate::config::COMPRESSED_VIDEO_SUFFIX;
use crate::crf_extractor::get_crf_from_file;
use crate::estimator::estimate_video_complexity;
use crate::ffmpeg::encode::{compress_video_core, compress_video_core_no_subtitles, compress_video_core_full_map, fix_vfr_target_crf};
use crate::ffmpeg::probe::{get_video_info_raw, VideoInfo};
use crate::settings::Settings;
use crate::video_processor::chunk_test::find_best_crf;
use crate::video_processor::content_type::detect_content_type;
use crate::commands::file_commands::TestResult;
use crate::process_control::PidTracker;

pub fn get_full_video_info(input_path: &str) -> Result<VideoInfo, String> {
    let mut info = get_video_info_basic(input_path)?;
    let video_type = detect_content_type(input_path, info.duration);
    info!("Content type for {}: {:?}", input_path, video_type);
    info.video_type = video_type;
    Ok(info)
}

pub fn get_video_info_basic(input_path: &str) -> Result<VideoInfo, String> {
    let input_path_owned = input_path.to_string();

    let handle_info = std::thread::spawn({
        let p = input_path_owned.clone();
        move || get_video_info_raw(&p)
    });
    let handle_crf = std::thread::spawn({
        let p = input_path_owned.clone();
        move || get_crf_from_file(&p)
    });

    let mut info = handle_info.join().map_err(|e| format!("Thread join error: {:?}", e))??;
    let crf_value = handle_crf.join().map_err(|e| format!("Thread join error: {:?}", e))?;
    info!("CRF for {}: {:?}", input_path, crf_value);

    let (complexity_score, complexity_desc) = estimate_video_complexity(&info);

    info.processing_mode = if info.gpu_info.contains("Available GPUs") { "GPU" } else { "CPU" }.to_string();
    info.complexity_score = complexity_score;
    info.complexity_desc = complexity_desc;
    info.crf_value = crf_value;
    Ok(info)
}

pub fn check_auto_skip(
    input_path: &str,
    video_info: &VideoInfo,
    test_result: Option<&TestResult>,
    settings: &Settings,
) -> Option<String> {
    let filename = Path::new(input_path).file_name()
        .map(|s| s.to_string_lossy().to_string())
        .unwrap_or_else(|| input_path.to_string());

    if settings.skip_min_diff_enabled {
        if let Some(tr) = test_result.filter(|t| t.error.is_none()) {
            let diff_str = tr.test_diff.trim();
            let is_reduction = diff_str.starts_with('-');
            if let Ok(diff) = diff_str.trim_start_matches(|c: char| c == '-' || c == '+')
                .trim_end_matches('%').parse::<f64>()
            {
                if !is_reduction || diff < settings.skip_min_diff_percent {
                    return Some(format!(
                        "SKIP: {} — size reduction {:.1}% < minimum {:.1}%",
                        filename, diff, settings.skip_min_diff_percent
                    ));
                }
            }
        }
    }

    if settings.skip_min_crf_enabled {
        if let Some(crf) = video_info.crf_value {
            if crf >= settings.skip_min_crf_value {
                return Some(format!(
                    "SKIP: {} — original CRF {} >= minimum CRF {}",
                    filename, crf, settings.skip_min_crf_value
                ));
            }
        }
    }

    None
}

pub fn compress_video(
    input_path: &str, output_format: &str, codec: &str, crf_value: i32,
    preset_value: &str, force_vfr_fix: bool, use_hardware: bool,
    cancel_flag: Arc<AtomicBool>,
    progress_cb: Option<Arc<dyn Fn(i32, String) + Send + Sync>>,
    output_dir: Option<&str>,
    auto_crf: bool, target_vmaf: f64, target_ssimulacra2: f64,
    test_result: Option<&TestResult>,
    child_pid: Option<PidTracker>,
) -> Result<String, String> {
    let input_p = Path::new(input_path);
    let mut actual_crf = crf_value;

    let video_info = get_full_video_info(input_path).map_err(|e| {
        error!("Failed to get video info for {}: {}", input_path, e);
        e
    })?;
    let duration = video_info.duration;
    if duration <= 0.0 {
        error!("Invalid video duration for {}: {}", input_path, duration);
        return Err("Invalid video duration".to_string());
    }

    if auto_crf {
        let settings = crate::settings::load_settings();
        if let Some(reason) = check_auto_skip(input_path, &video_info, test_result, &settings) {
            warn!("{}", reason);
            if let Some(ref cb) = progress_cb {
                cb(100, reason.clone());
            }
            return Err(reason);
        }
        let acrf = find_best_crf(input_path, codec, preset_value, use_hardware, target_vmaf, target_ssimulacra2, cancel_flag.clone(), progress_cb.clone(), force_vfr_fix, child_pid.clone());
        if acrf.cancelled {
            warn!("Auto CRF cancelled for {}", input_path);
            return Err("Operation cancelled".to_string());
        }
        match acrf.crf {
            Some(crf) => {
                actual_crf = crf;
                if let Some(ref cb) = progress_cb {
                    cb(15, format!("Auto CRF: selected {}. Starting compress...", actual_crf));
                }
            }
            None => {
                let filename = input_p.file_name().map(|s| s.to_string_lossy().to_string()).unwrap_or_else(|| input_path.to_string());
                let msg = format!("SKIP: {} — target unreachable (best achieved: {:.1})", filename, acrf.best_vmaf);
                warn!("{}", msg);
                if let Some(ref cb) = progress_cb {
                    cb(100, msg.clone());
                }
                return Err(msg);
            }
        }
    } else if let Some(ref cb) = progress_cb {
        cb(5, "Analyzing video...".to_string());
    }

    let needs_fix = force_vfr_fix || video_info.needs_vfr_fix;
    let video_type = &video_info.video_type;
    info!("Compress: content type={:?}, codec={}, CRF={}", video_type, codec, actual_crf);
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
            preset_value, duration, use_hardware, &video_info, video_type, cancel_flag.clone(), progress_cb.clone(), child_pid.clone(),
        );
        if !result.success {
            error!("VFR-fix error for {}: {}", input_path, result.message);
            return Err(format!("VFR-fix error: {}", result.message));
        }
    } else {
        let result = compress_video_core(
            input_path, &output_str, output_format, codec, actual_crf,
            preset_value, duration, &video_info, video_type, use_hardware, cancel_flag.clone(), progress_cb.clone(), child_pid.clone(),
        );
        if !result.success {
            warn!("First compress attempt failed for {}, trying without subtitles", input_path);
            let result2 = compress_video_core_no_subtitles(
                input_path, &output_str, output_format, codec, actual_crf,
                preset_value, duration, &video_info, video_type, use_hardware, cancel_flag.clone(), progress_cb.clone(), child_pid.clone(),
            );
            if !result2.success {
                warn!("Second compress attempt failed for {}, trying full map", input_path);
                let final_cb = progress_cb.clone();
                let result3 = compress_video_core_full_map(
                    input_path, &output_str, output_format, codec, actual_crf,
                    preset_value, duration, cancel_flag, final_cb, child_pid.clone(),
                );
                if !result3.success {
                    error!("All compress attempts failed for {}: {}", input_path, result3.message);
                    return Err(format!("Compress error: {}", result3.message));
                }
            }
        }
    }

    let original_size = video_info.size_mb;
    let compressed_size = std::fs::metadata(&output_path)
        .map(|m| m.len() as f64 / (1024.0 * 1024.0))
        .unwrap_or(0.0);

    if original_size > 0.0 && compressed_size > 0.0 {
        let diff_percent = ((original_size - compressed_size) / original_size) * 100.0;
        let filename = input_p.file_name().map(|s| s.to_string_lossy().to_string()).unwrap_or_else(|| input_path.to_string());
        if diff_percent > 0.0 {
            info!("Compressed: {} — size reduced by {:.1}% ({:.1} MB -> {:.1} MB)", filename, diff_percent, original_size, compressed_size);
            if let Some(ref cb) = progress_cb {
                cb(100, format!("Done! Size reduced by {:.1}%", diff_percent));
            }
        } else {
            info!("Compressed: {} — size INCREASED by {:.1}% ({:.1} MB -> {:.1} MB)", filename, diff_percent.abs(), original_size, compressed_size);
            if let Some(ref cb) = progress_cb {
                cb(100, format!("Done! Size increased by {:.1}%", diff_percent.abs()));
            }
        }
    } else if let Some(cb) = progress_cb {
        cb(100, "Done!".to_string());
    }

    Ok(output_str)
}
