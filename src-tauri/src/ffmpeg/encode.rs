use std::sync::Arc;
use std::sync::atomic::AtomicBool;
use log::warn;

use super::core::{run_command_with_progress, run_command_simple, RunResult};
use super::probe::get_gpu_info;
use crate::config::DEFAULT_FPS_FIX;

pub fn fix_vfr_target_crf(
    input_path: &str, output_path: &str, output_format: &str, codec: &str, crf_value: i32,
    preset_value: &str, duration_seconds: f64, use_hardware: bool, video_info: &super::probe::VideoInfo,
    cancel_flag: Arc<AtomicBool>, progress_cb: Option<Arc<dyn Fn(i32, String) + Send + Sync>>,
) -> RunResult {
    let gpu_info = get_gpu_info();
    let has_nvenc = gpu_info.contains("NVIDIA NVENC");
    let mut cmd = vec!["ffmpeg".to_string(), "-y".to_string()];
    if video_info.is_hevc && has_nvenc {
        cmd.extend(["-hwaccel".to_string(), "cuda".to_string()]);
    }
    cmd.extend(["-i".to_string(), input_path.to_string()]);
    let mut vf_filters = vec![format!("fps={}", DEFAULT_FPS_FIX)];
    if video_info.is_10bit && codec != "libx265" {
        vf_filters.push("format=yuv420p".to_string());
    }
    cmd.extend(["-vf".to_string(), vf_filters.join(",")]);
    match codec {
        "libvpx-vp9" => {
            if use_hardware && has_nvenc {
                cmd.extend(["-c:v".to_string(), "vp9_nvenc".to_string(), "-crf".to_string(), crf_value.to_string(), "-b:v".to_string(), "0".to_string()]);
            } else {
                cmd.extend(["-c:v".to_string(), "libvpx-vp9".to_string(), "-crf".to_string(), crf_value.to_string(), "-b:v".to_string(), "0".to_string(), "-deadline".to_string(), "good".to_string(), "-cpu-used".to_string(), "2".to_string()]);
            }
            cmd.extend(["-c:a".to_string(), "copy".to_string()]);
        }
        "libx265" => {
            if use_hardware && has_nvenc {
                cmd.extend(["-c:v".to_string(), "hevc_nvenc".to_string(), "-crf".to_string(), crf_value.to_string(), "-preset".to_string(), "p6".to_string(), "-tune".to_string(), "ll".to_string()]);
            } else {
                cmd.extend(["-c:v".to_string(), "libx265".to_string(), "-crf".to_string(), crf_value.to_string(), "-preset".to_string(), preset_value.to_string()]);
            }
            cmd.extend(["-c:a".to_string(), "copy".to_string()]);
        }
        _ => {
            if use_hardware && has_nvenc {
                cmd.extend(["-c:v".to_string(), "h264_nvenc".to_string(), "-cq".to_string(), crf_value.to_string(), "-preset".to_string(), "p6".to_string(), "-tune".to_string(), "ll".to_string()]);
            } else {
                cmd.extend(["-c:v".to_string(), "libx264".to_string(), "-crf".to_string(), crf_value.to_string(), "-preset".to_string(), preset_value.to_string()]);
            }
            cmd.extend(["-c:a".to_string(), "copy".to_string()]);
        }
    }
    if video_info.has_subtitles {
        if output_format == "mp4" {
            cmd.extend(["-c:s".to_string(), "mov_text".to_string()]);
        } else {
            cmd.extend(["-c:s".to_string(), "copy".to_string()]);
        }
        cmd.extend(["-map".to_string(), "0:V".to_string(), "-map".to_string(), "0:a".to_string(), "-map".to_string(), "0:s".to_string()]);
    } else {
        cmd.extend(["-map".to_string(), "0:V".to_string(), "-map".to_string(), "0:a".to_string()]);
    }
    if output_format == "mp4" {
        cmd.extend(["-movflags".to_string(), "+faststart".to_string()]);
    }
    cmd.extend(["-progress".to_string(), "pipe:1".to_string(), output_path.to_string()]);
    run_command_with_progress(&cmd, Some(duration_seconds), "VFR-fix+compress", cancel_flag, progress_cb)
}

