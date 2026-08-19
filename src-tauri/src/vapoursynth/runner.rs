use std::io::{BufRead, Read};
use std::process::{Command, Stdio};
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;

use crate::ffmpeg::core::run_command_simple;
use crate::ffmpeg::probe::{get_gpu_info, VideoInfo, VideoType};
use crate::process_control::PidTracker;
use crate::settings::get_actual_ffmpeg_path;
use crate::vapoursynth::script::{generate_denoise_vpy, DenoiseSource};

pub struct DenoiseEncodeResult {
    pub success: bool,
    pub message: String,
}

fn windows_hidden(cmd: &mut Command) {
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x08000000);
    }
}

fn ffmpeg_path() -> String {
    get_actual_ffmpeg_path()
}

fn vspipe_bat() -> std::path::PathBuf {
    crate::vapoursynth::vspipe_bat_path()
}

/// Cores we are willing to hand to denoise work, reserving 2 for the OS/UI so
/// the whole PC stays responsive (no freeze during heavy BM3D denoise).
pub fn denoise_usable_cores() -> usize {
    let cores = std::thread::available_parallelism()
        .map(|n| n.get())
        .unwrap_or(4);
    (cores.saturating_sub(2)).max(1)
}

/// Returns `(segment_count, threads_per_vspipe)` for the segmented denoise,
/// bounded by the user-configurable limits (`denoise_max_threads` /
/// `denoise_max_segments`, 0 = auto). Guarantees total threads ≈ usable cores
/// so RAM and CPU are not oversubscribed.
fn denoise_segment_plan() -> (usize, usize) {
    let settings = crate::settings::load_settings();
    let usable = denoise_usable_cores();
    let per = if settings.denoise_max_threads > 0 {
        settings.denoise_max_threads
    } else {
        2
    };
    let maxseg = if settings.denoise_max_segments > 0 {
        settings.denoise_max_segments
    } else {
        8
    };
    let n = (usable / per).max(2).min(maxseg);
    let vs_threads = if settings.denoise_max_threads > 0 {
        settings.denoise_max_threads
    } else {
        (usable / n).max(1)
    };
    (n, vs_threads)
}

/// Threads to give a single vspipe process when `workers` of them run
/// concurrently (auto-CRF denoise references / chunks).
pub fn denoise_vs_threads_for_workers(workers: usize) -> usize {
    let settings = crate::settings::load_settings();
    if settings.denoise_max_threads > 0 {
        return settings.denoise_max_threads;
    }
    let usable = denoise_usable_cores();
    (usable / workers.max(1)).max(1)
}

/// Video/audio codec arguments (without the input side) for a denoise encode.
fn encode_codec_args(
    codec: &str,
    crf: i32,
    preset: &str,
    use_hardware: bool,
    video_type: &VideoType,
) -> Vec<String> {
    let gpu_info = get_gpu_info();
    let has_nvenc = gpu_info.contains("NVIDIA NVENC");
    let crf_s = crf.to_string();
    let mut v = Vec::new();
    match codec {
        "libvpx-vp9" => {
            if use_hardware && has_nvenc {
                v.extend(["-c:v", "vp9_nvenc", "-crf", &crf_s, "-b:v", "0"]);
            } else {
                v.extend([
                    "-c:v", "libvpx-vp9", "-crf", &crf_s, "-b:v", "0", "-deadline", "good",
                    "-cpu-used", "2",
                ]);
            }
        }
        "libx265" => {
            if use_hardware && has_nvenc {
                v.extend(["-c:v", "hevc_nvenc", "-crf", &crf_s, "-preset", "p6", "-tune", "ll"]);
            } else {
                v.extend(["-c:v", "libx265", "-crf", &crf_s, "-preset", preset]);
                if matches!(video_type, VideoType::Animation) {
                    v.extend(["-x265-params", "aq-mode=3:bframes=8:psy-rd=1.0"]);
                }
            }
        }
        _ => {
            if use_hardware && has_nvenc {
                v.extend([
                    "-c:v", "h264_nvenc", "-cq", &crf_s, "-preset", "p6", "-tune", "ll",
                ]);
            } else {
                v.extend(["-c:v", "libx264", "-crf", &crf_s, "-preset", preset]);
                if matches!(video_type, VideoType::Animation) {
                    v.extend(["-tune", "animation"]);
                }
            }
        }
    }
    v.iter().map(|s| s.to_string()).collect()
}

