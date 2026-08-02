pub mod iqa_metrics;
pub mod oximedia_metrics;

use serde::{Serialize, Deserialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MetricResult {
    pub metric: String,
    pub score: f64,
    pub unit: String,
    pub passed: bool,
    pub target: f64,
    pub compute_ms: u64,
    /// Perceptual similarity in 0-100% (higher = closer to original visually).
    pub percent: f64,
}

/// Convert a metric score to a human-perceptual similarity percentage (0-100%).
///
/// Rules: higher = more similar to the original. 100% = visually identical.
/// - Metrics already on [0,1] with higher-is-better map directly to percent.
/// - Error/distance metrics (lower-is-better) are inverted.
/// - Unbounded metrics are normalized against a practical "worst case".
pub fn score_to_percent(metric: &str, score: f64) -> f64 {
    let p = match metric {
        // Higher is better, already 0-1
        "SSIM" | "MS-SSIM" | "IW-SSIM" | "VIF" => score * 100.0,
        // Lower is better: DSSIM = (1 - SSIM)/2
        "DSSIM" => (1.0 - 2.0 * score) * 100.0,
        // LPIPS: 0 = identical, ~1 = very different
        "LPIPS (oximedia)" => (1.0 - score) * 100.0,
        // PSNR: 0 dB = garbage, 50 dB = essentially lossless
        "PSNR" => (score / 50.0 * 100.0).clamp(0.0, 100.0),
        "PSNR-HVS-M" => (score / 50.0 * 100.0).clamp(0.0, 100.0),
        // Butteraugli: 0 = identical, 10+ = heavily distorted
        "Butteraugli" => (1.0 - score / 10.0).max(0.0) * 100.0,
        // CIEDE2000: 0 = identical color, 10+ = large color difference
        "CIEDE2000" => (1.0 - score / 10.0).max(0.0) * 100.0,
        // VMAF is already 0-100
        "VMAF" => score,
        _ => {
            let clamped = score.clamp(0.0, 1.0);
            clamped * 100.0
        }
    };
    p.clamp(0.0, 100.0)
}
