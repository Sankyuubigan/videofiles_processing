use serde::{Deserialize, Serialize};
use std::collections::HashMap;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Hash)]
pub enum OutputFormat {
    MP4,
    WebM,
    MKV,
}

impl OutputFormat {
    pub fn all() -> Vec<Self> {
        vec![Self::MP4, Self::WebM, Self::MKV]
    }
    
    pub fn extension(&self) -> &'static str {
        match self {
            Self::MP4 => "mp4",
            Self::WebM => "webm",
            Self::MKV => "mkv",
        }
    }
    
    pub fn codec(&self) -> &'static str {
        match self {
            Self::MP4 => "libx264",
            Self::WebM => "libvpx-vp9",
            Self::MKV => "libx264",
        }
    }
    
    pub fn audio_codec(&self) -> &'static str {
        match self {
            Self::MP4 => "aac",
            Self::WebM => "libopus",
            Self::MKV => "aac",
        }
    }
}

impl std::fmt::Display for OutputFormat {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::MP4 => write!(f, "MP4"),
            Self::WebM => write!(f, "WebM"),
            Self::MKV => write!(f, "MKV"),
        }
    }
}

pub const DEFAULT_OUTPUT_FORMAT: OutputFormat = OutputFormat::MP4;

#[derive(Debug, Clone)]
pub struct AppConfig {
    pub crf_defaults: HashMap<OutputFormat, u8>,
    pub crf_ranges: HashMap<OutputFormat, (u8, u8)>,
    pub default_fps_fix: f32,
    pub default_fix_crf_h264: u8,
    pub default_fix_crf_vp9: u8,
    pub temp_fixed_video_suffix: String,
    pub compressed_video_suffix: String,
}

impl Default for AppConfig {
    fn default() -> Self {
        let mut crf_defaults = HashMap::new();
        crf_defaults.insert(OutputFormat::MP4, 23);
        crf_defaults.insert(OutputFormat::WebM, 28);
        crf_defaults.insert(OutputFormat::MKV, 23);
        
        let mut crf_ranges = HashMap::new();
        crf_ranges.insert(OutputFormat::MP4, (18, 35));
        crf_ranges.insert(OutputFormat::WebM, (15, 50));
        crf_ranges.insert(OutputFormat::MKV, (18, 35));
        
        Self {
            crf_defaults,
            crf_ranges,
            default_fps_fix: 25.0,
            default_fix_crf_h264: 18,
            default_fix_crf_vp9: 18,
            temp_fixed_video_suffix: "_temp_fixed_cfr".to_string(),
            compressed_video_suffix: "_compressed".to_string(),
        }
    }
}

impl AppConfig {
    pub fn get_default_crf(&self, format: &OutputFormat) -> u8 {
        *self.crf_defaults.get(format).unwrap_or(&23)
    }
    
    pub fn get_crf_range(&self, format: &OutputFormat) -> (u8, u8) {
        *self.crf_ranges.get(format).unwrap_or(&(18, 35))
    }
}