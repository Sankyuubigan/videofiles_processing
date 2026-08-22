use std::sync::Arc;
use std::sync::atomic::AtomicBool;
use std::sync::atomic::Ordering;

use log::{info, warn};
use oximedia_core::PixelFormat;
use oximedia_quality::blur_detector::AdvancedBlurDetector;
use oximedia_quality::blockiness_detector::AdvancedBlockinessDetector;
use oximedia_quality::{BrisqueAssessor, Frame, NiqeAssessor, NoiseEstimator};

use crate::ffmpeg::core::run_command_simple;
use crate::video_processor::compress::get_full_video_info;

/// Max frame width used for quality metrics (speed vs. detail trade-off).
const MAX_FRAME_WIDTH: usize = 1280;

/// NIQE requires patches of at least 96x96.
const NIQE_MIN_DIM: usize = 96;

/// Noise score >= this value is considered "heavy noise" (0% quality).
const NOISE_MAX: f64 = 15.0;

#[derive(Clone, serde::Serialize)]
pub struct MetricSummary {
    pub name: String,
    pub avg_pct: f64,
    pub min_pct: f64,
    pub max_pct: f64,
    pub note: String,
}

#[derive(Clone, serde::Serialize)]
pub struct QualityAssessment {
    pub file: String,
    pub frames_used: usize,
    pub metrics: Vec<MetricSummary>,
    pub verdict: String,
}

struct FrameMetrics {
    natural_pct: f64,
    niqe_pct: Option<f64>,
    sharp_pct: f64,
    sharp_grade: String,
    block_pct: f64,
}

pub(crate) fn chunk_timestamps(duration: f64, chunk_count: usize) -> Vec<f64> {
    if duration < 30.0 {
        return vec![(duration * 0.5).round()];
    }
    match chunk_count {
        1 => vec![(duration * 0.5).round()],
        2 => vec![(duration * 0.2).round(), (duration * 0.8).round()],
        3 => vec![(duration * 0.1).round(), (duration * 0.5).round(), (duration * 0.8).round()],
        4 => vec![(duration * 0.1).round(), (duration * 0.35).round(), (duration * 0.6).round(), (duration * 0.85).round()],
        _ => vec![(duration * 0.1).round(), (duration * 0.3).round(), (duration * 0.5).round(), (duration * 0.7).round(), (duration * 0.9).round()],
    }
}

fn extract_gray_frame(
    input_path: &str, ts: f64, width: usize, height: usize,
    cancel_flag: Arc<AtomicBool>,
) -> Result<Frame, String> {
    let (target_w, target_h) = if width > MAX_FRAME_WIDTH {
        let w = MAX_FRAME_WIDTH;
        let h = ((height * MAX_FRAME_WIDTH) / width) & !1;
        (w, h.max(2))
    } else {
        (width, height)
    };

    let raw_path = std::env::temp_dir().join(format!(
        "quality_frame_{}_{}.raw", std::process::id(), ts
    ));
    let raw_str = raw_path.to_string_lossy().to_string();

    let mut cmd = vec![
        "ffmpeg".to_string(), "-y".to_string(),
        "-ss".to_string(), format!("{:.3}", ts),
        "-i".to_string(), input_path.to_string(),
        "-frames:v".to_string(), "1".to_string(),
    ];
    if (target_w, target_h) != (width, height) {
        cmd.extend(vec![
            "-vf".to_string(), format!("scale={}:{}", target_w, target_h),
        ]);
    }
    cmd.extend(vec![
        "-f".to_string(), "rawvideo".to_string(),
        "-pix_fmt".to_string(), "gray".to_string(),
        raw_str,
    ]);

    let result = run_command_simple(&cmd, cancel_flag, None);
    if !result.success {
        let _ = std::fs::remove_file(&raw_path);
        return Err(format!("Frame extraction at {:.1}s failed: {}", ts, result.message));
    }

    let data = std::fs::read(&raw_path).map_err(|e| {
        let _ = std::fs::remove_file(&raw_path);
        format!("Failed to read extracted frame at {:.1}s: {}", ts, e)
    })?;
    let _ = std::fs::remove_file(&raw_path);

    let expected = target_w * target_h;
    if data.len() != expected {
        return Err(format!(
            "Unexpected raw frame size at {:.1}s: got {} bytes, expected {} ({}x{})",
            ts, data.len(), expected, target_w, target_h
        ));
    }

    let mut frame = Frame::new(target_w, target_h, PixelFormat::Gray8)
        .map_err(|e| format!("Failed to create frame: {}", e))?;
    frame.planes[0].copy_from_slice(&data);
    Ok(frame)
}

