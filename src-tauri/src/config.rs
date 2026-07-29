use std::collections::HashMap;

pub const DEFAULT_MIN_CRF_H264: i32 = 18;
pub const DEFAULT_MAX_CRF_H264: i32 = 35;
pub const DEFAULT_CRF_H264: i32 = 22;

pub const DEFAULT_MIN_CRF_H265: i32 = 20;
pub const DEFAULT_MAX_CRF_H265: i32 = 40;
pub const DEFAULT_CRF_H265: i32 = 21;

pub const DEFAULT_MIN_CRF_VP9: i32 = 15;
pub const DEFAULT_MAX_CRF_VP9: i32 = 50;
pub const DEFAULT_CRF_VP9: i32 = 28;

pub const _DEFAULT_FIX_CRF_VP9: i32 = 30;
pub const _DEFAULT_FIX_CRF_H264: i32 = 28;
pub const _DEFAULT_FIX_CRF_H265: i32 = 30;
pub const DEFAULT_FPS_FIX: f64 = 25.0;

pub const _DEFAULT_USE_HARDWARE_ENCODING: bool = false;

pub const H264_PRESETS: &[&str] = &["veryslow", "slower", "slow", "medium", "fast", "faster", "veryfast", "superfast", "ultrafast"];
pub const H265_PRESETS: &[&str] = &["veryslow", "slower", "slow", "medium", "fast", "faster", "veryfast", "superfast", "ultrafast"];
pub const VP9_PRESETS: &[&str] = &["veryslow", "slower", "slow", "medium", "fast", "faster", "veryfast", "superfast", "ultrafast"];

pub const DEFAULT_H264_PRESET: &str = "slow";
pub const DEFAULT_H265_PRESET: &str = "slow";
pub const DEFAULT_VP9_PRESET: &str = "slow";

pub const COMPRESSED_VIDEO_SUFFIX: &str = "_compressed";
pub const TRIMMED_VIDEO_SUFFIX: &str = "_trimmed";
pub const EXTRACTED_FRAME_SUFFIX: &str = "_frame";

pub const _DEFAULT_CODEC_KEY: &str = "libx264";
pub const _DEFAULT_OUTPUT_FORMAT_KEY: &str = "mp4";

#[derive(Debug, Clone)]
pub struct CodecInfo {
    #[allow(dead_code)]
    pub name: String,
    pub crf_min: i32,
    pub crf_max: i32,
    pub crf_default: i32,
    #[allow(dead_code)]
    pub presets: Vec<String>,
    #[allow(dead_code)]
    pub preset_default: String,
}

pub fn get_codecs() -> HashMap<String, CodecInfo> {
    let mut m = HashMap::new();
    m.insert("libx264".to_string(), CodecInfo {
        name: "H.264 (AVC)".to_string(),
        crf_min: DEFAULT_MIN_CRF_H264,
        crf_max: DEFAULT_MAX_CRF_H264,
        crf_default: DEFAULT_CRF_H264,
        presets: H264_PRESETS.iter().map(|s| s.to_string()).collect(),
        preset_default: DEFAULT_H264_PRESET.to_string(),
    });
    m.insert("libx265".to_string(), CodecInfo {
        name: "H.265 (HEVC)".to_string(),
        crf_min: DEFAULT_MIN_CRF_H265,
        crf_max: DEFAULT_MAX_CRF_H265,
        crf_default: DEFAULT_CRF_H265,
        presets: H265_PRESETS.iter().map(|s| s.to_string()).collect(),
        preset_default: DEFAULT_H265_PRESET.to_string(),
    });
    m.insert("libvpx-vp9".to_string(), CodecInfo {
        name: "VP9".to_string(),
        crf_min: DEFAULT_MIN_CRF_VP9,
        crf_max: DEFAULT_MAX_CRF_VP9,
        crf_default: DEFAULT_CRF_VP9,
        presets: VP9_PRESETS.iter().map(|s| s.to_string()).collect(),
        preset_default: DEFAULT_VP9_PRESET.to_string(),
    });
    m
}

