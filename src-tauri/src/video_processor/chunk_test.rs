use std::sync::Arc;
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};

use log::{warn, info, error};
use crate::config::get_codecs;
use crate::estimator::format_duration;
use crate::ffmpeg::encode::encode_chunk;
use crate::ffmpeg::probe::VideoType;
use crate::process_control::PidTracker;
use crate::video_processor::compress::get_full_video_info;
use crate::video_processor::parallel_chunks::{
    effective_workers, grade_chunk, log_worker_panic, run_parallel, StepChunkOutcome, test_chunk,
};
use crate::video_processor::quality_check;
use crate::vapoursynth::denoise::DenoiseSpec;
use crate::vapoursynth::runner::{generate_denoised_reference, run_encode_from_ref};
use crate::vapoursynth::script::{generate_denoise_vpy, DenoiseSource};

pub struct AutoCrfResult {
    pub crf: Option<i32>,
    pub best_crf: Option<i32>,
    pub best_vmaf: f64,
    pub cancelled: bool,
    pub metric_error: Option<String>,
}

/// Builds, per timestamp, a denoised reference clip (lossless FFV1) from a
/// trimmed vpy. These references are reused across every CRF candidate during
/// the search: candidate encodes read the reference directly
/// (`run_encode_from_ref`), so the expensive BM3D denoise runs exactly once per
/// chunk, not once per CRF candidate.
///
/// The references are built in parallel with `workers` vspipe processes, each
/// given `vs_threads` threads, so the one-time build is as fast as possible.
fn build_denoise_references(
    denoise: &DenoiseSpec,
    timestamps: &[f64],
    chunk_duration: f64,
    cancel: Arc<AtomicBool>,
    child_pid: Option<PidTracker>,
    workers: usize,
    vs_threads: usize,
) -> Vec<Option<String>> {
    let fps = denoise.fps;
    let temp_dir = std::env::temp_dir();
    let pid = std::process::id();
    let slots: Arc<std::sync::Mutex<Vec<Option<String>>>> =
        Arc::new(std::sync::Mutex::new(vec![None; timestamps.len()]));
    let next = Arc::new(AtomicUsize::new(0));
    let n = timestamps.len();
    let worker_count = workers.max(1).min(n.max(1));
    std::thread::scope(|s| {
        for _ in 0..worker_count {
            let cancel = cancel.clone();
            let child_pid = child_pid.clone();
            let slots = slots.clone();
            let next = next.clone();
            let temp_dir = temp_dir.clone();
            s.spawn(move || loop {
                let i = next.fetch_add(1, Ordering::Relaxed);
                if i >= n {
                    break;
                }
                if cancel.load(Ordering::Relaxed) {
                    continue;
                }
                let ts = timestamps[i];
                let f0 = (ts * fps).round().max(0.0) as u64;
                let f1 = ((ts + chunk_duration) * fps).round().max(0.0) as u64;
                if f1 <= f0 {
                    continue;
                }
                let ref_vpy_path = temp_dir.join(format!("dn_ref_{}_{}.vpy", pid, i));
                let ref_path = temp_dir.join(format!("dn_ref_{}_{}.mkv", pid, i));
                let ref_vpy = generate_denoise_vpy(
                    &denoise.input,
                    fps,
                    denoise.sigma,
                    DenoiseSource::Lsmash,
                    Some((f0, f1 - 1)),
                    true,
                    vs_threads,
                );
                if let Err(e) = std::fs::write(&ref_vpy_path, ref_vpy) {
                    warn!("Denoise ref: failed to write vpy: {}", e);
                    continue;
                }
                let res = generate_denoised_reference(
                    &ref_vpy_path.to_string_lossy(),
                    &ref_path.to_string_lossy(),
                    cancel.clone(),
                    child_pid.clone(),
                    vs_threads,
                );
                let _ = std::fs::remove_file(&ref_vpy_path);
                if !res.success {
                    warn!("Denoise ref generation failed: {}", res.message);
                    let _ = std::fs::remove_file(&ref_path);
                    continue;
                }
                if let Ok(mut g) = slots.lock() {
                    g[i] = Some(ref_path.to_string_lossy().to_string());
                }
            });
        }
    });
    match Arc::try_unwrap(slots) {
        Ok(guard) => guard.into_inner().unwrap_or_default(),
        Err(_) => vec![None; n],
    }
}

fn cleanup_denoise_refs(refs: &[Option<String>]) {
    for r in refs {
        if let Some(refp) = r {
            let _ = std::fs::remove_file(refp);
        }
    }
}