/// Runs `vspipe -c y4m <vpy> -` piped into `ffmpeg <ffmpeg_args>`, capturing
/// progress from vspipe's stderr. When `slot` is provided, the per-segment
/// completion fraction (0..1) is written there; otherwise `progress_cb` gets a
/// percentage.
fn run_piped(
    vpy_path: &str,
    ffmpeg_args: Vec<String>,
    cancel_flag: Arc<AtomicBool>,
    child_pid: Option<PidTracker>,
    progress_cb: Option<Arc<dyn Fn(i32, String) + Send + Sync>>,
    slot: Option<Arc<Mutex<f64>>>,
    label: &str,
    vs_threads: usize,
    timeout: Option<std::time::Duration>,
) -> DenoiseEncodeResult {
    let vspipe_bat = vspipe_bat();
    if !vspipe_bat.exists() {
        return DenoiseEncodeResult {
            success: false,
            message: "VapourSynth is not installed (vspipe.bat missing)".to_string(),
        };
    }

    let mut vspipe_cmd = Command::new(&vspipe_bat);
    vspipe_cmd.arg("--progress").arg("-c").arg("y4m").arg(vpy_path).arg("-");
    vspipe_cmd.stdout(Stdio::piped()).stderr(Stdio::piped());
    vspipe_cmd.env("OMP_NUM_THREADS", vs_threads.to_string());
    windows_hidden(&mut vspipe_cmd);
    let mut vs_child = match vspipe_cmd.spawn() {
        Ok(c) => c,
        Err(e) => {
            log::error!("Failed to start vspipe: {}", e);
            return DenoiseEncodeResult {
                success: false,
                message: format!("Failed to start vspipe: {}", e),
            };
        }
    };
    if let Err(e) = crate::process_control::set_process_below_normal(vs_child.id()) {
        log::debug!("Failed to lower vspipe priority: {}", e);
    }
    let vs_stdout = match vs_child.stdout.take() {
        Some(s) => s,
        None => {
            let _ = vs_child.kill();
            return DenoiseEncodeResult {
                success: false,
                message: "Failed to capture vspipe stdout".to_string(),
            };
        }
    };
    if let Some(ref tracker) = child_pid {
        tracker.registry().register(vs_child.id());
    }

    let mut ffmpeg_cmd = Command::new(ffmpeg_path());
    ffmpeg_cmd.args(["-hide_banner"]).args(&ffmpeg_args);
    ffmpeg_cmd.stdin(Stdio::from(vs_stdout)).stderr(Stdio::piped());
    windows_hidden(&mut ffmpeg_cmd);
    let mut ff_child = match ffmpeg_cmd.spawn() {
        Ok(c) => c,
        Err(e) => {
            let _ = vs_child.kill();
            log::error!("Failed to start ffmpeg: {}", e);
            return DenoiseEncodeResult {
                success: false,
                message: format!("Failed to start ffmpeg: {}", e),
            };
        }
    };
    if let Err(e) = crate::process_control::set_process_below_normal(ff_child.id()) {
        log::debug!("Failed to lower ffmpeg priority: {}", e);
    }
    if let Some(ref tracker) = child_pid {
        tracker.registry().register(ff_child.id());
    }

    let vs_stderr = match vs_child.stderr.take() {
        Some(s) => s,
        None => {
            let _ = vs_child.kill();
            let _ = ff_child.kill();
            return DenoiseEncodeResult {
                success: false,
                message: "Failed to capture vspipe stderr".to_string(),
            };
        }
    };
    let cb = progress_cb.clone();
    let slot_clone = slot.clone();
    let label_owned = label.to_string();
    let progress_thread = std::thread::spawn(move || {
        let report = |line: &str| {
            let parse = |prefix: &str, is_frame: bool| -> Option<f64> {
                if is_frame {
                    if let Some(rest) = line.strip_prefix(prefix) {
                        let mut parts = rest.trim().split('/');
                        let n_str = parts.next().unwrap_or("").trim();
                        let m_str = parts.next().unwrap_or("").trim();
                        let m_str = m_str.split_whitespace().next().unwrap_or("").trim();
                        if let (Ok(n), Ok(m)) = (n_str.parse::<u64>(), m_str.parse::<u64>()) {
                            if m > 0 {
                                return Some((n as f64 / m as f64).clamp(0.0, 1.0));
                            }
                        }
                    }
                } else if let Some(rest) = line.strip_prefix(prefix) {
                    let num_str = rest.trim().trim_end_matches('%');
                    if let Ok(n) = num_str.parse::<f64>() {
                        return Some((n / 100.0).clamp(0.0, 1.0));
                    }
                }
                None
            };
            let frac = parse("Frame:", true).or_else(|| parse("Progress:", false));
            if let Some(frac) = frac {
                if let Some(slot) = &slot_clone {
                    if let Ok(mut g) = slot.lock() {
                        *g = frac;
                    }
                } else if let Some(cb) = &cb {
                    cb((frac * 100.0) as i32, label_owned.clone());
                }
            }
        };
        let mut reader = std::io::BufReader::new(vs_stderr);
        let mut pending: Vec<u8> = Vec::new();
        let mut error_lines = Vec::new();
        let mut buf = [0u8; 4096];
        loop {
            let n = match reader.read(&mut buf) {
                Ok(0) => break,
                Ok(n) => n,
                Err(_) => break,
            };
            pending.extend_from_slice(&buf[..n]);
            while let Some(pos) = pending.iter().position(|&b| b == b'\r' || b == b'\n') {
                let line: Vec<u8> = pending.drain(..pos).collect();
                pending.drain(..1);
                let line = String::from_utf8_lossy(&line).trim().to_string();
                if line.is_empty() {
                    continue;
                }
                if line.starts_with("Frame:") || line.starts_with("Progress:") {
                    report(&line);
                } else {
                    let lower = line.to_lowercase();
                    if ["error", "traceback", "failed", "exception", "cannot", "unable"]
                        .iter()
                        .any(|k| lower.contains(k))
                    {
                        error_lines.push(line.clone());
                    }
                }
            }
        }
        error_lines
    });

    let ff_stderr = match ff_child.stderr.take() {
        Some(s) => s,
        None => {
            let _ = vs_child.kill();
            let _ = ff_child.kill();
            return DenoiseEncodeResult {
                success: false,
                message: "Failed to capture ffmpeg stderr".to_string(),
            };
        }
    };
    let stderr_thread = std::thread::spawn(move || {
        let reader = std::io::BufReader::new(ff_stderr);
        let mut error_lines = Vec::new();
        for line in reader.lines() {
            if let Ok(line) = line {
                let lower = line.to_lowercase();
                if ["error", "failed", "invalid", "cannot", "unable"]
                    .iter()
                    .any(|k| lower.contains(k))
                {
                    error_lines.push(line.trim().to_string());
                }
            }
        }
        error_lines
    });

    let mut cancelled = false;
    let mut timed_out = false;
    let started = std::time::Instant::now();
    loop {
        if cancel_flag.load(Ordering::Relaxed) {
            let _ = vs_child.kill();
            let _ = ff_child.kill();
            cancelled = true;
            break;
        }
        if let Some(t) = timeout {
            if started.elapsed() > t {
                log::warn!(
                    "run_piped timed out after {:.1}s (label={})",
                    started.elapsed().as_secs_f64(),
                    label
                );
                let _ = vs_child.kill();
                let _ = ff_child.kill();
                timed_out = true;
                break;
            }
        }
        match vs_child.try_wait() {
            Ok(Some(_)) => break,
            Ok(None) => std::thread::sleep(std::time::Duration::from_millis(150)),
            Err(e) => {
                let _ = ff_child.kill();
                log::error!("Failed to wait for vspipe: {}", e);
                return DenoiseEncodeResult {
                    success: false,
                    message: format!("Failed to wait for vspipe: {}", e),
                };
            }
        }
    }

    if let Some(ref tracker) = child_pid {
        tracker.registry().unregister(vs_child.id());
        tracker.registry().unregister(ff_child.id());
    }

    if cancelled {
        return DenoiseEncodeResult {
            success: false,
            message: "Operation cancelled".to_string(),
        };
    }

    if timed_out {
        let secs = started.elapsed().as_secs_f64();
        return DenoiseEncodeResult {
            success: false,
            message: format!("VapourSynth pipeline timed out after {:.0} seconds", secs),
        };
    }

    let _ = vs_child.wait();
    let mut vs_errors = progress_thread.join().unwrap_or_default();
    let ff_status = ff_child.wait();
    let mut ff_errors = stderr_thread.join().unwrap_or_default();
    vs_errors.reverse();

    match ff_status {
        Ok(code) if code.success() => DenoiseEncodeResult {
            success: true,
            message: "Denoise encode completed successfully".to_string(),
        },
        Ok(_) => {
            ff_errors.reverse();
            let detail: Vec<String> = if !vs_errors.is_empty() {
                vs_errors.into_iter().take(10).collect()
            } else {
                ff_errors.into_iter().take(10).collect()
            };
            DenoiseEncodeResult {
                success: false,
                message: format!(
                    "Denoise encode failed.{}",
                    if detail.is_empty() {
                        String::new()
                    } else {
                        format!("\n{}", detail.join("\n"))
                    }
                ),
            }
        }
        Err(e) => DenoiseEncodeResult {
            success: false,
            message: format!("Failed to wait for ffmpeg: {}", e),
        },
    }
}

