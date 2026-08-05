use std::path::Path;
use std::sync::Arc;
use std::sync::atomic::AtomicBool;

use log::error;

use crate::ffmpeg::encode::encode_chunk;
use crate::ffmpeg::probe::{VideoInfo, VideoType};
use crate::process_control::PidTracker;
use crate::video_processor::quality_check;

pub enum StepChunkOutcome {
    Scored { score: f64, metric: String },
    EncodeFailed { message: String },
    MetricFailed { metric: String, message: String },
    Cancelled,
}

pub struct TestChunkOutcome {
    pub size_bytes: u64,
    pub encode_seconds: f64,
    pub score: Option<f64>,
    pub metric: Option<String>,
    pub quality_error: Option<String>,
    pub encode_error: Option<String>,
}

pub fn effective_workers(chunk_count: usize, use_hardware: bool) -> usize {
    let settings = crate::settings::load_settings();
    let cores = std::thread::available_parallelism()
        .map(|n| n.get())
        .unwrap_or(4);
    let cap = if use_hardware { 8 } else { cores };
    let max = if settings.parallel_workers > 0 {
        settings.parallel_workers
    } else {
        cap
    };
    chunk_count.min(max).max(1)
}

pub fn run_parallel<T, F>(count: usize, workers: usize, worker: F) -> Vec<Option<T>>
where
    F: Fn(usize) -> T + Sync,
    T: Send,
{
    let workers = workers.min(count).max(1);
    if workers <= 1 {
        return (0..count).map(worker).map(Some).collect();
    }
    let per = (count + workers - 1) / workers;
    let worker_ref = &worker;
    std::thread::scope(|s| {
        let mut handles = Vec::new();
        for w in 0..workers {
            let start = w * per;
            let end = (start + per).min(count);
            if start >= end {
                break;
            }
            handles.push((start, end, s.spawn(move || {
                (start..end).map(|i| (i, worker_ref(i))).collect::<Vec<_>>()
            })));
        }
        let mut results: Vec<Option<T>> = (0..count).map(|_| None).collect();
        for (start, end, handle) in handles {
            match handle.join() {
                Ok(pairs) => {
                    for (i, value) in pairs {
                        results[i] = Some(value);
                    }
                }
                Err(_) => {
                    for slot in results.iter_mut().take(end).skip(start) {
                        *slot = None;
                    }
                }
            }
        }
        results
    })
}

#[allow(clippy::too_many_arguments)]
pub fn grade_chunk(
    input_path: &str,
    chunk_path: &str,
    ts: f64,
    chunk_duration: f64,
    codec: &str,
    crf_value: i32,
    preset_value: &str,
    use_hardware: bool,
    video_info: &VideoInfo,
    video_type: &VideoType,
    vmaf_subsample: usize,
    width: usize,
    height: usize,
    force_vfr_fix: bool,
    pad_applied: bool,
    ignore_noise: bool,
    target_vmaf: f64,
    target_ssimulacra2: f64,
    cancel_flag: Arc<AtomicBool>,
    child_pid: Option<PidTracker>,
) -> StepChunkOutcome {
    let encode_result = encode_chunk(
        input_path, chunk_path, ts, chunk_duration,
        codec, crf_value, preset_value, use_hardware,
        video_info, video_type, force_vfr_fix,
        cancel_flag.clone(), child_pid.clone(),
    );
    if !encode_result.success {
        if cancel_flag.load(std::sync::atomic::Ordering::Relaxed) {
            return StepChunkOutcome::Cancelled;
        }
        return StepChunkOutcome::EncodeFailed { message: encode_result.message };
    }

    let qr = quality_check::check_quality(
        input_path, chunk_path, video_type,
        ts, chunk_duration,
        vmaf_subsample, width, height, video_info,
        force_vfr_fix, pad_applied, ignore_noise,
        target_vmaf, target_ssimulacra2,
        cancel_flag.clone(), child_pid, None,
    );

    let _ = std::fs::remove_file(chunk_path);

    match qr {
        Ok(r) => {
            if r.score < 0.0 {
                if cancel_flag.load(std::sync::atomic::Ordering::Relaxed) {
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

#[allow(clippy::too_many_arguments)]
pub fn test_chunk(
    input_path: &str,
    chunk_path: &str,
    ts: f64,
    chunk_duration: f64,
    codec: &str,
    crf_value: i32,
    preset_value: &str,
    use_hardware: bool,
    video_info: &VideoInfo,
    video_type: &VideoType,
    vmaf_subsample: usize,
    width: usize,
    height: usize,
    force_vfr_fix: bool,
    pad_applied: bool,
    ignore_noise: bool,
    target_vmaf: f64,
    target_ssimulacra2: f64,
    force_metric: Option<String>,
    cancel_flag: Arc<AtomicBool>,
    child_pid: Option<PidTracker>,
) -> TestChunkOutcome {
    let start = std::time::Instant::now();
    let result = encode_chunk(
        input_path, chunk_path, ts, chunk_duration,
        codec, crf_value, preset_value, use_hardware,
        video_info, video_type, force_vfr_fix,
        cancel_flag.clone(), child_pid.clone(),
    );
    let encode_seconds = start.elapsed().as_secs_f64();

    if !result.success {
        return TestChunkOutcome {
            size_bytes: 0,
            encode_seconds,
            score: None,
            metric: None,
            quality_error: None,
            encode_error: Some(result.message),
        };
    }

    let mut size_bytes = 0;
    let mut score = None;
    let mut metric = None;
    let mut quality_error = None;

    if Path::new(chunk_path).exists() {
        match quality_check::check_quality(
            input_path, chunk_path, video_type,
            ts, chunk_duration,
            vmaf_subsample, width, height, video_info,
            force_vfr_fix, pad_applied, ignore_noise,
            target_vmaf, target_ssimulacra2,
            cancel_flag.clone(), child_pid, force_metric,
        ) {
            Ok(r) => {
                metric = Some(r.metric);
                score = Some(r.score);
            }
            Err(e) => {
                quality_error = Some(e);
            }
        }
        if let Ok(meta) = std::fs::metadata(chunk_path) {
            size_bytes = meta.len();
        }
        if let Err(e) = std::fs::remove_file(chunk_path) {
            log::warn!("Failed to remove chunk output {:?}: {}", chunk_path, e);
        }
    }

    TestChunkOutcome {
        size_bytes,
        encode_seconds,
        score,
        metric,
        quality_error,
        encode_error: None,
    }
}

pub fn log_worker_panic(index: usize) {
    error!("Chunk worker {} panicked", index);
}
