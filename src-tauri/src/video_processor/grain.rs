use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;

use log::{info, warn};
use serde::{Deserialize, Serialize};

use crate::ffmpeg::core::run_command_simple_output;
use crate::nn_quality::assess::chunk_timestamps;

/// Median YDIF below this => clean (no visible grain).
pub const GRAIN_CLEAN_THRESHOLD: f64 = 1.5;
/// Median YDIF at/above this => heavy grain.
pub const GRAIN_HEAVY_THRESHOLD: f64 = 4.0;

/// Default number of sampled windows across the video.
pub const GRAIN_WINDOWS: usize = 4;
/// Default length of each sampled window (seconds).
pub const GRAIN_WINDOW_SEC: f64 = 2.0;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GrainMetrics {
    pub ydif_median: f64,
    pub ydif_min: f64,
    pub ydif_max: f64,
    pub windows_used: usize,
}

/// Estimates temporal grain level by sampling short windows across the video
/// and computing the median inter-frame luma difference (YDIF) per window.
///
/// Motion produces spiky YDIF outliers, while stationary grain raises the
/// median uniformly across all frames - so the median is a robust grain proxy.
pub fn estimate_grain(
    input_path: &str,
    duration: f64,
    windows: usize,
    window_sec: f64,
    cancel_flag: Arc<AtomicBool>,
) -> Result<GrainMetrics, String> {
    let timestamps = chunk_timestamps(duration, windows);
    let mut window_medians: Vec<f64> = Vec::new();
    let mut all_min = f64::MAX;
    let mut all_max = f64::MIN;

    for ts in &timestamps {
        if cancel_flag.load(Ordering::Relaxed) {
            return Err("Operation cancelled".to_string());
        }
        match window_ydif_median(input_path, *ts, window_sec, cancel_flag.clone()) {
            Ok(median) => {
                info!("Grain: window @ {:.1}s -> YDIF median {:.2}", ts, median);
                window_medians.push(median);
                all_min = all_min.min(median);
                all_max = all_max.max(median);
            }
            Err(e) => warn!("Grain: window @ {:.1}s failed: {}", ts, e),
        }
    }

    if window_medians.is_empty() {
        return Err("No grain windows could be analyzed".to_string());
    }

    window_medians.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
    let median = window_medians[window_medians.len() / 2];
    Ok(GrainMetrics {
        ydif_median: median,
        ydif_min: all_min,
        ydif_max: all_max,
        windows_used: window_medians.len(),
    })
}

/// Extracts a short clip at `ts` and returns the median YDIF over its frames.
fn window_ydif_median(
    input_path: &str,
    ts: f64,
    window_sec: f64,
    cancel_flag: Arc<AtomicBool>,
) -> Result<f64, String> {
    let cmd = vec![
        "ffmpeg".to_string(),
        "-y".to_string(),
        "-ss".to_string(),
        format!("{:.3}", ts),
        "-t".to_string(),
        format!("{:.2}", window_sec),
        "-i".to_string(),
        input_path.to_string(),
        "-vf".to_string(),
        "signalstats,metadata=print:file=-:key=lavfi.signalstats.YDIF".to_string(),
        "-f".to_string(),
        "null".to_string(),
        "-".to_string(),
    ];

    let result = run_command_simple_output(&cmd, cancel_flag, None);
    if !result.success {
        return Err(format!("YDIF window at {:.1}s failed: {}", ts, result.message));
    }

    let mut values: Vec<f64> = Vec::new();
    for line in &result.lines {
        if let Some(v) = line.trim().strip_prefix("lavfi.signalstats.YDIF=") {
            if let Ok(val) = v.trim().parse::<f64>() {
                values.push(val);
            }
        }
    }
    if values.is_empty() {
        return Err(format!("No YDIF values captured at {:.1}s", ts));
    }
    values.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
    Ok(values[values.len() / 2])
}

/// Converts median YDIF to a 0-100 "grain-free" score (100 = no grain).
/// `threshold` is the denoise grain threshold from settings.
pub fn grain_free_pct(ydif: f64, threshold: f64) -> f64 {
    (100.0 - ydif / threshold * 100.0).clamp(0.0, 100.0)
}
