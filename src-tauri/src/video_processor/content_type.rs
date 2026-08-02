use std::path::Path;
use std::process::Command;
use log::{info, warn};

use crate::ffmpeg::probe::VideoType;

const FRAME_COUNT: usize = 10;
const ANALYSIS_HEIGHT: u32 = 480;
const BLOCK_SIZE: usize = 8;
const EDGE_THRESHOLD: f64 = 30.0;
const QUANT_SHIFT: u8 = 3; // 256 / 32 = 8, shift by 3 bits
const THRESHOLD_ANIMATION: f32 = 0.7;
const THRESHOLD_LIVE_ACTION: f32 = 0.3;

pub fn detect_content_type(input_path: &str, duration: f64) -> VideoType {
    info!("Content type detection: analyzing {} frames from {}", FRAME_COUNT, input_path);

    let timestamps = generate_timestamps(duration);
    let path = input_path.to_string();

    let handles: Vec<_> = timestamps.into_iter().map(|ts| {
        let p = path.clone();
        std::thread::spawn(move || {
            match extract_and_analyze_frame(&p, ts) {
                Ok(score) => Some(score),
                Err(e) => {
                    warn!("Content type: frame at {:.1}s failed: {}", ts, e);
                    None
                }
            }
        })
    }).collect();

    let mut scores = Vec::new();
    for h in handles {
        if let Ok(Some(score)) = h.join() {
            scores.push(score);
        }
    }

    if scores.is_empty() {
        warn!("Content type: no frames analyzed, defaulting to LiveAction");
        return VideoType::LiveAction;
    }

    let avg_score = scores.iter().sum::<f32>() / scores.len() as f32;
    let result = if avg_score > THRESHOLD_ANIMATION {
        VideoType::Animation
    } else if avg_score < THRESHOLD_LIVE_ACTION {
        VideoType::LiveAction
    } else {
        VideoType::Mixed
    };

    info!("Content type result: {:?} (avg_score={:.3}, threshold_anim={:.1}, threshold_live={:.1})",
        result, avg_score, THRESHOLD_ANIMATION, THRESHOLD_LIVE_ACTION);

    result
}

fn generate_timestamps(duration: f64) -> Vec<f64> {
    if duration <= 0.0 {
        return vec![0.0];
    }
    if duration < 5.0 {
        return vec![duration * 0.5];
    }

    let step = duration / (FRAME_COUNT as f64 + 1.0);
    (1..=FRAME_COUNT).map(|i| step * i as f64).collect()
}

fn extract_and_analyze_frame(input_path: &str, timestamp: f64) -> Result<f32, String> {
    let tmp_dir = std::env::temp_dir();
    let ppm_path = tmp_dir.join(format!("content_detect_{}_{}.ppm", std::process::id(), (timestamp * 1000.0) as u64));
    let ppm_str = ppm_path.to_string_lossy().to_string();

    let ffmpeg_path = crate::settings::get_actual_ffmpeg_path();
    let mut cmd = Command::new(&ffmpeg_path);
    cmd.args([
        "-y", "-ss", &format!("{:.3}", timestamp),
        "-i", input_path,
        "-vf", &format!("scale=-1:{}:flags=bicubic", ANALYSIS_HEIGHT),
        "-frames:v", "1",
        "-pix_fmt", "rgb24",
        &ppm_str,
    ]);
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x08000000);
    }
    let output = cmd.output()
        .map_err(|e| format!("ffmpeg launch failed: {}", e))?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        let _ = std::fs::remove_file(&ppm_path);
        return Err(format!("ffmpeg exited with {}: {}", output.status, stderr.lines().last().unwrap_or("unknown error")));
    }

    let img = image::open(&ppm_path)
        .map_err(|e| {
            let _ = std::fs::remove_file(&ppm_path);
            format!("failed to open PPM: {}", e)
        })?;
    let _ = std::fs::remove_file(&ppm_path);

    let rgb = img.to_rgb8();
    let (w, h) = rgb.dimensions();
    let pixels: Vec<[u8; 3]> = rgb.pixels().map(|p| [p[0], p[1], p[2]]).collect();

    let dispersion_score = analyze_color_dispersion(&pixels, w as usize, h as usize);
    let edge_score = analyze_edge_density(&pixels, w as usize, h as usize);
    let color_score = analyze_unique_colors(&pixels);
    let hist_score = analyze_histogram_peaks(&pixels);

    let combined = 0.30 * dispersion_score + 0.30 * edge_score + 0.20 * color_score + 0.20 * hist_score;

    Ok(combined)
}