#[derive(Debug, Clone)]
pub struct FormatInfo {
    pub name: String,
    pub compatible_codecs: Vec<String>,
    pub audio_codec: String,
    pub default_codec: String,
}

pub fn get_output_formats() -> HashMap<String, FormatInfo> {
    let mut m = HashMap::new();
    m.insert("mp4".to_string(), FormatInfo {
        name: "MP4".to_string(),
        compatible_codecs: vec!["libx264".to_string(), "libx265".to_string()],
        audio_codec: "aac".to_string(),
        default_codec: "libx264".to_string(),
    });
    m.insert("mkv".to_string(), FormatInfo {
        name: "MKV".to_string(),
        compatible_codecs: vec!["libx264".to_string(), "libx265".to_string()],
        audio_codec: "aac".to_string(),
        default_codec: "libx264".to_string(),
    });
    m.insert("hevc".to_string(), FormatInfo {
        name: "HEVC".to_string(),
        compatible_codecs: vec!["libx265".to_string()],
        audio_codec: "aac".to_string(),
        default_codec: "libx265".to_string(),
    });
    m.insert("webm".to_string(), FormatInfo {
        name: "WebM".to_string(),
        compatible_codecs: vec!["libvpx-vp9".to_string()],
        audio_codec: "libopus".to_string(),
        default_codec: "libvpx-vp9".to_string(),
    });
    m
}

pub fn get_h264_crf_factor(crf: i32) -> f64 {
    match crf {
        18 => 1.0, 19 => 0.95, 20 => 0.90, 21 => 0.85, 22 => 0.80, 23 => 0.75,
        24 => 0.70, 25 => 0.65, 26 => 0.60, 27 => 0.55, 28 => 0.50, 29 => 0.45, 30 => 0.40,
        31 => 0.38, 32 => 0.36, 33 => 0.34, 34 => 0.32, 35 => 0.30,
        _ => 0.50,
    }
}

pub fn get_h265_crf_factor(crf: i32) -> f64 {
    match crf {
        20 => 1.0, 21 => 0.95, 22 => 0.90, 23 => 0.85, 24 => 0.80, 25 => 0.75,
        26 => 0.70, 27 => 0.65, 28 => 0.60, 29 => 0.55, 30 => 0.50, 31 => 0.45, 32 => 0.40,
        33 => 0.38, 34 => 0.36, 35 => 0.34, 36 => 0.32, 37 => 0.30, 38 => 0.28, 39 => 0.26,
        40 => 0.24,
        _ => 0.50,
    }
}

pub fn get_vp9_crf_factor(crf: i32) -> f64 {
    match crf {
        15 => 1.0, 16 => 0.95, 17 => 0.90, 18 => 0.85, 19 => 0.80, 20 => 0.75,
        21 => 0.70, 22 => 0.65, 23 => 0.60, 24 => 0.55, 25 => 0.50, 26 => 0.45, 27 => 0.40,
        28 => 0.38, 29 => 0.36, 30 => 0.34, 31 => 0.32, 32 => 0.30, 33 => 0.28, 34 => 0.26,
        35 => 0.24, 36 => 0.22, 37 => 0.20, 38 => 0.18, 39 => 0.16, 40 => 0.14,
        41 => 0.13, 42 => 0.12, 43 => 0.11, 44 => 0.10, 45 => 0.09, 46 => 0.08,
        47 => 0.07, 48 => 0.06, 49 => 0.05, 50 => 0.04,
        _ => 0.50,
    }
}

pub fn get_preset_factor(preset: &str) -> f64 {
    match preset {
        "veryslow" => 0.85, "slower" => 0.88, "slow" => 0.92,
        "medium" => 1.0, "fast" => 1.1, "faster" => 1.2,
        "veryfast" => 1.3, "superfast" => 1.4, "ultrafast" => 1.5,
        _ => 1.0,
    }
}
