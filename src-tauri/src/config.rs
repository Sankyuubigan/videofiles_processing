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
