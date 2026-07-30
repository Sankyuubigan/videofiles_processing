use std::sync::Arc;
use std::sync::atomic::AtomicBool;

use log::{warn, info, error};
use crate::config::get_codecs;
use crate::estimator::format_duration;
use crate::ffmpeg::encode::{calculate_vmaf, encode_chunk};
use crate::video_processor::compress::get_full_video_info;

pub struct AutoCrfResult {
    pub crf: Option<i32>,
    pub best_vmaf: f64,
    pub target_vmaf: f64,
}

pub fn find_best_crf(
    input_path: &str, codec: &str, preset_value: &str, use_hardware: bool,
    target_vmaf: f64, cancel_flag: Arc<AtomicBool>,
    progress_cb: Option<Arc<dyn Fn(i32, String) + Send + Sync>>,
    force_vfr_fix: bool,
) -> AutoCrfResult {
    let default_crf = get_codecs().get(codec).map(|c| c.crf_default).unwrap_or(22);
    let video_info = match get_full_video_info(input_path) {
        Ok(i) => i,
        Err(_) => return AutoCrfResult { crf: Some(default_crf), best_vmaf: 0.0, target_vmaf },
    };
    let width = video_info.width;
    let duration = video_info.duration;
    let codecs = get_codecs();
    let codec_info = match codecs.get(codec) {
        Some(c) => c.clone(),
        None => match codecs.get("libx264") {
            Some(c) => {
                log::warn!("Codec '{}' not found, falling back to libx264", codec);
                c.clone()
            }
            None => {
                log::error!("No codecs available and libx264 not found");
                return AutoCrfResult { crf: Some(22), best_vmaf: 0.0, target_vmaf };
            }
        },
    };
    let mut crf_low = codec_info.crf_min;
    let mut crf_high = codec_info.crf_max;

    let vmaf_subsample = 5;
    let chunk_count = 5;
    let chunk_duration = 2.0_f64;

    let timestamps = if duration < 30.0 {
        vec![duration * 0.5]
    } else {
        match chunk_count {
            1 => vec![duration * 0.5],
            2 => vec![duration * 0.2, duration * 0.8],
            3 => vec![duration * 0.1, duration * 0.5, duration * 0.8],
            4 => vec![duration * 0.1, duration * 0.35, duration * 0.6, duration * 0.85],
            _ => vec![duration * 0.1, duration * 0.3, duration * 0.5, duration * 0.7, duration * 0.9],
        }
    };

    let mut best_crf_closest = codec_info.crf_default;
    let mut best_vmaf_closest = 0.0_f64;
    let mut min_diff = f64::MAX;
    let mut best_crf_acceptable = -1;
    let mut best_vmaf_acceptable = 0.0_f64;
    let temp_dir = std::env::temp_dir();

    for step in 0..6 {
        if crf_low > crf_high { break; }
        let mid_crf = (crf_low + crf_high) / 2;
        if let Some(ref cb) = progress_cb {
            cb(10 + step * 10, format!("Auto CRF: testing CRF {}...", mid_crf));
        }
        let mut vmaf_scores = Vec::new();
        let mut libvmaf_missing = false;

        for (i, ts) in timestamps.iter().enumerate() {
            let chunk_path = temp_dir.join(format!("auto_crf_{}_{}_{}.mp4", std::process::id(), chrono::Utc::now().timestamp(), i));
            let chunk_str = chunk_path.to_string_lossy().to_string();
            let result = encode_chunk(
                input_path, &chunk_str, *ts, chunk_duration,
                codec, mid_crf, preset_value, use_hardware, &video_info, force_vfr_fix, cancel_flag.clone(),
            );
            if !result.success {
                warn!("Auto CRF: encode failed for chunk {} at CRF {}: {}", i, mid_crf, result.message);
                break;
            }
            let vmaf = calculate_vmaf(
                input_path, &chunk_str, *ts, chunk_duration,
                vmaf_subsample, width, &video_info, force_vfr_fix, cancel_flag.clone(),
            );
            if let Err(e) = std::fs::remove_file(&chunk_path) {
                warn!("Failed to remove chunk {:?}: {}", chunk_path, e);
            }
            if vmaf < 0.0 {
                error!("Auto CRF: VMAF failed for chunk {} at CRF {} (score={})", i, mid_crf, vmaf);
                libvmaf_missing = true;
                break;
            }
            info!("Auto CRF: chunk {} at CRF {} -> VMAF={:.2}", i, mid_crf, vmaf);
            vmaf_scores.push(vmaf);
        }

        if libvmaf_missing || vmaf_scores.is_empty() {
            warn!("Auto CRF: VMAF returned error at step {}, aborting search", step + 1);
            break;
        }
        let avg_vmaf = vmaf_scores.iter().sum::<f64>() / vmaf_scores.len() as f64;
        let diff = (avg_vmaf - target_vmaf).abs();

        info!("Auto CRF: step {}, CRF {}, Avg VMAF={:.2}, Target={}", step + 1, mid_crf, avg_vmaf, target_vmaf);

        if avg_vmaf >= (target_vmaf - 0.1) && mid_crf > best_crf_acceptable {
            best_crf_acceptable = mid_crf;
            best_vmaf_acceptable = avg_vmaf;
        }
        if diff < min_diff {
            min_diff = diff;
            best_crf_closest = mid_crf;
            best_vmaf_closest = avg_vmaf;
        }
        if avg_vmaf < target_vmaf {
            crf_high = mid_crf - 1;
        } else {
            crf_low = mid_crf + 1;
        }
    }

    let (final_crf, best_vmaf) = if best_crf_acceptable != -1 {
        (Some(best_crf_acceptable), best_vmaf_acceptable)
    } else {
        (None, best_vmaf_closest)
    };

    if let Some(crf) = final_crf {
        info!("Auto CRF done: selected CRF {} for target VMAF {} (achieved: {:.1})", crf, target_vmaf, best_vmaf);
        if let Some(cb) = progress_cb {
            cb(60, format!("Auto CRF done: CRF {}", crf));
        }
    } else {
        warn!("Auto CRF: target VMAF {} unreachable. Best CRF {} gives VMAF {:.1}", target_vmaf, best_crf_closest, best_vmaf);
        if let Some(cb) = progress_cb {
            cb(60, format!("Auto CRF: target VMAF {} unreachable (best: {:.1})", target_vmaf, best_vmaf));
        }
    }

    AutoCrfResult { crf: final_crf, best_vmaf, target_vmaf }
}

