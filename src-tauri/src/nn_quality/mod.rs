pub mod models;
pub mod session;
pub mod lpips;
pub mod dists;
pub mod content_type;

use std::sync::Arc;
use std::sync::atomic::AtomicBool;
use std::time::Instant;
use log::info;

pub struct NnQualityResult {
    pub score: f64,
    pub metric: String,
    pub inference_ms: u64,
    pub passed: bool,
    pub target: f64,
}

/// Run LPIPS quality check on a video pair
pub fn run_lpips(
    original_path: &str,
    encoded_path: &str,
    start_time: f64,
    duration: f64,
    width: usize,
    height: usize,
    ignore_noise: bool,
    cancel_flag: Arc<AtomicBool>,
    target: f64,
) -> Result<NnQualityResult, String> {
    let t0 = Instant::now();

    let score = lpips::calculate_lpips(
        original_path,
        encoded_path,
        start_time,
        duration,
        width,
        height,
        ignore_noise,
        cancel_flag,
    )?;

    let inference_ms = t0.elapsed().as_millis() as u64;
    let passed = score <= target;

    info!(
        "LPIPS inference: {}ms, score={:.4} (target < {:.4}) {}",
        inference_ms,
        score,
        target,
        if passed { "PASSED" } else { "FAILED" }
    );

    Ok(NnQualityResult {
        score,
        metric: "LPIPS".to_string(),
        inference_ms,
        passed,
        target,
    })
}

/// Run DISTS quality check on a video pair
pub fn run_dists(
    original_path: &str,
    encoded_path: &str,
    start_time: f64,
    duration: f64,
    width: usize,
    height: usize,
    ignore_noise: bool,
    cancel_flag: Arc<AtomicBool>,
    target: f64,
) -> Result<NnQualityResult, String> {
    let t0 = Instant::now();

    let score = dists::calculate_dists(
        original_path,
        encoded_path,
        start_time,
        duration,
        width,
        height,
        ignore_noise,
        cancel_flag,
    )?;

    let inference_ms = t0.elapsed().as_millis() as u64;
    let passed = score <= target;

    info!(
        "DISTS inference: {}ms, score={:.4} (target < {:.4}) {}",
        inference_ms,
        score,
        target,
        if passed { "PASSED" } else { "FAILED" }
    );

    Ok(NnQualityResult {
        score,
        metric: "DISTS".to_string(),
        inference_ms,
        passed,
        target,
    })
}