fn analyze_color_dispersion(pixels: &[[u8; 3]], w: usize, h: usize) -> f32 {
    let mut flat_blocks = 0;
    let mut total_blocks = 0;

    for by in (0..h).step_by(BLOCK_SIZE) {
        for bx in (0..w).step_by(BLOCK_SIZE) {
            let block_w = (w - bx).min(BLOCK_SIZE);
            let block_h = (h - by).min(BLOCK_SIZE);
            if block_w < 2 || block_h < 2 {
                continue;
            }

            let mut sum_r: u64 = 0;
            let mut sum_g: u64 = 0;
            let mut sum_b: u64 = 0;
            let mut count = 0u64;

            for y in by..by + block_h {
                for x in bx..bx + block_w {
                    let p = pixels[y * w + x];
                    sum_r += p[0] as u64;
                    sum_g += p[1] as u64;
                    sum_b += p[2] as u64;
                    count += 1;
                }
            }

            let mean_r = sum_r as f64 / count as f64;
            let mean_g = sum_g as f64 / count as f64;
            let mean_b = sum_b as f64 / count as f64;

            let mut var: f64 = 0.0;
            for y in by..by + block_h {
                for x in bx..bx + block_w {
                    let p = pixels[y * w + x];
                    let dr = p[0] as f64 - mean_r;
                    let dg = p[1] as f64 - mean_g;
                    let db = p[2] as f64 - mean_b;
                    var += dr * dr + dg * dg + db * db;
                }
            }
            var /= count as f64 * 3.0;
            let std_dev = var.sqrt();

            total_blocks += 1;
            if std_dev < 5.0 {
                flat_blocks += 1;
            }
        }
    }

    if total_blocks == 0 {
        return 0.0;
    }
    flat_blocks as f32 / total_blocks as f32
}

fn analyze_edge_density(pixels: &[[u8; 3]], w: usize, h: usize) -> f32 {
    if w < 3 || h < 3 {
        return 0.0;
    }

    let to_luma = |p: &[u8; 3]| -> f64 {
        0.299 * p[0] as f64 + 0.587 * p[1] as f64 + 0.114 * p[2] as f64
    };

    let mut edge_pixels = 0usize;
    let mut total_pixels = 0usize;

    for y in 1..h - 1 {
        for x in 1..w - 1 {
            let tl = to_luma(&pixels[(y - 1) * w + (x - 1)]);
            let tc = to_luma(&pixels[(y - 1) * w + x]);
            let tr = to_luma(&pixels[(y - 1) * w + (x + 1)]);
            let ml = to_luma(&pixels[y * w + (x - 1)]);
            let mr = to_luma(&pixels[y * w + (x + 1)]);
            let bl = to_luma(&pixels[(y + 1) * w + (x - 1)]);
            let bc = to_luma(&pixels[(y + 1) * w + x]);
            let br = to_luma(&pixels[(y + 1) * w + (x + 1)]);

            let gx = -tl - 2.0 * ml - bl + tr + 2.0 * mr + br;
            let gy = -tl - 2.0 * tc - tr + bl + 2.0 * bc + br;
            let magnitude = (gx * gx + gy * gy).sqrt();

            total_pixels += 1;
            if magnitude > EDGE_THRESHOLD {
                edge_pixels += 1;
            }
        }
    }

    if total_pixels == 0 {
        return 0.0;
    }
    edge_pixels as f32 / total_pixels as f32
}

fn analyze_unique_colors(pixels: &[[u8; 3]]) -> f32 {
    use std::collections::HashSet;

    let mut unique = HashSet::new();
    for p in pixels {
        let qr = p[0] >> QUANT_SHIFT;
        let qg = p[1] >> QUANT_SHIFT;
        let qb = p[2] >> QUANT_SHIFT;
        unique.insert((qr, qg, qb));
    }

    let total = pixels.len() as f64;
    let unique_ratio = unique.len() as f64 / total;

    if unique_ratio < 0.10 {
        1.0
    } else if unique_ratio < 0.25 {
        0.8
    } else if unique_ratio < 0.45 {
        0.4
    } else {
        0.0
    }
}

fn analyze_histogram_peaks(pixels: &[[u8; 3]]) -> f32 {
    let mut hist = [0u32; 256];
    for p in pixels {
        let luma = (0.299 * p[0] as f64 + 0.587 * p[1] as f64 + 0.114 * p[2] as f64) as u8;
        hist[luma as usize] += 1;
    }

    let total = pixels.len() as f64;
    let mean = total / 256.0;
    if mean <= 0.0 {
        return 0.0;
    }

    let variance: f64 = hist.iter().map(|&c| {
        let diff = c as f64 - mean;
        diff * diff
    }).sum::<f64>() / 256.0;

    let cv = variance.sqrt() / mean;

    if cv > 3.0 {
        1.0
    } else if cv > 2.0 {
        0.7
    } else if cv > 1.0 {
        0.3
    } else {
        0.0
    }
}