fn grade_denoised(
    ref_path: &str,
    chunk_index: usize,
    codec: &str,
    crf_value: i32,
    preset_value: &str,
    use_hardware: bool,
    video_info: &crate::ffmpeg::probe::VideoInfo,
    video_type: &VideoType,
    vmaf_subsample: usize,
    width: usize,
    height: usize,
    force_vfr_fix: bool,
    ignore_noise: bool,
    target_vmaf: f64,
    target_ssimulacra2: f64,
    cancel_flag: Arc<AtomicBool>,
    child_pid: Option<PidTracker>,
    encode_threads: usize,
) -> StepChunkOutcome {
    let temp_dir = std::env::temp_dir();
    let chunk_path = temp_dir.join(format!(
        "dn_chunk_{}_{}_{}.mkv",
        std::process::id(),
        chunk_index,
        chrono::Utc::now().timestamp_millis()
    ));
    let chunk_str = chunk_path.to_string_lossy().to_string();
    let res = run_encode_from_ref(
        ref_path,
        &chunk_str,
        codec,
        crf_value,
        preset_value,
        use_hardware,
        video_type,
        encode_threads,
        cancel_flag.clone(),
        child_pid.clone(),
    );
    if !res.success {
        if cancel_flag.load(Ordering::Relaxed) {
            return StepChunkOutcome::Cancelled;
        }
        return StepChunkOutcome::EncodeFailed { message: res.message };
    }
    let qr = quality_check::check_quality_denoised(
        ref_path,
        &chunk_str,
        video_type,
        2.0,
        vmaf_subsample,
        width,
        height,
        video_info,
        force_vfr_fix,
        ignore_noise,
        target_vmaf,
        target_ssimulacra2,
        cancel_flag.clone(),
        child_pid,
        chunk_index as u64,
        None,
    );
    let _ = std::fs::remove_file(&chunk_path);
    match qr {
        Ok(r) => {
            if r.score < 0.0 {
                if cancel_flag.load(Ordering::Relaxed) {
                    StepChunkOutcome::Cancelled
                } else {
                    StepChunkOutcome::MetricFailed {
                        metric: r.metric,
                        message: format!("score={}", r.score),
                    }
                }
            } else {
                StepChunkOutcome::Scored { score: r.score, metric: r.metric }
            }
        }
        Err(e) => StepChunkOutcome::MetricFailed {
            metric: "quality check".to_string(),
            message: e,
        },
    }
}