/// Single-pipe denoise + compress: `vspipe` feeds `ffmpeg` directly, so there is
/// no intermediate file on disk. Audio (and optional subtitles) are muxed from
/// the original.
#[allow(clippy::too_many_arguments)]
pub fn run_denoise_encode_single(
    vpy_path: &str,
    audio_input: &str,
    output_path: &str,
    output_format: &str,
    codec: &str,
    crf: i32,
    preset: &str,
    use_hardware: bool,
    video_info: &VideoInfo,
    video_type: &crate::ffmpeg::probe::VideoType,
    cancel_flag: Arc<AtomicBool>,
    progress_cb: Option<Arc<dyn Fn(i32, String) + Send + Sync>>,
    child_pid: Option<PidTracker>,
    vs_threads: usize,
) -> DenoiseEncodeResult {
    log::info!("Denoising + compressing (single pipe) -> {}", output_path);
    let include_subs =
        crate::vapoursynth::setup::subtitles_compatible(audio_input) && video_info.has_subtitles;
    let subs_codec = if output_format == "mp4" { "mov_text" } else { "copy" };

    let mut args: Vec<String> = vec![
        "-f".to_string(),
        "yuv4mpegpipe".to_string(),
        "-i".to_string(),
        "-".to_string(),
        "-i".to_string(),
        audio_input.to_string(),
        "-map".to_string(),
        "0:v".to_string(),
        "-map".to_string(),
        "1:a?".to_string(),
    ];
    if include_subs {
        args.extend(["-map".to_string(), "1:s?".to_string()]);
    }
    args.extend(encode_codec_args(codec, crf, preset, use_hardware, video_type));
    args.extend(["-c:a".to_string(), "copy".to_string()]);
    if include_subs {
        args.extend(["-c:s".to_string(), subs_codec.to_string()]);
    }
    if output_format == "mp4" {
        args.extend(["-movflags".to_string(), "+faststart".to_string()]);
    }
    args.extend(["-y".to_string(), output_path.to_string()]);

    run_piped(vpy_path, args, cancel_flag, child_pid, progress_cb, None, "Denoising", vs_threads, None)
}

