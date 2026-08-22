pub const SIGMA_MIN: f64 = 1.0;
pub const SIGMA_MAX: f64 = 30.0;
/// Threshold value that disables denoise for a content type.
pub const DENOISE_OFF: f64 = -1.0;

use crate::ffmpeg::probe::VideoType;
use crate::settings::Settings;

/// Spatial denoiser, выбранный по типу контента (см. docs/task new settings.md):
/// - аниме: KNLMeansCL (сохраняет lineart, BM3D портит линии);
/// - лайв-экшн / 3D-рендер: BM3D (bm3dcuda / bm3d).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DenoiseFilter {
    Bm3d,
    Knlmeans,
}

impl DenoiseFilter {
    pub fn for_type(video_type: &VideoType) -> Self {
        match video_type {
            VideoType::Animation => DenoiseFilter::Knlmeans,
            VideoType::LiveAction | VideoType::Rendered => DenoiseFilter::Bm3d,
        }
    }
}

/// Resolved denoise parameters passed through the compression pipeline so the
/// denoise script can be (re)generated for the full file or for per-chunk tests.
#[derive(Debug, Clone)]
pub struct DenoiseSpec {
    pub input: String,
    pub sigma: f64,
    pub fps: f64,
    pub filter: DenoiseFilter,
}

/// Returns the denoise sigma to use when the file's measured grain (median YDIF)
/// is at/above `threshold`, else `None` (no denoise needed).
/// A non-positive `threshold` (e.g. `DENOISE_OFF`) disables denoise.
pub fn sigma_from_ydif(ydif: Option<f64>, threshold: f64) -> Option<f64> {
    match ydif {
        Some(y) if threshold > 0.0 && y >= threshold => Some(y.clamp(SIGMA_MIN, SIGMA_MAX)),
        _ => None,
    }
}

/// Per-content-type denoise threshold from settings (`DENOISE_OFF` = disabled).
pub fn denoise_threshold_for(settings: &Settings, video_type: &VideoType) -> f64 {
    match video_type {
        VideoType::Animation => settings.denoise_threshold_animation,
        VideoType::LiveAction => settings.denoise_threshold_liveaction,
        VideoType::Rendered => settings.denoise_threshold_rendered,
    }
}

/// Resolves the denoise sigma for a file given its content type, settings and
/// measured grain YDIF. Returns `None` when denoise is disabled for the type or
/// the grain is below the threshold.
pub fn denoise_sigma_for(
    settings: &Settings,
    video_type: &VideoType,
    ydif: Option<f64>,
) -> Option<f64> {
    let threshold = denoise_threshold_for(settings, video_type);
    sigma_from_ydif(ydif, threshold)
}
