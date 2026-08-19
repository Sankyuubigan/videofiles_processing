pub const SIGMA_MIN: f64 = 1.0;
pub const SIGMA_MAX: f64 = 30.0;

/// Resolved denoise parameters passed through the compression pipeline so the
/// denoise script can be (re)generated for the full file or for per-chunk tests.
#[derive(Debug, Clone)]
pub struct DenoiseSpec {
    pub input: String,
    pub sigma: f64,
    pub fps: f64,
}

/// Returns the denoise sigma to use when the file's measured grain (median YDIF)
/// is at/above `threshold`, else `None` (no denoise needed).
pub fn sigma_from_ydif(ydif: Option<f64>, threshold: f64) -> Option<f64> {
    match ydif {
        Some(y) if y >= threshold => Some(y.clamp(SIGMA_MIN, SIGMA_MAX)),
        _ => None,
    }
}
