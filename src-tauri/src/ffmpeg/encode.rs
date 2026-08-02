use std::sync::Arc;
use std::sync::atomic::{AtomicBool, AtomicU32};
use log::{info, warn};

use super::core::{run_command_with_progress, run_command_simple, RunResult};
use super::probe::{get_gpu_info, VideoType};
use crate::config::DEFAULT_FPS_FIX;

fn get_content_type_flags(video_type: &VideoType, codec: &str, use_hardware: bool, has_nvenc: bool) -> Vec<String> {
    let mut flags = Vec::new();

    if use_hardware && has_nvenc {
        return flags;
    }

    match video_type {
        VideoType::Animation => {
            match codec {
                "libx265" => {
                    flags.extend(vec![
                        "-tune".to_string(), "animation".to_string(),
                        "-x265-params".to_string(), "aq-mode=3:bframes=8:psy-rd=1.0".to_string(),
                    ]);
                }
                "libsvtav1" => {
                    flags.extend(vec![
                        "-svtav1-params".to_string(), "tune=0".to_string(),
                    ]);
                }
                "libx264" => {
                    flags.extend(vec![
                        "-tune".to_string(), "animation".to_string(),
                    ]);
                }
                _ => {}
            }
        }
        VideoType::Mixed => {
            // Для 3D (CGI, Mixed) принудительно используем 10-bit цвет, чтобы исключить бандинг
            flags.extend(vec!["-pix_fmt".to_string(), "yuv420p10le".to_string()]);
            match codec {
                "libx265" => {
                    // Используем aq-mode=3 для защиты темных областей и никаких tune=animation
                    flags.extend(vec![
                        "-x265-params".to_string(), "aq-mode=3".to_string(),
                    ]);
                }
                _ => {}
            }
        }
        VideoType::LiveAction => {}
    }

    flags
}