fn clamp01(v: f64) -> f64 {
    v.clamp(0.0, 100.0)
}

/// Naturalness/NIQE: raw score is 0-100 where lower = better.
fn inverted_pct(raw: f64) -> f64 {
    clamp01(100.0 - raw)
}

/// Noise: raw is unbounded; >= NOISE_MAX is treated as 0%.
fn noise_pct(raw: f64) -> f64 {
    clamp01(100.0 - raw * 100.0 / NOISE_MAX)
}

/// Sharpness: piecewise-linear over the crate's grade thresholds
/// (0 -> 0%, 10 -> 25%, 50 -> 50%, 300 -> 75%, 1000 -> 100%).
fn sharpness_pct(raw: f64) -> f64 {
    if raw <= 0.0 {
        0.0
    } else if raw < 10.0 {
        raw / 10.0 * 25.0
    } else if raw < 50.0 {
        25.0 + (raw - 10.0) / 40.0 * 25.0
    } else if raw < 300.0 {
        50.0 + (raw - 50.0) / 250.0 * 25.0
    } else if raw < 1000.0 {
        75.0 + (raw - 300.0) / 700.0 * 25.0
    } else {
        100.0
    }
}

/// Blockiness: crate score = (ratio - 1) * 100; ratio 1.0 -> 100%,
/// ratio 1.7 (score 70) -> 0%.
fn blockiness_pct(score: f64) -> f64 {
    clamp01(100.0 - score / 0.7)
}

fn assess_frame_metrics(
    frame: &Frame,
    brisque: &BrisqueAssessor,
    niqe: &NiqeAssessor,
    blur: &AdvancedBlurDetector,
    block: &AdvancedBlockinessDetector,
) -> FrameMetrics {
    let natural = brisque
        .assess(frame)
        .map(|s| inverted_pct(s.score))
        .unwrap_or_else(|e| { warn!("Quality: BRISQUE failed: {}", e); -1.0 });

    let niqe_pct = if frame.width >= NIQE_MIN_DIM && frame.height >= NIQE_MIN_DIM {
        niqe.assess(frame)
            .map(|s| Some(inverted_pct(s.score)))
            .unwrap_or_else(|e| { warn!("Quality: NIQE failed: {}", e); None })
    } else {
        warn!("Quality: NIQE skipped (frame {}x{} < {}x{})", frame.width, frame.height, NIQE_MIN_DIM, NIQE_MIN_DIM);
        None
    };

    let (sharp_pct, sharp_grade) = match blur.measure(frame) {
        Ok(r) => (sharpness_pct(r.score), r.grade.label().to_string()),
        Err(e) => { warn!("Quality: blur measure failed: {}", e); (-1.0, "error".to_string()) }
    };

    let block_pct = match block.analyze(frame) {
        Ok(r) => blockiness_pct(r.score),
        Err(e) => { warn!("Quality: blockiness failed: {}", e); -1.0 }
    };

    FrameMetrics {
        natural_pct: natural,
        niqe_pct,
        sharp_pct,
        sharp_grade,
        block_pct,
    }
}

fn summarize(name: &str, pcts: &[f64], note: &str) -> MetricSummary {
    let avg = pcts.iter().sum::<f64>() / pcts.len() as f64;
    let min = pcts.iter().copied().fold(f64::MAX, f64::min);
    let max = pcts.iter().copied().fold(f64::MIN, f64::max);
    MetricSummary {
        name: name.to_string(),
        avg_pct: avg,
        min_pct: min,
        max_pct: max,
        note: note.to_string(),
    }
}