pub fn find_best_crf(
    input_path: &str, codec: &str, preset_value: &str, use_hardware: bool,
    target_vmaf: f64, target_ssimulacra2: f64,
    cancel_flag: Arc<AtomicBool>,
    progress_cb: Option<Arc<dyn Fn(i32, String) + Send + Sync>>,
    force_vfr_fix: bool,
    child_pid: Option<PidTracker>,
    denoise: Option<DenoiseSpec>,
) -> AutoCrfResult {
    let settings = crate::settings::load_settings();
    info!("Auto CRF: ignore_noise_for_tests={}", settings.ignore_noise_for_tests);
    let video_info = match get_full_video_info(input_path) {
        Ok(i) => i,
        Err(e) => {
            error!("Auto CRF: failed to probe video {}: {}", input_path, e);
            return AutoCrfResult { crf: None, best_crf: None, best_vmaf: 0.0, cancelled: false, metric_error: None };
        }
    };
    let video_type = &video_info.video_type;
    let width = video_info.width;
    let height = video_info.height;
    let duration = video_info.duration;
    let codecs = get_codecs();
    let codec_info = match codecs.get(codec) {
        Some(c) => c.clone(),
        None => match codecs.get("libx264") {
            Some(c) => c.clone(),
            None => {
                error!("Auto CRF: codec '{}' not found and no libx264 fallback", codec);
                return AutoCrfResult { crf: None, best_crf: None, best_vmaf: 0.0, cancelled: false, metric_error: None };
            }
        },
    };
    let mut crf_low = codec_info.crf_min;
    let mut crf_high = codec_info.crf_max;

    let vmaf_subsample = settings.vmaf_subsample;
    let chunk_count = settings.chunk_count;
    let chunk_duration = settings.chunk_duration as f64;
    let needs_fix = force_vfr_fix || video_info.needs_vfr_fix;
    let pad_applied = codec == "libx264" && !use_hardware && !needs_fix;

    info!("Auto CRF: content type={:?}, using {} metric", video_type,
        match video_type { VideoType::Animation | VideoType::Rendered => "SSIMULACRA2", _ => "VMAF" });
    info!("Auto CRF: settings -> vmaf_subsample={}, chunk_count={}, chunk_duration={}", vmaf_subsample, chunk_count, chunk_duration);

    let timestamps = if duration < 30.0 {
        vec![(duration * 0.5).round()]
    } else {
        match chunk_count {
            1 => vec![(duration * 0.5).round()],
            2 => vec![(duration * 0.2).round(), (duration * 0.8).round()],
            3 => vec![(duration * 0.1).round(), (duration * 0.5).round(), (duration * 0.8).round()],
            4 => vec![(duration * 0.1).round(), (duration * 0.35).round(), (duration * 0.6).round(), (duration * 0.85).round()],
            _ => vec![(duration * 0.1).round(), (duration * 0.3).round(), (duration * 0.5).round(), (duration * 0.7).round(), (duration * 0.9).round()],
        }
    };

    // Denoise-aware references (reused across CRF candidates). Denoise is
    // CRF-independent, so it runs exactly once per chunk here; candidate CRFs
    // are encoded from these lossless references instead of re-running BM3D.
    let usable = crate::vapoursynth::runner::denoise_usable_cores();
    let denoise_workers = effective_workers(timestamps.len(), use_hardware).min(usable);
    let ref_vs_threads = crate::vapoursynth::runner::denoise_vs_threads_for_workers(denoise_workers);
    let denoise_refs: Vec<Option<String>> = match &denoise {
        Some(d) => build_denoise_references(d, &timestamps, chunk_duration, cancel_flag.clone(), child_pid.clone(), denoise_workers, ref_vs_threads),
        None => Vec::new(),
    };
    let use_denoise = denoise.is_some() && denoise_refs.iter().any(|o| o.is_some());
    if use_denoise {
        info!("Auto CRF: denoise-aware mode ({} references)", denoise_refs.iter().filter(|o| o.is_some()).count());
    } else if denoise.is_some() {
        warn!("Auto CRF: denoise requested but no references were generated, falling back to raw source");
        if let Some(cb) = &progress_cb {
            cb(3, "Denoise unavailable (plugin issue) — using raw source".to_string());
        }
    }

    let denoise_run_workers = if use_denoise {
        denoise_workers
    } else {
        effective_workers(timestamps.len(), use_hardware)
    };
    let encode_threads = crate::vapoursynth::runner::denoise_vs_threads_for_workers(denoise_run_workers);
    let parallel = timestamps.len() > 1;

    let mut best_crf_closest = codec_info.crf_default;
    let mut best_vmaf_closest = 0.0_f64;
    let mut min_diff = f64::MAX;
    let mut best_crf_acceptable = -1;
    let mut best_vmaf_acceptable = 0.0_f64;
    let mut cancelled = false;
    let mut metric_error: Option<String> = None;
    let temp_dir = std::env::temp_dir();

    let effective_target = match video_type {
        VideoType::Animation | VideoType::Rendered => target_ssimulacra2,
        _ => target_vmaf,
    };

    for step in 0..6 {
        if crf_low > crf_high { break; }
        let mid_crf = (crf_low + crf_high) / 2;
        if let Some(ref cb) = progress_cb {
            cb(10 + step * 10, format!("Auto CRF: testing CRF {}...", mid_crf));
        }
        let mut quality_scores = Vec::new();

        if parallel {
            let file_stamp = chrono::Utc::now().timestamp_millis();
            let outcomes = run_parallel(timestamps.len(), denoise_run_workers, |i| {
                if use_denoise {
                    match &denoise_refs[i] {
                        Some(refp) => grade_denoised(
                            refp, i, codec, mid_crf, preset_value, use_hardware, &video_info, video_type,
                            vmaf_subsample, width, height, force_vfr_fix, settings.ignore_noise_for_tests, target_vmaf, target_ssimulacra2,
                            cancel_flag.clone(), child_pid.as_ref().map(|t| t.fork()),
                            encode_threads,
                        ),
                        None => StepChunkOutcome::MetricFailed { metric: "denoise".to_string(), message: "reference unavailable".to_string() },
                    }
                } else {
                    let chunk_path = temp_dir.join(format!("auto_crf_{}_{}_{}.mkv", std::process::id(), file_stamp, i));
                    let chunk_str = chunk_path.to_string_lossy().to_string();
                    grade_chunk(
                        input_path, &chunk_str, timestamps[i], chunk_duration,
                        codec, mid_crf, preset_value, use_hardware, &video_info, video_type,
                        vmaf_subsample, width, height, force_vfr_fix, pad_applied,
                        settings.ignore_noise_for_tests, target_vmaf, target_ssimulacra2,
                        cancel_flag.clone(), child_pid.as_ref().map(|t| t.fork()),
                    )
                }
            });

            for (i, outcome) in outcomes.into_iter().enumerate() {
                match outcome {
                    None => {
                        log_worker_panic(i);
                        warn!("Auto CRF: chunk worker {} panicked, skipping chunk", i + 1);
                        if metric_error.is_none() {
                            metric_error = Some(format!("chunk worker {} panicked", i + 1));
                        }
                    }
                    Some(StepChunkOutcome::Scored { score, metric }) => {
                        info!("Auto CRF: chunk {} at CRF {} -> {}={:.2}", i, mid_crf, metric, score);
                        quality_scores.push(score);
                        if let Some(cb) = &progress_cb {
                            let frac = (i + 1) as f32 / timestamps.len() as f32;
                            cb(
                                ((10 + step * 10) as f32 + frac * 10.0) as i32,
                                format!("Auto CRF step {}: chunk {}/{} at CRF {} done ({}={:.1})", step + 1, i + 1, timestamps.len(), mid_crf, metric, score),
                            );
                        }
                    }
                    Some(StepChunkOutcome::EncodeFailed { message }) => {
                        warn!("Auto CRF: encode failed for chunk {} at CRF {}, skipping: {}", i, mid_crf, message);
                        if metric_error.is_none() {
                            metric_error = Some(format!("encode: {}", message));
                        }
                    }
                    Some(StepChunkOutcome::MetricFailed { metric, message }) => {
                        warn!("Auto CRF: {} failed for chunk {} at CRF {}, skipping: {}", metric, i, mid_crf, message);
                        if metric_error.is_none() {
                            metric_error = Some(format!("{}: {}", metric, message));
                        }
                    }
                    Some(StepChunkOutcome::Cancelled) => {
                        info!("Auto CRF: search cancelled during chunk {} at CRF {}", i, mid_crf);
                        cancelled = true;
                    }
                }
            }

            if cancelled {
                break;
            }
            if quality_scores.is_empty() {
                warn!("Auto CRF: no chunk scored at step {}, aborting search", step + 1);
                break;
            }
        } else {
            for (i, ts) in timestamps.iter().enumerate() {
                if use_denoise {
                    match &denoise_refs[i] {
                        Some(refp) => {
                            let oc = grade_denoised(
                                refp, i, codec, mid_crf, preset_value, use_hardware, &video_info, video_type,
                                vmaf_subsample, width, height, force_vfr_fix, settings.ignore_noise_for_tests, target_vmaf, target_ssimulacra2,
                                cancel_flag.clone(), child_pid.clone(),
                                encode_threads,
                            );
                            match oc {
                                StepChunkOutcome::Scored { score, metric } => {
                                    info!("Auto CRF: chunk {} at CRF {} -> {}={:.2}", i, mid_crf, metric, score);
                                    quality_scores.push(score);
                                    if let Some(cb) = &progress_cb {
                                        let frac = (i + 1) as f32 / timestamps.len() as f32;
                                        cb(
                                            ((10 + step * 10) as f32 + frac * 10.0) as i32,
                                            format!("Auto CRF step {}: chunk {}/{} at CRF {} done ({}={:.1})", step + 1, i + 1, timestamps.len(), mid_crf, metric, score),
                                        );
                                    }
                                }
                                StepChunkOutcome::Cancelled => cancelled = true,
                                StepChunkOutcome::EncodeFailed { message } => {
                                    if cancel_flag.load(Ordering::Relaxed) { cancelled = true; }
                                    else if metric_error.is_none() { metric_error = Some(format!("encode: {}", message)); }
                                }
                                StepChunkOutcome::MetricFailed { metric, message } => {
                                    if cancel_flag.load(Ordering::Relaxed) { cancelled = true; }
                                    else if metric_error.is_none() { metric_error = Some(format!("{}: {}", metric, message)); }
                                }
                            }
                        }
                        None => { if metric_error.is_none() { metric_error = Some("denoise reference unavailable".to_string()); } }
                    }
                } else {
                    let chunk_path = temp_dir.join(format!("auto_crf_{}_{}_{}.mkv", std::process::id(), chrono::Utc::now().timestamp(), i));
                    let chunk_str = chunk_path.to_string_lossy().to_string();
                    let result = encode_chunk(
                        input_path, &chunk_str, *ts, chunk_duration,
                        codec, mid_crf, preset_value, use_hardware, &video_info, video_type, force_vfr_fix,
                        cancel_flag.clone(), child_pid.clone(),
                    );
                    if !result.success {
                        if cancel_flag.load(Ordering::Relaxed) {
                            info!("Auto CRF: search cancelled during chunk {} at CRF {}", i, mid_crf);
                            cancelled = true;
                        } else {
                            warn!("Auto CRF: encode failed for chunk {} at CRF {}, skipping: {}", i, mid_crf, result.message);
                            if metric_error.is_none() {
                                metric_error = Some(format!("encode: {}", result.message));
                            }
                        }
                        continue;
                    }
                    let qr = quality_check::check_quality(
                        input_path, &chunk_str, video_type,
                        *ts, chunk_duration,
                        vmaf_subsample, width, height, &video_info,
                        force_vfr_fix, pad_applied, settings.ignore_noise_for_tests,
                        target_vmaf, target_ssimulacra2, cancel_flag.clone(),
                        child_pid.clone(), None,
                    );
                    if let Err(e) = std::fs::remove_file(&chunk_path) {
                        warn!("Failed to remove chunk {:?}: {}", chunk_path, e);
                    }
                    match qr {
                        Ok(r) => {
                            if r.score < 0.0 {
                                if cancel_flag.load(Ordering::Relaxed) {
                                    info!("Auto CRF: search cancelled during {} for chunk {} at CRF {}", r.metric, i, mid_crf);
                                    cancelled = true;
                                } else {
                                    warn!("Auto CRF: {} failed for chunk {} at CRF {} (score={}), skipping", r.metric, i, mid_crf, r.score);
                                    if metric_error.is_none() {
                                        metric_error = Some(format!("{}: score={}", r.metric, r.score));
                                    }
                                }
                                continue;
                            }
                            info!("Auto CRF: chunk {} at CRF {} -> {}={:.2}", i, mid_crf, r.metric, r.score);
                            quality_scores.push(r.score);
                            if let Some(cb) = &progress_cb {
                                let frac = (i + 1) as f32 / timestamps.len() as f32;
                                cb(
                                    ((10 + step * 10) as f32 + frac * 10.0) as i32,
                                    format!("Auto CRF step {}: chunk {}/{} at CRF {} done ({}={:.1})", step + 1, i + 1, timestamps.len(), mid_crf, r.metric, r.score),
                                );
                            }
                        }
                        Err(e) => {
                            if cancel_flag.load(Ordering::Relaxed) {
                                info!("Auto CRF: search cancelled during quality check for chunk {} at CRF {}", i, mid_crf);
                                cancelled = true;
                            } else {
                                warn!("Auto CRF: quality check error for chunk {} at CRF {}, skipping: {}", i, mid_crf, e);
                                if metric_error.is_none() {
                                    metric_error = Some(format!("quality check: {}", e));
                                }
                            }
                            continue;
                        }
                    }
                }
            }

            if cancelled {
                break;
            }
            if quality_scores.is_empty() {
                warn!("Auto CRF: no chunk scored at step {}, aborting search", step + 1);
                break;
            }
        }
        let avg_score = quality_scores.iter().sum::<f64>() / quality_scores.len() as f64;
        let diff = (avg_score - effective_target).abs();

        info!("Auto CRF: step {}, CRF {}, Avg Score={:.2}, Target={}", step + 1, mid_crf, avg_score, effective_target);

        if avg_score >= (effective_target - 0.1) && mid_crf > best_crf_acceptable {
            best_crf_acceptable = mid_crf;
            best_vmaf_acceptable = avg_score;
        }
        if diff < min_diff {
            min_diff = diff;
            best_crf_closest = mid_crf;
            best_vmaf_closest = avg_score;
        }
        if avg_score < effective_target {
            crf_high = mid_crf - 1;
        } else {
            crf_low = mid_crf + 1;
        }
    }

    cleanup_denoise_refs(&denoise_refs);

    if cancelled {
        warn!("Auto CRF: search cancelled, no CRF selected");
        return AutoCrfResult { crf: None, best_crf: Some(best_crf_closest), best_vmaf: best_vmaf_closest, cancelled: true, metric_error };
    }

    let (final_crf, best_vmaf) = if best_crf_acceptable != -1 {
        (Some(best_crf_acceptable), best_vmaf_acceptable)
    } else {
        (None, best_vmaf_closest)
    };

    if let Some(crf) = final_crf {
        info!("Auto CRF done: selected CRF {} for target {} (achieved: {:.1})", crf, effective_target, best_vmaf);
        if let Some(cb) = progress_cb {
            cb(60, format!("Auto CRF done: CRF {}", crf));
        }
    } else {
        warn!("Auto CRF: target {} unreachable. Best CRF {} gives score {:.1}", effective_target, best_crf_closest, best_vmaf);
        if let Some(cb) = progress_cb {
            cb(60, format!("Auto CRF: target {} unreachable (best: {:.1})", effective_target, best_vmaf));
        }
    }

    AutoCrfResult { crf: final_crf, best_crf: Some(best_crf_closest), best_vmaf, cancelled, metric_error }
}