pub fn fix_vfr_target_crf(
    input_path: &str, output_path: &str, output_format: &str, codec: &str, crf_value: i32,
    preset_value: &str, duration_seconds: f64, use_hardware: bool, video_info: &super::probe::VideoInfo,
    video_type: &VideoType,
    cancel_flag: Arc<AtomicBool>, progress_cb: Option<Arc<dyn Fn(i32, String) + Send + Sync>>,
    child_pid: Option<Arc<AtomicU32>>,
) -> RunResult {
    let gpu_info = get_gpu_info();
    let has_nvenc = gpu_info.contains("NVIDIA NVENC");
    let mut cmd = vec!["ffmpeg".to_string(), "-y".to_string()];
    if video_info.is_hevc && has_nvenc {
        cmd.extend(["-hwaccel".to_string(), "cuda".to_string()]);
    }
    cmd.extend(["-i".to_string(), input_path.to_string()]);
    let mut vf_filters = vec![format!("fps={}", DEFAULT_FPS_FIX)];
    
    // Не используем yuv420p для Mixed (потому что мы задаем yuv420p10le в get_content_type_flags)
    if video_info.is_10bit && codec != "libx265" && *video_type != VideoType::Mixed {
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
                cmd.extend(get_content_type_flags(video_type, codec, use_hardware, has_nvenc));
            }
            cmd.extend(["-c:a".to_string(), "copy".to_string()]);
        }
        _ => {
            if use_hardware && has_nvenc {
                cmd.extend(["-c:v".to_string(), "h264_nvenc".to_string(), "-cq".to_string(), crf_value.to_string(), "-preset".to_string(), "p6".to_string(), "-tune".to_string(), "ll".to_string()]);
            } else {
                cmd.extend(["-c:v".to_string(), "libx264".to_string(), "-crf".to_string(), crf_value.to_string(), "-preset".to_string(), preset_value.to_string()]);
                cmd.extend(get_content_type_flags(video_type, codec, use_hardware, has_nvenc));
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
    run_command_with_progress(&cmd, Some(duration_seconds), "VFR-fix+compress", cancel_flag, progress_cb, child_pid)
}

pub fn compress_video_core(
    input_path: &str, output_path: &str, output_format: &str, codec: &str, crf_value: i32,
    preset_value: &str, duration_seconds: f64, video_info: &super::probe::VideoInfo,
    video_type: &VideoType, use_hardware: bool, cancel_flag: Arc<AtomicBool>,
    progress_cb: Option<Arc<dyn Fn(i32, String) + Send + Sync>>,
    child_pid: Option<Arc<AtomicU32>>,
) -> RunResult {
    let gpu_info = get_gpu_info();
    let has_nvenc = gpu_info.contains("NVIDIA NVENC");
    let mut cmd = vec!["ffmpeg".to_string(), "-y".to_string()];
    if video_info.is_hevc && has_nvenc {
        cmd.extend(["-hwaccel".to_string(), "cuda".to_string()]);
    }
    cmd.extend(["-i".to_string(), input_path.to_string()]);
    let mut vf_filters = Vec::new();
    
    if video_info.is_10bit && codec != "libx265" && *video_type != VideoType::Mixed {
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
                cmd.extend(get_content_type_flags(video_type, codec, use_hardware, has_nvenc));
            }
        }
        _ => {
            if use_hardware && has_nvenc {
                cmd.extend(["-c:v".to_string(), "h264_nvenc".to_string(), "-cq".to_string(), crf_value.to_string(), "-preset".to_string(), "p6".to_string(), "-tune".to_string(), "ll".to_string(), "-spatial_aq".to_string(), "1".to_string(), "-temporal_aq".to_string(), "1".to_string(), "-rc-lookahead".to_string(), "20".to_string(), "-aq-strength".to_string(), "15".to_string()]);
            } else {
                cmd.extend(["-c:v".to_string(), "libx264".to_string(), "-crf".to_string(), crf_value.to_string(), "-preset".to_string(), preset_value.to_string()]);
                cmd.extend(get_content_type_flags(video_type, codec, use_hardware, has_nvenc));
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
    run_command_with_progress(&cmd, Some(duration_seconds), "Compress", cancel_flag, progress_cb, child_pid)
}

pub fn compress_video_core_no_subtitles(
    input_path: &str, output_path: &str, output_format: &str, codec: &str, crf_value: i32,
    preset_value: &str, duration_seconds: f64, video_info: &super::probe::VideoInfo,
    video_type: &VideoType, use_hardware: bool, cancel_flag: Arc<AtomicBool>,
    progress_cb: Option<Arc<dyn Fn(i32, String) + Send + Sync>>,
    child_pid: Option<Arc<AtomicU32>>,
) -> RunResult {
    let mut info_clone = video_info.clone();
    info_clone.has_subtitles = false;
    compress_video_core(input_path, output_path, output_format, codec, crf_value, preset_value, duration_seconds, &info_clone, video_type, use_hardware, cancel_flag, progress_cb, child_pid)
}

pub fn compress_video_core_full_map(
    input_path: &str, output_path: &str, _output_format: &str, _codec: &str, crf_value: i32,
    preset_value: &str, duration_seconds: f64,
    cancel_flag: Arc<AtomicBool>,
    progress_cb: Option<Arc<dyn Fn(i32, String) + Send + Sync>>,
    child_pid: Option<Arc<AtomicU32>>,
) -> RunResult {
    let mut cmd = vec!["ffmpeg".to_string(), "-y".to_string(), "-i".to_string(), input_path.to_string()];
    cmd.extend(["-c:v".to_string(), "libx264".to_string(), "-crf".to_string(), crf_value.to_string(), "-preset".to_string(), preset_value.to_string(), "-c:a".to_string(), "aac".to_string(), "-b:a".to_string(), "192k".to_string()]);
    cmd.extend(["-map".to_string(), "0".to_string(), "-map".to_string(), "-0:d".to_string(), "-progress".to_string(), "pipe:1".to_string(), output_path.to_string()]);
    run_command_with_progress(&cmd, Some(duration_seconds), "Compress (fallback)", cancel_flag, progress_cb, child_pid)
}

pub fn encode_chunk(
    input_path: &str, output_path: &str, start_time: f64, duration: f64,
    codec: &str, crf_value: i32, preset_value: &str, use_hardware: bool,
    video_info: &super::probe::VideoInfo, video_type: &VideoType, force_vfr_fix: bool,
    cancel_flag: Arc<AtomicBool>,
) -> RunResult {
    let gpu_info = get_gpu_info();
    let has_nvenc = gpu_info.contains("NVIDIA NVENC");
    
    let fast_seek = (start_time - 10.0).max(0.0);
    let trim_start = start_time - fast_seek;

    let mut cmd = vec![
        "ffmpeg".to_string(), "-y".to_string(), 
        "-ss".to_string(), format!("{:.3}", fast_seek), 
        "-i".to_string(), input_path.to_string(),
    ];
    
    let needs_fix = force_vfr_fix || video_info.needs_vfr_fix;
    
    let mut vf_filters = vec![
        format!("trim=start={:.3}:duration={:.3}", trim_start, duration),
        "setpts=PTS-STARTPTS".to_string()
    ];
    
    if needs_fix {
        vf_filters.push(format!("fps={}", DEFAULT_FPS_FIX));
    }
    if video_info.is_10bit && codec != "libx265" && *video_type != VideoType::Mixed {
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
                cmd.extend(get_content_type_flags(video_type, codec, use_hardware, has_nvenc));
            }
        }
        _ => {
            if use_hardware && has_nvenc {
                cmd.extend(["-c:v".to_string(), "h264_nvenc".to_string(), "-cq".to_string(), crf_value.to_string(), "-preset".to_string(), "p6".to_string(), "-tune".to_string(), "ll".to_string()]);
            } else {
                cmd.extend(["-c:v".to_string(), "libx264".to_string(), "-crf".to_string(), crf_value.to_string(), "-preset".to_string(), preset_value.to_string()]);
                cmd.extend(get_content_type_flags(video_type, codec, use_hardware, has_nvenc));
            }
        }
    }
    
    cmd.extend(["-t".to_string(), duration.to_string(), "-an".to_string(), output_path.to_string()]);
    run_command_simple(&cmd, cancel_flag)
}