/// Segmented parallel denoise + compress: the file is split into N frame ranges,
/// each processed by its own `vspipe|ffmpeg` pipeline concurrently. The number of
/// segments and threads-per-process are bounded by `denoise_segment_plan()` (driven
/// by the user-configurable `denoise_max_segments` / `denoise_max_threads` limits,
/// with safe auto defaults) so the whole PC stays responsive and RAM is bounded.
#[allow(clippy::too_many_arguments)]
pub fn run_denoise_encode_segmented(
    input_path: &str,
    output_path: &str,
    output_format: &str,
    codec: &str,
    crf: i32,
    preset: &str,
    use_hardware: bool,
    video_info: &VideoInfo,
    video_type: &VideoType,
    sigma: f64,
    cancel_flag: Arc<AtomicBool>,
    progress_cb: Option<Arc<dyn Fn(i32, String) + Send + Sync>>,
    child_pid: Option<PidTracker>,
) -> DenoiseEncodeResult {
    let fps = video_info.fps;
    let duration = video_info.duration;
    if fps <= 0.0 || duration <= 0.0 {
        return DenoiseEncodeResult {
            success: false,
            message: "Invalid duration/fps for segmented denoise".to_string(),
        };
    }
    let (n, vs_threads) = denoise_segment_plan();
    let threads_per = vs_threads;
    let total_frames = (duration * fps).round().max(1.0) as u64;
    log::info!(
        "Denoising + compressing (segmented, {} segments, {} threads/segment) -> {}",
        n, vs_threads, output_path
    );

    let temp_dir = std::env::temp_dir();
    let pid = std::process::id();
    let mut specs: Vec<(u64, u64, std::path::PathBuf, std::path::PathBuf)> = Vec::new();
    for i in 0..n {
        let f0 = ((duration * (i as f64) / n as f64) * fps).round().max(0.0) as u64;
        let f1 = ((duration * ((i + 1) as f64) / n as f64) * fps)
            .round()
            .min(total_frames as f64) as u64;
        if f1 <= f0 {
            continue;
        }
        let vpy = temp_dir.join(format!("denoise_seg_{}_{}.vpy", pid, i));
        let out = temp_dir.join(format!("denoise_seg_{}_{}.{}", pid, i, output_format));
        specs.push((f0, f1 - 1, vpy, out));
    }
    if specs.is_empty() {
        return DenoiseEncodeResult {
            success: false,
            message: "No segments generated".to_string(),
        };
    }

    for (f0, f1, vpy, _out) in &specs {
        let script = generate_denoise_vpy(
            input_path,
            fps,
            sigma,
            DenoiseSource::Lsmash,
            Some((*f0, *f1)),
            true,
            vs_threads,
        );
        if let Err(e) = std::fs::write(vpy, script) {
            cleanup_segmented(&specs);
            return DenoiseEncodeResult {
                success: false,
                message: format!("Failed to write segment vpy: {}", e),
            };
        }
    }

    let slots: Vec<Arc<Mutex<f64>>> = (0..specs.len()).map(|_| Arc::new(Mutex::new(0.0))).collect();
    let progress_slots: Arc<Vec<Arc<Mutex<f64>>>> = Arc::new(slots);

    let results: Vec<Result<(), String>> = std::thread::scope(|s| {
        let mut handles = Vec::new();
        for (i, (f0, f1, vpy, out)) in specs.iter().enumerate() {
            let slot = progress_slots[i].clone();
            let cancel = cancel_flag.clone();
            let cpid = child_pid.clone();
            let vpy_s = vpy.to_string_lossy().to_string();
            let out_s = out.to_string_lossy().to_string();
            let codec = codec.to_string();
            let preset = preset.to_string();
            let out_fmt = output_format.to_string();
            let vi = video_info.clone();
            let vt = video_type.clone();
            handles.push(s.spawn(move || {
                let mut args: Vec<String> = vec![
                    "-f".to_string(),
                    "yuv4mpegpipe".to_string(),
                    "-i".to_string(),
                    "-".to_string(),
                    "-an".to_string(),
                    "-threads".to_string(),
                    threads_per.to_string(),
                ];
                args.extend(encode_codec_args(&codec, crf, &preset, use_hardware, &vt));
                args.extend(["-y".to_string(), out_s.clone()]);
                let res = run_piped(
                    &vpy_s,
                    args,
                    cancel,
                    cpid,
                    None,
                    Some(slot),
                    "seg",
                    vs_threads,
                    None,
                );
                if res.success { Ok(()) } else { Err(res.message) }
            }));
            let _ = (f0, f1);
        }
        let mut out_res = Vec::new();
        loop {
            if cancel_flag.load(Ordering::Relaxed) {
                break;
            }
            let finished = handles.iter().filter(|h| h.is_finished()).count();
            let sum: f64 = progress_slots
                .iter()
                .map(|m| m.lock().map(|g| *g).unwrap_or(0.0))
                .sum();
            let pct = ((sum / specs.len() as f64) * 100.0) as i32;
            if let Some(cb) = &progress_cb {
                cb(pct, format!("Denoising segments {}/{}", finished, specs.len()));
            }
            if finished == handles.len() {
                break;
            }
            std::thread::sleep(std::time::Duration::from_millis(150));
        }
        for h in handles {
            match h.join() {
                Ok(r) => out_res.push(r),
                Err(_) => out_res.push(Err("segment panicked".to_string())),
            }
        }
        out_res
    });

    let failures: Vec<String> = results.into_iter().filter_map(|r| r.err()).collect();
    if !failures.is_empty() {
        cleanup_segmented(&specs);
        return DenoiseEncodeResult {
            success: false,
            message: format!("Segmented denoise failed:\n{}", failures.join("\n")),
        };
    }

    let list_path = temp_dir.join(format!("denoise_concat_{}.txt", pid));
    let list_content: String = specs
        .iter()
        .map(|(_, _, _, out)| format!("file '{}'", out.to_string_lossy().replace('\\', "/")))
        .collect::<Vec<_>>()
        .join("\n");
    if let Err(e) = std::fs::write(&list_path, list_content) {
        cleanup_segmented(&specs);
        return DenoiseEncodeResult {
            success: false,
            message: format!("Failed to write concat list: {}", e),
        };
    }

    let include_subs =
        crate::vapoursynth::setup::subtitles_compatible(input_path) && video_info.has_subtitles;
    let mut concat_args: Vec<String> = vec![
        "ffmpeg".to_string(),
        "-f".to_string(),
        "concat".to_string(),
        "-safe".to_string(),
        "0".to_string(),
        "-i".to_string(),
        list_path.to_string_lossy().to_string(),
        "-i".to_string(),
        input_path.to_string(),
        "-map".to_string(),
        "0:v".to_string(),
        "-map".to_string(),
        "1:a?".to_string(),
    ];
    if include_subs {
        concat_args.extend(["-map".to_string(), "1:s?".to_string()]);
    }
    concat_args.extend(["-c:v".to_string(), "copy".to_string(), "-c:a".to_string(), "copy".to_string()]);
    if include_subs {
        concat_args.extend(["-c:s".to_string(), "copy".to_string()]);
    }
    concat_args.extend(["-y".to_string(), output_path.to_string()]);

    let concat_res = run_command_simple(&concat_args, cancel_flag.clone(), child_pid.clone());
    cleanup_segmented(&specs);
    let _ = std::fs::remove_file(&list_path);

    if !concat_res.success {
        return DenoiseEncodeResult {
            success: false,
            message: format!("Concat failed: {}", concat_res.message),
        };
    }
    DenoiseEncodeResult {
        success: true,
        message: "Segmented denoise encode completed".to_string(),
    }
}