pub struct ChunkTestResult {
    pub file_path: String,
    pub test_diff: String,
    pub test_est_size: String,
    pub test_est_time: String,
    pub test_vmaf: f64,
    pub is_profitable: bool,
}

pub fn run_chunk_test(
    input_path: &str, codec: &str, crf_value: i32, preset_value: &str,
    use_hardware: bool, cancel_flag: Arc<AtomicBool>,
    auto_crf: bool, target_vmaf: f64, force_vfr_fix: bool,
) -> Result<ChunkTestResult, String> {
    let mut actual_crf = crf_value;
    if auto_crf {
        info!("Chunk Test: Auto CRF enabled, target VMAF={}", target_vmaf);
        let acrf = find_best_crf(input_path, codec, preset_value, use_hardware, target_vmaf, cancel_flag.clone(), None, force_vfr_fix);
        actual_crf = acrf.crf.unwrap_or_else(|| {
            warn!("Chunk Test: Auto CRF target unreachable, using fallback CRF (best VMAF: {:.1})", acrf.best_vmaf);
            crf_value  // fallback to user-provided CRF for the test
        });
        info!("Chunk Test: Auto CRF selected CRF {}", actual_crf);
    }

    let video_info = get_full_video_info(input_path)?;
    let duration = video_info.duration;
    let width = video_info.width;

    let chunk_count = 5;
    let chunk_duration = 2.0_f64;
    let vmaf_subsample = 5;

    let timestamps = if duration < 30.0 {
        vec![duration * 0.5]
    } else {
        match chunk_count {
            1 => vec![duration * 0.5],
            2 => vec![duration * 0.2, duration * 0.8],
            3 => vec![duration * 0.1, duration * 0.5, duration * 0.8],
            4 => vec![duration * 0.1, duration * 0.35, duration * 0.6, duration * 0.85],
            _ => vec![duration * 0.1, duration * 0.3, duration * 0.5, duration * 0.7, duration * 0.9],
        }
    };

    let temp_dir = std::env::temp_dir();
    let mut total_size_bytes: u64 = 0;
    let mut vmaf_scores = Vec::new();
    let mut libvmaf_missing = false;
    let mut encode_time_total: f64 = 0.0;

    for (i, ts) in timestamps.iter().enumerate() {
        let out_path = temp_dir.join(format!("chunk_test_{}.mp4", i));
        let out_str = out_path.to_string_lossy().to_string();

        let start = std::time::Instant::now();
        let result = encode_chunk(
            input_path, &out_str, *ts, chunk_duration,
            codec, actual_crf, preset_value, use_hardware, &video_info, force_vfr_fix, cancel_flag.clone(),
        );
        encode_time_total += start.elapsed().as_secs_f64();

        if !result.success {
            return Err(format!("Error encoding chunk {}: {}", i + 1, result.message));
        }

        if out_path.exists() {
            if !libvmaf_missing {
                let vmaf = calculate_vmaf(
                    input_path, &out_str, *ts, chunk_duration,
                    vmaf_subsample, width, &video_info, force_vfr_fix, cancel_flag.clone(),
                );
                if vmaf == -2.0 {
                    error!("Chunk Test: libvmaf missing, skipping VMAF for remaining chunks");
                    libvmaf_missing = true;
                } else if vmaf >= 0.0 {
                    info!("Chunk Test: chunk {} at CRF {} -> VMAF={:.2}", i, actual_crf, vmaf);
                    vmaf_scores.push(vmaf);
                } else {
                    warn!("Chunk Test: VMAF returned {} for chunk {}", vmaf, i);
                }
            }
            if let Ok(meta) = std::fs::metadata(&out_path) {
                total_size_bytes += meta.len();
            }
            if let Err(e) = std::fs::remove_file(&out_path) {
                warn!("Failed to remove chunk output {:?}: {}", out_path, e);
            }
        }
    }

    let total_chunk_duration = chunk_duration as f64 * timestamps.len() as f64;
    let chunk_bitrate_bps = (total_size_bytes as f64 * 8.0) / total_chunk_duration;
    let est_size_mb = (chunk_bitrate_bps * duration) / 8.0 / (1024.0 * 1024.0);
    let est_time_sec = if encode_time_total > 0.0 {
        let speed_multiplier = total_chunk_duration / encode_time_total;
        duration / speed_multiplier
    } else {
        0.0
    };

    let orig_size_mb = video_info.size_mb;
    let diff_percent = if orig_size_mb > 0.0 {
        ((orig_size_mb - est_size_mb) / orig_size_mb) * 100.0
    } else {
        0.0
    };
    let diff_str = if diff_percent > 0.0 {
        format!("-{:.1}%", diff_percent)
    } else {
        format!("+{:.1}%", diff_percent.abs())
    };

    let avg_vmaf = if vmaf_scores.is_empty() { -1.0 }
    else if libvmaf_missing { -2.0 }
    else { vmaf_scores.iter().sum::<f64>() / vmaf_scores.len() as f64 };

    log::info!("Chunk Test finished for {}: diff={}, est size={}, VMAF={:.1}", input_path, diff_str, format!("{:.1} MB", est_size_mb), avg_vmaf);

    Ok(ChunkTestResult {
        file_path: input_path.to_string(),
        test_diff: diff_str,
        test_est_size: format!("{:.1} MB", est_size_mb),
        test_est_time: format_duration(est_time_sec),
        test_vmaf: avg_vmaf,
        is_profitable: diff_percent > 0.0,
    })
}