pub fn calculate_vmaf(
    original_path: &str, chunk_path: &str, start_time: f64, duration: f64,
    n_subsample: usize, width: usize, video_info: &super::probe::VideoInfo,
    force_vfr_fix: bool, pad_applied: bool, ignore_noise: bool, cancel_flag: Arc<AtomicBool>,
) -> f64 {
    let tmp_dir = std::env::temp_dir();
    let json_filename = format!("vmaf_{}_{}.json", std::process::id(), chrono::Utc::now().timestamp_millis());
    let json_path = tmp_dir.join(&json_filename);
    let json_path_ff = json_path.to_string_lossy().replace('\\', "/").replace(':', "\\:");

    let fast_seek = (start_time - 10.0).max(0.0);
    let trim_start = start_time - fast_seek;

    let needs_fix = force_vfr_fix || video_info.needs_vfr_fix;

    let mut ref_filters = format!("trim=start={:.3}:duration={:.3},setpts=PTS-STARTPTS", trim_start, duration);
    if needs_fix {
        ref_filters.push_str(&format!(",fps={}", crate::config::DEFAULT_FPS_FIX));
    }
    
    if pad_applied {
        ref_filters.push_str(",pad=ceil(iw/2)*2:ceil(ih/2)*2");
    }

    if ignore_noise {
        // Усиленный фильтр для игнора 3D CGI шума в VMAF
        ref_filters.push_str(",hqdn3d=12:9:14:12,gblur=sigma=0.6");
    }

    let scale_filter = if width > 1920 { ",scale=1920:-1:flags=bicubic" } else { "" };
    ref_filters.push_str(scale_filter);

    let mut dist_filters = format!("setpts=PTS-STARTPTS");
    if ignore_noise {
        dist_filters.push_str(",hqdn3d=12:9:14:12,gblur=sigma=0.6");
    }
    dist_filters.push_str(scale_filter);

    let filter_complex = format!(
        "[0:v]{}[ref];[1:v]{}[dist];[dist][ref]libvmaf=model=version=vmaf_v0.6.1neg:log_fmt=json:log_path='{}':n_subsample={}",
        ref_filters, dist_filters, json_path_ff, n_subsample
    );

    let cmd = vec![
        "ffmpeg".to_string(), "-y".to_string(),
        "-ss".to_string(), format!("{:.3}", fast_seek),
        "-i".to_string(), original_path.to_string(),
        "-i".to_string(), chunk_path.to_string(),
        "-filter_complex".to_string(), filter_complex,
        "-f".to_string(), "null".to_string(),
        "-".to_string(),
    ];

    let result = run_command_simple(&cmd, cancel_flag);
    let mut score = -1.0;

    if json_path.exists() {
        if let Ok(content) = std::fs::read_to_string(&json_path) {
            if let Ok(data) = serde_json::from_str::<serde_json::Value>(&content) {
                if let Some(pooled) = data.get("pooled_metrics") {
                    if let Some(vmaf) = pooled.get("vmaf")
                        .and_then(|v| v.get("mean"))
                        .and_then(|v| v.as_f64())
                    {
                        score = vmaf;
                    }
                    if let Some(obj) = pooled.as_object() {
                        let features: Vec<String> = obj.iter()
                            .filter(|(k, _)| *k != "vmaf")
                            .map(|(k, v)| {
                                let mean = v.get("mean")
                                    .and_then(|v| v.as_f64())
                                    .map(|v| format!("{:.4}", v))
                                    .unwrap_or_else(|| "N/A".to_string());
                                format!("{}={}", k, mean)
                            })
                            .collect();
                        info!("VMAF features: vmaf={:.2} | {}", score, features.join(" | "));
                    }
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