pub struct ChunkTestResult {
    pub test_diff: String,
    pub test_est_size: String,
    pub test_est_time: String,
    pub test_vmaf: f64,
    pub is_profitable: bool,
    pub test_crf: i32,
    pub metric: String,
}

pub fn run_chunk_test(
    input_path: &str, codec: &str, crf_value: i32, preset_value: &str,
    use_hardware: bool, cancel_flag: Arc<AtomicBool>,
    auto_crf: bool, target_vmaf: f64, target_ssimulacra2: f64, force_vfr_fix: bool,
    force_metric: Option<String>,
    progress_cb: Option<Arc<dyn Fn(i32, String) + Send + Sync>>,
    child_pid: Option<PidTracker>,
    denoise: Option<DenoiseSpec>,
) -> Result<ChunkTestResult, String> {
    let mut actual_crf = crf_value;
    let settings = crate::settings::load_settings();
    let video_info = get_full_video_info(input_path)?;
    let video_type = &video_info.video_type;

    info!("Chunk Test: content type={:?}, ignore_noise_for_tests={}", video_type, settings.ignore_noise_for_tests);

    if auto_crf {
        info!("Chunk Test: Auto CRF enabled, target VMAF={}", target_vmaf);
        let acrf = find_best_crf(input_path, codec, preset_value, use_hardware, target_vmaf, target_ssimulacra2, cancel_flag.clone(), progress_cb.clone(), force_vfr_fix, child_pid.clone(), denoise.clone());
        if acrf.cancelled {
            return Err("Operation cancelled".to_string());
        }
        actual_crf = match acrf.crf {
            Some(crf) => crf,
            None => {
                let msg = match acrf.metric_error {
                    Some(err) => format!("Failed (metric error: {})", err),
                    None => match acrf.best_crf {
                        Some(bc) => format!("Failed (best result: {} / {:.1})", bc, acrf.best_vmaf),
                        None => "Failed (video analysis error)".to_string(),
                    },
                };
                warn!("Chunk Test: {}", msg);
                return Err(msg);
            }
        };
        info!("Chunk Test: Auto CRF selected CRF {}", actual_crf);
    }

    let duration = video_info.duration;
    let width = video_info.width;
    let height = video_info.height;

    let chunk_count = settings.chunk_count;
    let chunk_duration = settings.chunk_duration as f64;
    let vmaf_subsample = settings.vmaf_subsample;
    let needs_fix = force_vfr_fix || video_info.needs_vfr_fix;
    let pad_applied = codec == "libx264" && !use_hardware && !needs_fix;

    let timestamps = if duration < 30.0 {
        vec![(duration * 0.5).round()]
    } else {
        match chunk_count {
            1 => vec![(duration * 0.5).round()],
            2 => vec![(duration * 0.2).round(), (duration * 0.8).round()],
            3 => vec![(duration * 0.1).round(), (duration * 0.5).round(), (duration * 0.8).round()],
            4 => vec![(duration * 0.1).round(), (duration * 0.35).round(), (duration * 0.6).round(), (duration * 0.85).round()],
            _ => vec![(duration * 0.1).round(), (duration * 0.3).round(), (duration * 0.5).round(), (duration * 0.7).round(), (duration * 0.9).round()],
        }
    };

    let usable = crate::vapoursynth::runner::denoise_usable_cores();
    let denoise_workers = effective_workers(timestamps.len(), use_hardware).min(usable);
    let ref_vs_threads = crate::vapoursynth::runner::denoise_vs_threads_for_workers(denoise_workers);
    let denoise_refs: Vec<Option<String>> = match &denoise {
        Some(d) => build_denoise_references(d, &timestamps, chunk_duration, cancel_flag.clone(), child_pid.clone(), denoise_workers, ref_vs_threads),
        None => Vec::new(),
    };
    let use_denoise = denoise.is_some() && denoise_refs.iter().any(|o| o.is_some());
    if denoise.is_some() && !use_denoise {
        warn!("Chunk Test: denoise requested but no references were generated, falling back to raw source");
        if let Some(cb) = &progress_cb {
            cb(1, "Denoise unavailable (plugin issue) — using raw source".to_string());
        }
    }

    let denoise_run_workers = if use_denoise {
        denoise_workers
    } else {
        effective_workers(timestamps.len(), use_hardware)
    };
    let encode_threads = crate::vapoursynth::runner::denoise_vs_threads_for_workers(denoise_run_workers);
    let parallel = timestamps.len() > 1;

    let temp_dir = std::env::temp_dir();
    let mut total_size_bytes: u64 = 0;
    let mut quality_scores = Vec::new();
    let mut metric_missing = false;
    let mut encode_time_total: f64 = 0.0;
    let mut used_metric = "VMAF".to_string();

    let progress_start = if auto_crf { 60 } else { 0 };
    let progress_span = 100 - progress_start;

    if parallel {
        let file_stamp = chrono::Utc::now().timestamp_millis();
        if let Some(cb) = &progress_cb {
            cb(progress_start, format!("Chunk {}/{} at CRF {}...", 1, timestamps.len(), actual_crf));
        }
        let outcomes = run_parallel(timestamps.len(), denoise_run_workers, |i| {
            if use_denoise {
                match &denoise_refs[i] {
                    Some(refp) => {
                        let chunk_path = temp_dir.join(format!("dn_ct_{}_{}_{}.mkv", std::process::id(), file_stamp, i));
                        let chunk_str = chunk_path.to_string_lossy().to_string();
                        let res = run_encode_from_ref(refp, &chunk_str, codec, actual_crf, preset_value, use_hardware, video_type, encode_threads, cancel_flag.clone(), child_pid.as_ref().map(|t| t.fork()));
                        let mut out = crate::video_processor::parallel_chunks::TestChunkOutcome { size_bytes: 0, encode_seconds: 0.0, score: None, metric: None, quality_error: None, encode_error: None };
                        if !res.success {
                            out.encode_error = Some(res.message);
                        } else {
                            if let Ok(meta) = std::fs::metadata(&chunk_path) { out.size_bytes = meta.len(); }
                            let qr = quality_check::check_quality_denoised(refp, &chunk_str, video_type, chunk_duration, vmaf_subsample, width, height, &video_info, force_vfr_fix, settings.ignore_noise_for_tests, target_vmaf, target_ssimulacra2, cancel_flag.clone(), child_pid.clone(), i as u64, force_metric.clone());
                            match qr {
                                Ok(r) => { out.score = Some(r.score); out.metric = Some(r.metric); }
                                Err(e) => out.quality_error = Some(e),
                            }
                            let _ = std::fs::remove_file(&chunk_path);
                        }
                        out
                    }
                    None => crate::video_processor::parallel_chunks::TestChunkOutcome { size_bytes: 0, encode_seconds: 0.0, score: None, metric: None, quality_error: None, encode_error: Some("denoise reference unavailable".to_string()) },
                }
            } else {
                let out_path = temp_dir.join(format!("chunk_test_{}_{}_{}.mkv", std::process::id(), file_stamp, i));
                let out_str = out_path.to_string_lossy().to_string();
                test_chunk(
                    input_path, &out_str, timestamps[i], chunk_duration,
                    codec, actual_crf, preset_value, use_hardware, &video_info, video_type,
                    vmaf_subsample, width, height, force_vfr_fix, pad_applied,
                    settings.ignore_noise_for_tests, target_vmaf, target_ssimulacra2,
                    force_metric.clone(), cancel_flag.clone(),
                    child_pid.as_ref().map(|t| t.fork()),
                )
            }
        });

        for (i, outcome) in outcomes.into_iter().enumerate() {
            if let Some(cb) = &progress_cb {
                let pct = progress_start + ((i as f32 + 1.0) / timestamps.len() as f32 * progress_span as f32) as i32;
                cb(pct, format!("Chunk {}/{} at CRF {} done", i + 1, timestamps.len(), actual_crf));
            }
            let outcome = match outcome {
                Some(o) => o,
                None => {
                    log_worker_panic(i);
                    return Err(format!("Chunk worker {} panicked", i + 1));
                }
            };
            if let Some(err) = outcome.encode_error {
                return Err(format!("Error encoding chunk {}: {}", i + 1, err));
            }
            encode_time_total += outcome.encode_seconds;
            total_size_bytes += outcome.size_bytes;
            if let Some(m) = outcome.metric {
                used_metric = m;
            }
            match outcome.score {
                Some(s) if s < 0.0 => {
                    error!("Chunk Test: {} missing, skipping for remaining chunks", used_metric);
                    metric_missing = true;
                }
                Some(s) => {
                    info!("Chunk Test: chunk {} at CRF {} -> {}={:.2}", i, actual_crf, used_metric, s);
                    quality_scores.push(s);
                }
                None => {}
            }
            if let Some(err) = outcome.quality_error {
                warn!("Chunk Test: quality check error for chunk {}: {}", i, err);
            }
        }
    } else {
        for (i, ts) in timestamps.iter().enumerate() {
            if let Some(cb) = &progress_cb {
                let pct = progress_start + ((i as f32 + 1.0) / timestamps.len() as f32 * progress_span as f32) as i32;
                cb(pct, format!("Chunk {}/{} at CRF {}...", i + 1, timestamps.len(), actual_crf));
            }
            if use_denoise {
                match &denoise_refs[i] {
                    Some(refp) => {
                        let start = std::time::Instant::now();
                        let out_path = temp_dir.join(format!("dn_ct_{}_{}_{}.mkv", std::process::id(), chrono::Utc::now().timestamp(), i));
                        let out_str = out_path.to_string_lossy().to_string();
                        let res = run_encode_from_ref(refp, &out_str, codec, actual_crf, preset_value, use_hardware, video_type, encode_threads, cancel_flag.clone(), child_pid.clone());
                        encode_time_total += start.elapsed().as_secs_f64();
                        if !res.success {
                            return Err(format!("Error encoding chunk {}: {}", i + 1, res.message));
                        }
                        if out_path.exists() {
                            if !metric_missing {
                                let qr = quality_check::check_quality_denoised(refp, &out_str, video_type, chunk_duration, vmaf_subsample, width, height, &video_info, force_vfr_fix, settings.ignore_noise_for_tests, target_vmaf, target_ssimulacra2, cancel_flag.clone(), child_pid.clone(), i as u64, force_metric.clone());
                                match qr {
                                    Ok(r) => { used_metric = r.metric.clone(); if r.score < 0.0 { error!("Chunk Test: {} missing, skipping", r.metric); metric_missing = true; } else if r.score >= 0.0 { info!("Chunk Test: chunk {} at CRF {} -> {}={:.2}", i, actual_crf, r.metric, r.score); quality_scores.push(r.score); } }
                                    Err(e) => warn!("Chunk Test: quality check error for chunk {}: {}", i, e),
                                }
                            }
                            if let Ok(meta) = std::fs::metadata(&out_path) { total_size_bytes += meta.len(); }
                            if let Err(e) = std::fs::remove_file(&out_path) { warn!("Failed to remove chunk output {:?}: {}", out_path, e); }
                        }
                    }
                    None => return Err("Denoise reference unavailable".to_string()),
                }
            } else {
                let out_path = temp_dir.join(format!("chunk_test_{}_{}_{}.mkv", std::process::id(), chrono::Utc::now().timestamp(), i));
                let out_str = out_path.to_string_lossy().to_string();

                let start = std::time::Instant::now();
                let result = encode_chunk(
                    input_path, &out_str, *ts, chunk_duration,
                    codec, actual_crf, preset_value, use_hardware, &video_info, video_type, force_vfr_fix,
                    cancel_flag.clone(), child_pid.clone(),
                );
                encode_time_total += start.elapsed().as_secs_f64();

                if !result.success {
                    return Err(format!("Error encoding chunk {}: {}", i + 1, result.message));
                }

                if out_path.exists() {
                    if !metric_missing {
                        let qr = quality_check::check_quality(
                            input_path, &out_str, video_type,
                            *ts, chunk_duration,
                            vmaf_subsample, width, height, &video_info,
                            force_vfr_fix, pad_applied, settings.ignore_noise_for_tests,
                            target_vmaf, target_ssimulacra2, cancel_flag.clone(),
                            child_pid.clone(), force_metric.clone(),
                        );
                        match qr {
                            Ok(r) => {
                                used_metric = r.metric.clone();
                                if r.score < 0.0 {
                                    error!("Chunk Test: {} missing, skipping for remaining chunks", r.metric);
                                    metric_missing = true;
                                } else if r.score >= 0.0 {
                                    info!("Chunk Test: chunk {} at CRF {} -> {}={:.2}", i, actual_crf, r.metric, r.score);
                                    quality_scores.push(r.score);
                                }
                            }
                            Err(e) => {
                                warn!("Chunk Test: quality check error for chunk {}: {}", i, e);
                            }
                        }
                    }
                    if let Ok(meta) = std::fs::metadata(&out_path) {
                        total_size_bytes += meta.len();
                    }
                    if let Err(e) = std::fs::remove_file(&out_path) {
                        warn!("Failed to remove chunk output {:?}: {}", out_path, e);
                    }
                }
            }
        }
    }

    cleanup_denoise_refs(&denoise_refs);

    let total_chunk_duration = chunk_duration as f64 * timestamps.len() as f64;
    let chunk_video_bitrate_bps = (total_size_bytes as f64 * 8.0) / total_chunk_duration;
    let expected_audio_bitrate_bps = 192_000.0;
    let chunk_bitrate_bps = chunk_video_bitrate_bps + expected_audio_bitrate_bps;
    let est_size_mb = (chunk_bitrate_bps * duration) / 8.0 / (1024.0 * 1024.0);

    let est_time_sec = if encode_time_total > 0.0 {
        let speed_multiplier = total_chunk_duration / encode_time_total;
        duration / speed_multiplier
    } else {
        0.0
    };

    let orig_size_mb = video_info.size_mb;
    let diff_percent = if orig_size_mb > 0.0 {
        ((orig_size_mb - est_size_mb) / orig_size_mb) * 100.0
    } else {
        0.0
    };
    let diff_str = if diff_percent > 0.0 {
        format!("-{:.1}%", diff_percent)
    } else {
        format!("+{:.1}%", diff_percent.abs())
    };

    let avg_score = if quality_scores.is_empty() { -1.0 }
    else if metric_missing { -2.0 }
    else { quality_scores.iter().sum::<f64>() / quality_scores.len() as f64 };

    log::info!("Chunk Test finished for {}: diff={}, est size={}, {}={:.1}", input_path, diff_str, format!("{:.1} MB", est_size_mb), used_metric, avg_score);

    Ok(ChunkTestResult {
        test_diff: diff_str,
        test_est_size: format!("{:.1} MB", est_size_mb),
        test_est_time: format_duration(est_time_sec),
        test_vmaf: avg_score,
        is_profitable: diff_percent > 0.0,
        test_crf: actual_crf,
        metric: used_metric,
    })
}
