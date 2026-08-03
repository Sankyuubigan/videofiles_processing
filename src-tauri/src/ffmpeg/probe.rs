use serde::{Deserialize, Serialize};
use std::path::Path;

use super::core::run_ffprobe_json;
use crate::settings::get_actual_ffmpeg_path;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum VideoType {
    Animation,
    LiveAction,
}

impl std::fmt::Display for VideoType {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            VideoType::Animation => write!(f, "Animation"),
            VideoType::LiveAction => write!(f, "LiveAction"),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AudioTrack {
    pub index: usize,
    pub codec: String,
    pub language: String,
    pub title: String,
    pub channels: usize,
    pub sample_rate: String,
    pub bit_rate: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VideoInfo {
    pub path: String,
    pub duration: f64,
    pub size_mb: f64,
    pub video_bitrate: i64,
    pub audio_bitrate: i64,
    pub width: usize,
    pub height: usize,
    pub fps: f64,
    pub needs_vfr_fix: bool,
    pub is_hevc: bool,
    pub is_10bit: bool,
    pub video_codec: String,
    pub pixel_format: String,
    pub has_subtitles: bool,
    pub audio_tracks: Vec<AudioTrack>,
    pub gpu_info: String,
    pub processing_mode: String,
    pub complexity_score: i32,
    pub complexity_desc: String,
    pub crf_value: Option<f64>,
    pub video_type: VideoType,
}

#[derive(Deserialize)]
struct ProbeOutput {
    #[serde(default)]
    streams: Vec<ProbeStream>,
    #[serde(default)]
    format: ProbeFormat,
}

#[derive(Deserialize)]
struct ProbeStream {
    #[serde(default)]
    index: usize,
    #[serde(default)]
    codec_type: String,
    #[serde(default)]
    codec_name: String,
    #[serde(default)]
    width: usize,
    #[serde(default)]
    height: usize,
    #[serde(default)]
    bit_rate: String,
    #[serde(default)]
    r_frame_rate: String,
    #[serde(default)]
    avg_frame_rate: String,
    #[serde(default)]
    pix_fmt: String,
    #[serde(default)]
    channels: usize,
    #[serde(default)]
    sample_rate: String,
    #[serde(default)]
    tags: std::collections::HashMap<String, String>,
}

#[derive(Deserialize, Default)]
struct ProbeFormat {
    #[serde(default)]
    duration: String,
    #[serde(default)]
    size: String,
    #[serde(default)]
    bit_rate: String,
}

pub fn get_gpu_info() -> String {
    let ffmpeg_path = get_actual_ffmpeg_path();
    let mut cmd = std::process::Command::new(&ffmpeg_path);
    cmd.args(["-hide_banner", "-encoders"]);
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x08000000);
    }
    let output = cmd.output();
    match output {
        Ok(o) => {
            let text = String::from_utf8_lossy(&o.stdout);
            let mut gpu_encoders = Vec::new();
            if text.contains("h264_nvenc") { gpu_encoders.push("NVIDIA NVENC (H.264)"); }
            if text.contains("hevc_nvenc") || text.contains("h265_nvenc") { gpu_encoders.push("NVIDIA NVENC (HEVC)"); }
            if text.contains("h264_amf") { gpu_encoders.push("AMD AMF (H.264)"); }
            if text.contains("hevc_amf") { gpu_encoders.push("AMD AMF (HEVC)"); }
            if text.contains("h264_qsv") { gpu_encoders.push("Intel QSV (H.264)"); }
            if text.contains("hevc_qsv") { gpu_encoders.push("Intel QSV (HEVC)"); }
            if gpu_encoders.is_empty() {
                "GPU not detected".to_string()
            } else {
                format!("Available GPUs: {}", gpu_encoders.join(", "))
            }
        }
        Err(_) => "Failed to get GPU info".to_string(),
    }
}

pub fn get_audio_tracks(input_path: &str) -> Vec<AudioTrack> {
    let cmd = vec![
        "ffprobe".to_string(),
        "-v".to_string(), "quiet".to_string(),
        "-print_format".to_string(), "json".to_string(),
        "-show_streams".to_string(),
        input_path.to_string(),
    ];
    let output = match run_ffprobe_json(&cmd) {
        Ok(o) => o,
        Err(_) => return Vec::new(),
    };
    let data: ProbeOutput = match serde_json::from_str(&output) {
        Ok(d) => d,
        Err(_) => return Vec::new(),
    };
    data.streams
        .into_iter()
        .enumerate()
        .filter(|(_, s)| s.codec_type == "audio")
        .map(|(i, s)| AudioTrack {
            index: s.index,
            codec: s.codec_name,
            language: s.tags.get("language").cloned().unwrap_or_else(|| "und".to_string()),
            title: s.tags.get("title").cloned().unwrap_or_else(|| format!("Audio {}", i + 1)),
            channels: s.channels,
            sample_rate: s.sample_rate,
            bit_rate: s.bit_rate,
        })
        .collect()
}

