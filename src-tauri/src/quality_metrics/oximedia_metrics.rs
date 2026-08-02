use std::time::Instant;
use log::{info, warn};

use super::MetricResult;

fn dynamic_image_to_frame(img: &image::DynamicImage) -> Result<oximedia_quality::Frame, String> {
    let gray = img.to_luma8();
    let (w, h) = gray.dimensions();
    let raw = gray.into_raw();

    let frame = oximedia_quality::Frame {
        width: w as usize,
        height: h as usize,
        format: oximedia_core::PixelFormat::Gray8,
        planes: vec![raw],
        strides: vec![w as usize],
    };

    Ok(frame)
}

pub fn compute_oximedia_lpips(
    orig_img: &image::DynamicImage,
    dist_img: &image::DynamicImage,
) -> MetricResult {
    let t0 = Instant::now();

    let orig_frame = match dynamic_image_to_frame(orig_img) {
        Ok(f) => f,
        Err(e) => {
            warn!("Oximedia LPIPS frame creation failed: {}", e);
            return MetricResult {
                metric: "LPIPS (oximedia)".to_string(),
                score: 0.0,
                unit: "0-1".to_string(),
                passed: false,
                target: 0.3,
                compute_ms: 0,
                percent: 0.0,
            };
        }
    };
    let dist_frame = match dynamic_image_to_frame(dist_img) {
        Ok(f) => f,
        Err(e) => {
            warn!("Oximedia LPIPS frame creation failed: {}", e);
            return MetricResult {
                metric: "LPIPS (oximedia)".to_string(),
                score: 0.0,
                unit: "0-1".to_string(),
                passed: false,
                target: 0.3,
                compute_ms: 0,
                percent: 0.0,
            };
        }
    };

    let calc = oximedia_quality::lpips::LpipsCalculator::new(
        oximedia_quality::lpips::LpipsConfig::default(),
    );

    match calc.compute(&orig_frame, &dist_frame) {
        Ok(result) => {
            let score = result.distance;
            let ms = t0.elapsed().as_millis() as u64;
            let percent = super::score_to_percent("LPIPS (oximedia)", score);
            info!("Oximedia LPIPS: {:.4} = {:.1}% ({}ms)", score, percent, ms);
            MetricResult {
                metric: "LPIPS (oximedia)".to_string(),
                score,
                unit: "0-1".to_string(),
                passed: score <= 0.3,
                target: 0.3,
                compute_ms: ms,
                percent,
            }
        }
        Err(e) => {
            let ms = t0.elapsed().as_millis() as u64;
            warn!("Oximedia LPIPS failed: {}", e);
            MetricResult {
                metric: "LPIPS (oximedia)".to_string(),
                score: 0.0,
                unit: "0-1".to_string(),
                passed: false,
                target: 0.3,
                compute_ms: ms,
                percent: 0.0,
            }
        }
    }
}

/// Compute VMAF (0-100) and VIF (0-1) via the oximedia-quality crate.
pub fn compute_oximedia_metrics(
    orig_img: &image::DynamicImage,
    dist_img: &image::DynamicImage,
) -> Vec<MetricResult> {
    let mut results = Vec::new();

    let orig_frame = match dynamic_image_to_frame(orig_img) {
        Ok(f) => f,
        Err(e) => {
            warn!("Oximedia frame creation failed: {}", e);
            return results;
        }
    };
    let dist_frame = match dynamic_image_to_frame(dist_img) {
        Ok(f) => f,
        Err(e) => {
            warn!("Oximedia frame creation failed: {}", e);
            return results;
        }
    };

    // VMAF: 0-100, higher is better (already a percentage-like score)
    let t0 = Instant::now();
    match oximedia_quality::VmafCalculator::new().calculate(&orig_frame, &dist_frame) {
        Ok(result) => {
            let score = result.score;
            let ms = t0.elapsed().as_millis() as u64;
            let percent = super::score_to_percent("VMAF", score);
            info!("Oximedia VMAF: {:.2} = {:.1}% ({}ms)", score, percent, ms);
            results.push(MetricResult {
                metric: "VMAF".to_string(),
                score,
                unit: "0-100".to_string(),
                passed: score >= 80.0,
                target: 80.0,
                compute_ms: ms,
                percent,
            });
        }
        Err(e) => warn!("Oximedia VMAF failed: {}", e),
    }

    // VIF: 0-1, higher is better
    let t0 = Instant::now();
    match oximedia_quality::VifCalculator::new().calculate(&orig_frame, &dist_frame) {
        Ok(result) => {
            let score = result.score;
            let ms = t0.elapsed().as_millis() as u64;
            let percent = super::score_to_percent("VIF", score);
            info!("Oximedia VIF: {:.4} = {:.1}% ({}ms)", score, percent, ms);
            results.push(MetricResult {
                metric: "VIF".to_string(),
                score,
                unit: "0-1".to_string(),
                passed: score >= 0.9,
                target: 0.9,
                compute_ms: ms,
                percent,
            });
        }
        Err(e) => warn!("Oximedia VIF failed: {}", e),
    }

    results
}