pub fn compress_video_core(
    input_path: &str, output_path: &str, output_format: &str, codec: &str, crf_value: i32,
    preset_value: &str, duration_seconds: f64, video_info: &super::probe::VideoInfo,
    use_hardware: bool, cancel_flag: Arc<AtomicBool>,
    progress_cb: Option<Arc<dyn Fn(i32, String) + Send + Sync>>,
) -> RunResult {
    let gpu_info = get_gpu_info();
    let has_nvenc = gpu_info.contains("NVIDIA NVENC");
    let mut cmd = vec!["ffmpeg".to_string(), "-y".to_string()];
    if video_info.is_hevc && has_nvenc {
        cmd.extend(["-hwaccel".to_string(), "cuda".to_string()]);
    }
    cmd.extend(["-i".to_string(), input_path.to_string()]);
    let mut vf_filters = Vec::new();
    if video_info.is_10bit && codec != "libx265" {
        vf_filters.push("format=yuv420p".to_string());
    }
    if codec == "libx264" && !use_hardware {
        vf_filters.push("pad=ceil(iw/2)*2:ceil(ih/2)*2".to_string());
    }
    if !vf_filters.is_empty() {
        cmd.extend(["-vf".to_string(), vf_filters.join(",")]);
    }
    match codec {
        "libvpx-vp9" => {
            if use_hardware && has_nvenc {
                cmd.extend(["-c:v".to_string(), "vp9_nvenc".to_string(), "-crf".to_string(), crf_value.to_string(), "-b:v".to_string(), "0".to_string()]);
            } else {
                cmd.extend(["-c:v".to_string(), "libvpx-vp9".to_string(), "-crf".to_string(), crf_value.to_string(), "-b:v".to_string(), "0".to_string(), "-deadline".to_string(), "good".to_string(), "-cpu-used".to_string(), "2".to_string()]);
            }
        }
        "libx265" => {
            if use_hardware && has_nvenc {
                cmd.extend(["-c:v".to_string(), "hevc_nvenc".to_string(), "-crf".to_string(), crf_value.to_string(), "-preset".to_string(), "p6".to_string(), "-tune".to_string(), "ll".to_string()]);
            } else {
                cmd.extend(["-c:v".to_string(), "libx265".to_string(), "-crf".to_string(), crf_value.to_string(), "-preset".to_string(), preset_value.to_string()]);
            }
        }
        _ => {
            if use_hardware && has_nvenc {
                cmd.extend(["-c:v".to_string(), "h264_nvenc".to_string(), "-cq".to_string(), crf_value.to_string(), "-preset".to_string(), "p6".to_string(), "-tune".to_string(), "ll".to_string(), "-spatial_aq".to_string(), "1".to_string(), "-temporal_aq".to_string(), "1".to_string(), "-rc-lookahead".to_string(), "20".to_string(), "-aq-strength".to_string(), "15".to_string()]);
            } else {
                cmd.extend(["-c:v".to_string(), "libx264".to_string(), "-crf".to_string(), crf_value.to_string(), "-preset".to_string(), preset_value.to_string()]);
            }
        }
    }
    cmd.extend(["-c:a".to_string(), "aac".to_string(), "-b:a".to_string(), "192k".to_string()]);
    if video_info.has_subtitles {
        if output_format == "mp4" {
            cmd.extend(["-c:s".to_string(), "mov_text".to_string()]);
        } else {
            cmd.extend(["-c:s".to_string(), "copy".to_string()]);
        }
        cmd.extend(["-map".to_string(), "0:V".to_string(), "-map".to_string(), "0:a".to_string(), "-map".to_string(), "0:s".to_string()]);
    } else {
        cmd.extend(["-map".to_string(), "0:V".to_string(), "-map".to_string(), "0:a".to_string()]);
    }
    if output_format == "mp4" {
        cmd.extend(["-movflags".to_string(), "+faststart".to_string()]);
    }
    cmd.extend(["-progress".to_string(), "pipe:1".to_string(), output_path.to_string()]);
    run_command_with_progress(&cmd, Some(duration_seconds), "Compress", cancel_flag, progress_cb)
}