pub fn get_video_info_raw(input_path: &str) -> Result<VideoInfo, String> {
    if !Path::new(input_path).exists() {
        log::error!("File not found: {}", input_path);
        return Err(format!("File not found: {}", input_path));
    }
    let cmd = vec![
        "ffprobe".to_string(),
        "-v".to_string(), "quiet".to_string(),
        "-print_format".to_string(), "json".to_string(),
        "-show_format".to_string(), "-show_streams".to_string(),
        input_path.to_string(),
    ];
    let output = run_ffprobe_json(&cmd).map_err(|e| {
        log::error!("ffprobe failed for {}: {}", input_path, e);
        e
    })?;
    let data: ProbeOutput = serde_json::from_str(&output)
        .map_err(|e| {
            log::error!("Failed to parse ffprobe output for {}: {}", input_path, e);
            format!("Failed to parse ffprobe output: {}", e)
        })?;

    let video_stream = data.streams.iter().find(|s| s.codec_type == "video");
    let audio_streams: Vec<&ProbeStream> = data.streams.iter().filter(|s| s.codec_type == "audio").collect();
    let has_subtitles = data.streams.iter().any(|s| s.codec_type == "subtitle");

    if video_stream.is_none() && audio_streams.is_empty() {
        log::error!("No media streams found in {}", input_path);
        return Err("No media streams found".to_string());
    }

    let duration = data.format.duration.parse::<f64>().unwrap_or(0.0);
    let size_bytes = std::fs::metadata(input_path)
        .map(|m| m.len())
        .unwrap_or_else(|_| data.format.size.parse::<u64>().unwrap_or(0));
    let size_mb = size_bytes as f64 / (1024.0 * 1024.0);

    let (width, height, video_bitrate, fps, needs_vfr_fix, is_hevc, is_10bit, video_codec, pixel_format) =
        if let Some(vs) = video_stream {
            let w = vs.width;
            let h = vs.height;
            let total_bitrate = data.format.bit_rate.parse::<i64>().unwrap_or(0);
            let total_bitrate = if total_bitrate == 0 && duration > 0.0 {
                ((size_bytes as f64 * 8.0) / duration) as i64
            } else {
                total_bitrate
            };
            let mut vb = vs.bit_rate.parse::<i64>().unwrap_or(0);
            if vb == 0 {
                let ab: i64 = audio_streams.iter()
                    .map(|s| s.bit_rate.parse::<i64>().unwrap_or(128000))
                    .sum();
                vb = (total_bitrate - ab).max(0);
            }

            let fps_parts: Vec<&str> = vs.avg_frame_rate.split('/').collect();
            let fps_val = if fps_parts.len() == 2 {
                let num = fps_parts[0].parse::<f64>().unwrap_or(0.0);
                let den = fps_parts[1].parse::<f64>().unwrap_or(1.0);
                if den != 0.0 { num / den } else { 0.0 }
            } else {
                0.0
            };

            let needs_fix = vs.r_frame_rate == "1000/1" || vs.r_frame_rate == "0/0" || vs.avg_frame_rate == "0/0";
            let hevc = ["hevc", "h265"].contains(&vs.codec_name.to_lowercase().as_str());
            let tenbit = vs.pix_fmt.ends_with("10le") || vs.pix_fmt.ends_with("10be");

            (w, h, vb, fps_val, needs_fix, hevc, tenbit, vs.codec_name.clone(), vs.pix_fmt.clone())
        } else {
            (0, 0, 0, 0.0, false, false, false, "unknown".to_string(), "unknown".to_string())
        };

    let audio_bitrate: i64 = audio_streams.iter()
        .map(|s| s.bit_rate.parse::<i64>().unwrap_or(128000))
        .sum();

    Ok(VideoInfo {
        path: input_path.to_string(),
        duration,
        size_mb,
        video_bitrate,
        audio_bitrate,
        width,
        height,
        fps,
        needs_vfr_fix,
        is_hevc,
        is_10bit,
        video_codec,
        pixel_format,
        has_subtitles,
        audio_tracks: get_audio_tracks(input_path),
        gpu_info: get_gpu_info(),
        processing_mode: String::new(),
        complexity_score: 0,
        complexity_desc: String::new(),
        crf_value: None,
        video_type: VideoType::LiveAction,
    })
}