pub fn assess_video_quality(
    input_path: &str, cancel_flag: Arc<AtomicBool>,
) -> Result<QualityAssessment, String> {
    let video_info = get_full_video_info(input_path)?;
    if video_info.width < 8 || video_info.height < 8 {
        return Err(format!("Video too small for quality assessment: {}x{}", video_info.width, video_info.height));
    }

    let settings = crate::settings::load_settings();
    let timestamps = chunk_timestamps(video_info.duration, settings.chunk_count);
    let mut noise_pcts: Vec<f64> = Vec::new();
    let mut natural_pcts: Vec<f64> = Vec::new();
    let mut niqe_pcts: Vec<f64> = Vec::new();
    let mut sharp_pcts: Vec<f64> = Vec::new();
    let mut block_pcts: Vec<f64> = Vec::new();

    let brisque = BrisqueAssessor::new();
    let niqe = NiqeAssessor::new();
    let blur = AdvancedBlurDetector::new();
    let block = AdvancedBlockinessDetector::new();
    let noise_est = NoiseEstimator::new();

    let mut frames_used = 0usize;
    let total_planned = timestamps.len();

    info!("Quality: assessing {} ({}x{}, {:.0}s, {} chunks, {} frames)",
        input_path, video_info.width, video_info.height, video_info.duration, timestamps.len(), total_planned);

    for ts in &timestamps {
        if cancel_flag.load(Ordering::Relaxed) {
            return Err("Operation cancelled".to_string());
        }
        let frame = extract_gray_frame(
            input_path, *ts, video_info.width, video_info.height, cancel_flag.clone(),
        )?;

        if cancel_flag.load(Ordering::Relaxed) {
            return Err("Operation cancelled".to_string());
        }
        let m = assess_frame_metrics(&frame, &brisque, &niqe, &blur, &block);

        let noise = noise_est
            .estimate(&frame)
            .map(|s| noise_pct(s.score))
            .unwrap_or_else(|e| { warn!("Quality: noise estimation failed: {}", e); -1.0 });

        natural_pcts.push(m.natural_pct);
        if let Some(n) = m.niqe_pct {
            niqe_pcts.push(n);
        }
        noise_pcts.push(noise);
        sharp_pcts.push(m.sharp_pct);
        block_pcts.push(m.block_pct);

        frames_used += 1;
        info!(
            "Quality: frame {}/{} @ {:.1}s -> naturalness={:.0}%, noise-free={:.0}%, sharpness={:.0}% ({}), blockiness-free={:.0}%",
            frames_used, total_planned, ts, m.natural_pct, noise, m.sharp_pct, m.sharp_grade, m.block_pct
        );
    }

    if cancel_flag.load(Ordering::Relaxed) {
        return Err("Operation cancelled".to_string());
    }
    if natural_pcts.is_empty() {
        return Err("No frames were assessed".to_string());
    }

    let natural_agg = summarize(
        "Естественность (нет искажений)", &natural_pcts,
        "100 = выглядит как настоящее видео; <50 = заметные искажения",
    );
    let noise_agg = summarize(
        "Чистота от шума", &noise_pcts,
        "100 = без шума; <60 = заметный шум, <30 = сильный шум",
    );
    let sharp_agg = summarize(
        "Резкость", &sharp_pcts,
        "100 = очень резкое; <50 = размытое, <75 = слегка мягкое",
    );
    let block_agg = summarize(
        "Отсутствие блоков", &block_pcts,
        "100 = нет блочных артефактов; <60 = заметные блоки, <30 = сильные блоки",
    );

    let niqe_agg = if niqe_pcts.is_empty() {
        None
    } else {
        Some(summarize(
            "Естественность (NIQE, доп.)", &niqe_pcts,
            "100 = выглядит как настоящее видео; <50 = заметные искажения",
        ))
    };

    let mut verdict_parts: Vec<String> = Vec::new();
    if noise_agg.avg_pct < 30.0 {
        verdict_parts.push(format!("сильный шум ({:.0}%)", noise_agg.avg_pct));
    } else if noise_agg.avg_pct < 60.0 {
        verdict_parts.push(format!("заметный шум ({:.0}%)", noise_agg.avg_pct));
    }
    if sharp_agg.avg_pct < 50.0 {
        verdict_parts.push(format!("размытое изображение ({:.0}%)", sharp_agg.avg_pct));
    } else if sharp_agg.avg_pct < 75.0 {
        verdict_parts.push(format!("лёгкое размытие ({:.0}%)", sharp_agg.avg_pct));
    }
    if block_agg.avg_pct < 30.0 {
        verdict_parts.push(format!("сильные блочные артефакты ({:.0}%)", block_agg.avg_pct));
    } else if block_agg.avg_pct < 60.0 {
        verdict_parts.push(format!("заметные блочные артефакты ({:.0}%)", block_agg.avg_pct));
    }
    if natural_agg.avg_pct < 50.0 {
        verdict_parts.push(format!("низкая естественность ({:.0}%)", natural_agg.avg_pct));
    }

    info!("Quality: summary -> naturalness: avg={:.0}% [{}..{}]",
        natural_agg.avg_pct, natural_agg.min_pct, natural_agg.max_pct);
    info!("Quality: summary -> noise-free: avg={:.0}% [{}..{}]",
        noise_agg.avg_pct, noise_agg.min_pct, noise_agg.max_pct);
    info!("Quality: summary -> sharpness: avg={:.0}% [{}..{}]",
        sharp_agg.avg_pct, sharp_agg.min_pct, sharp_agg.max_pct);
    info!("Quality: summary -> blockiness-free: avg={:.0}% [{}..{}]",
        block_agg.avg_pct, block_agg.min_pct, block_agg.max_pct);

    let mut metrics = vec![natural_agg, noise_agg, sharp_agg, block_agg];
    if let Some(niqe) = niqe_agg {
        info!("Quality: summary -> niqe: avg={:.0}% [{}..{}]",
            niqe.avg_pct, niqe.min_pct, niqe.max_pct);
        metrics.push(niqe);
    }

    let grain = crate::video_processor::grain::estimate_grain(
        input_path,
        video_info.duration,
        settings.chunk_count,
        settings.chunk_duration as f64,
        cancel_flag.clone(),
    );
    match grain {
        Ok(g) => {
            let threshold = crate::vapoursynth::denoise::denoise_threshold_for(&settings, &video_info.video_type);
            let score_threshold = if threshold > 0.0 {
                threshold
            } else {
                crate::video_processor::grain::GRAIN_HEAVY_THRESHOLD
            };
            let avg = crate::video_processor::grain::grain_free_pct(g.ydif_median, score_threshold);
            let best = crate::video_processor::grain::grain_free_pct(g.ydif_min, score_threshold);
            let worst = crate::video_processor::grain::grain_free_pct(g.ydif_max, score_threshold);
            info!("Quality: summary -> grain (YDIF): median={:.2}, score={:.0}%", g.ydif_median, avg);
            let grain_agg = MetricSummary {
                name: "Зерно (YDIF)".to_string(),
                avg_pct: avg,
                min_pct: worst,
                max_pct: best,
                note: format!(
                    "медиана YDIF {:.1} по {} окнам; 100 = без зерна, <50 = заметное зерно",
                    g.ydif_median, g.windows_used
                ),
            };
            if grain_agg.avg_pct < 50.0 {
                verdict_parts.push(format!(
                    "зерно/шум ({:.0}%) - кодирование тратит битрейт на шум",
                    grain_agg.avg_pct
                ));
            }
            metrics.push(grain_agg);
        }
        Err(e) => warn!("Quality: grain analysis failed: {}", e),
    }

    let verdict = if verdict_parts.is_empty() {
        "Видео выглядит чистым: без шума, резкое, без блочных артефактов".to_string()
    } else {
        format!("Обнаружено: {}", verdict_parts.join(", "))
    };

    info!("Quality: verdict -> {}", verdict);

    Ok(QualityAssessment {
        file: input_path.to_string(),
        frames_used,
        metrics,
        verdict,
    })
}