fn cleanup_segmented(specs: &[(u64, u64, std::path::PathBuf, std::path::PathBuf)]) {
    for (_f0, _f1, vpy, out) in specs {
        let _ = std::fs::remove_file(vpy);
        let _ = std::fs::remove_file(out);
    }
}

/// Generates a denoised reference clip (lossless FFV1) for a (trimmed) vpy, used
/// as the VMAF/SSIM reference in denoise-aware auto-CRF.
///
/// A 5-minute timeout guards against hangs (e.g. a missing plugin stalling
/// vspipe for minutes before failing); legitimate reference builds for a 2s
/// chunk finish far below that.
pub fn generate_denoised_reference(
    vpy_path: &str,
    ref_path: &str,
    cancel_flag: Arc<AtomicBool>,
    child_pid: Option<PidTracker>,
    vs_threads: usize,
) -> DenoiseEncodeResult {
    let args: Vec<String> = vec![
        "-f".to_string(),
        "yuv4mpegpipe".to_string(),
        "-i".to_string(),
        "-".to_string(),
        "-an".to_string(),
        "-c:v".to_string(),
        "ffv1".to_string(),
        "-y".to_string(),
        ref_path.to_string(),
    ];
    run_piped(
        vpy_path,
        args,
        cancel_flag,
        child_pid,
        None,
        None,
        "ref",
        vs_threads,
        Some(std::time::Duration::from_secs(300)),
    )
}