pub fn compress_video_core_no_subtitles(
    input_path: &str, output_path: &str, output_format: &str, codec: &str, crf_value: i32,
    preset_value: &str, duration_seconds: f64, video_info: &super::probe::VideoInfo,
    use_hardware: bool, cancel_flag: Arc<AtomicBool>,
    progress_cb: Option<Arc<dyn Fn(i32, String) + Send + Sync>>,
) -> RunResult {
    let mut info_clone = video_info.clone();
    info_clone.has_subtitles = false;
    compress_video_core(input_path, output_path, output_format, codec, crf_value, preset_value, duration_seconds, &info_clone, use_hardware, cancel_flag, progress_cb)
}

pub fn compress_video_core_full_map(
    input_path: &str, output_path: &str, _output_format: &str, _codec: &str, crf_value: i32,
    preset_value: &str, duration_seconds: f64,
    cancel_flag: Arc<AtomicBool>,
    progress_cb: Option<Arc<dyn Fn(i32, String) + Send + Sync>>,
) -> RunResult {
    let mut cmd = vec!["ffmpeg".to_string(), "-y".to_string(), "-i".to_string(), input_path.to_string()];
    cmd.extend(["-c:v".to_string(), "libx264".to_string(), "-crf".to_string(), crf_value.to_string(), "-preset".to_string(), preset_value.to_string(), "-c:a".to_string(), "aac".to_string(), "-b:a".to_string(), "192k".to_string()]);
    cmd.extend(["-map".to_string(), "0".to_string(), "-map".to_string(), "-0:d".to_string(), "-progress".to_string(), "pipe:1".to_string(), output_path.to_string()]);
    run_command_with_progress(&cmd, Some(duration_seconds), "Compress (fallback)", cancel_flag, progress_cb)
}

pub fn encode_chunk(
    input_path: &str, output_path: &str, start_time: f64, duration: f64,
    codec: &str, crf_value: i32, preset_value: &str, use_hardware: bool,
    video_info: &super::probe::VideoInfo, force_vfr_fix: bool,
    cancel_flag: Arc<AtomicBool>,
) -> RunResult {
    let gpu_info = get_gpu_info();
    let has_nvenc = gpu_info.contains("NVIDIA NVENC");
    let mut cmd = vec!["ffmpeg".to_string(), "-y".to_string(), "-ss".to_string(), start_time.to_string(), "-i".to_string(), input_path.to_string(), "-t".to_string(), duration.to_string()];
    let needs_fix = force_vfr_fix || video_info.needs_vfr_fix;
    let mut vf_filters = Vec::new();
    if needs_fix {
        vf_filters.push(format!("fps={}", DEFAULT_FPS_FIX));
    }
    if video_info.is_10bit && codec != "libx265" {
        vf_filters.push("format=yuv420p".to_string());
    }
    if codec == "libx264" && !use_hardware && !needs_fix {
        vf_filters.push("pad=ceil(iw/2)*2:ceil(ih/2)*2".to_string());
    }
    if !vf_filters.is_empty() {
        cmd.extend(["-vf".to_string(), vf_filters.join(",")]);
    }
    match codec {
        "libvpx-vp9" => {
            if use_hardware && has_nvenc {
                cmd.extend(["-c:v".to_string(), "vp9_nvenc".to_string(), "-crf".to_string(), crf_value.to_string(), "-b:v".to_string(), "0".to_string()]);
            } else {
                cmd.extend(["-c:v".to_string(), "libvpx-vp9".to_string(), "-crf".to_string(), crf_value.to_string(), "-b:v".to_string(), "0".to_string(), "-deadline".to_string(), "good".to_string(), "-cpu-used".to_string(), "2".to_string()]);
            }
        }
        "libx265" => {
            if use_hardware && has_nvenc {
                cmd.extend(["-c:v".to_string(), "hevc_nvenc".to_string(), "-crf".to_string(), crf_value.to_string(), "-preset".to_string(), "p6".to_string(), "-tune".to_string(), "ll".to_string()]);
            } else {
                cmd.extend(["-c:v".to_string(), "libx265".to_string(), "-crf".to_string(), crf_value.to_string(), "-preset".to_string(), preset_value.to_string()]);
            }
        }
        _ => {
            if use_hardware && has_nvenc {
                cmd.extend(["-c:v".to_string(), "h264_nvenc".to_string(), "-cq".to_string(), crf_value.to_string(), "-preset".to_string(), "p6".to_string(), "-tune".to_string(), "ll".to_string()]);
            } else {
                cmd.extend(["-c:v".to_string(), "libx264".to_string(), "-crf".to_string(), crf_value.to_string(), "-preset".to_string(), preset_value.to_string()]);
            }
        }
    }
    cmd.extend(["-c:a".to_string(), "aac".to_string(), "-b:a".to_string(), "192k".to_string(), output_path.to_string()]);
    run_command_simple(&cmd, cancel_flag)
}

pub fn calculate_vmaf(
    original_path: &str, chunk_path: &str, start_time: f64, duration: f64,
    n_subsample: usize, width: usize, video_info: &super::probe::VideoInfo,
    force_vfr_fix: bool, cancel_flag: Arc<AtomicBool>,
) -> f64 {
    let tmp_dir = std::env::temp_dir();
    let json_filename = format!("vmaf_{}_{}.json", std::process::id(), chrono::Utc::now().timestamp_millis());
    let json_path = tmp_dir.join(&json_filename);
    let json_path_ff = json_path.to_string_lossy().replace('\\', "/").replace(':', "\\:");

    let scale_filter = if width > 1920 { ",scale=1920:-1:flags=bicubic" } else { "" };
    let needs_fix = force_vfr_fix || video_info.needs_vfr_fix;
    let target_fps = if needs_fix { DEFAULT_FPS_FIX } else { video_info.fps.max(30.0) };

    let filter_complex = format!(
        "[0:v]fps={},setpts=PTS-STARTPTS,format=yuv420p{}[ref];\
         [1:v]fps={},setpts=PTS-STARTPTS,format=yuv420p{}[dist];\
         [dist][ref]libvmaf=model=version=vmaf_v0.6.1neg:log_fmt=json:log_path='{}':n_subsample={}",
        target_fps, scale_filter, target_fps, scale_filter, json_path_ff, n_subsample
    );

    let mut cmd = vec![
        "ffmpeg".to_string(), "-y".to_string(),
        "-ss".to_string(), start_time.to_string(),
        "-t".to_string(), duration.to_string(),
        "-i".to_string(), original_path.to_string(),
        "-i".to_string(), chunk_path.to_string(),
        "-filter_complex".to_string(), filter_complex,
        "-f".to_string(), "null".to_string(),
        "-".to_string(),
    ];

    let result = run_command_simple(&mut cmd, cancel_flag);
    let mut score = -1.0;

    if json_path.exists() {
        if let Ok(content) = std::fs::read_to_string(&json_path) {
            if let Ok(data) = serde_json::from_str::<serde_json::Value>(&content) {
                if let Some(vmaf) = data.get("pooled_metrics")
                    .and_then(|m| m.get("vmaf"))
                    .and_then(|v| v.get("mean"))
                    .and_then(|v| v.as_f64())
                {
                    score = vmaf;
                }
            }
        }
        if let Err(e) = std::fs::remove_file(&json_path) {
            warn!("Failed to remove VMAF json {:?}: {}", json_path, e);
        }
    }

    if score == -1.0 && !result.success {
        if result.message.contains("No such filter: 'libvmaf'") {
            return -2.0;
        }
    }
    score
}