/// Encodes an already-denoised lossless reference (FFV1) clip at a candidate
/// CRF for auto-CRF grading. The denoise result is CRF-independent, so running
/// the VapourSynth BM3D pass again for every candidate would be pure waste —
/// encoding the lossless reference produces the identical pixel stream far
/// faster (denoise runs exactly once per chunk, when the reference is built).
#[allow(clippy::too_many_arguments)]
pub fn run_encode_from_ref(
    ref_path: &str,
    out_path: &str,
    codec: &str,
    crf: i32,
    preset: &str,
    use_hardware: bool,
    video_type: &VideoType,
    threads: usize,
    cancel_flag: Arc<AtomicBool>,
    child_pid: Option<PidTracker>,
) -> DenoiseEncodeResult {
    let mut args: Vec<String> = vec![
        "ffmpeg".to_string(),
        "-y".to_string(),
        "-i".to_string(),
        ref_path.to_string(),
        "-an".to_string(),
        "-threads".to_string(),
        threads.max(1).to_string(),
    ];
    args.extend(encode_codec_args(codec, crf, preset, use_hardware, video_type));
    args.extend(["-y".to_string(), out_path.to_string()]);
    let res = crate::ffmpeg::core::run_command_simple(&args, cancel_flag, child_pid);
    if res.success {
        DenoiseEncodeResult { success: true, message: "Reference encode completed".to_string() }
    } else {
        DenoiseEncodeResult { success: false, message: res.message }
    }
}
