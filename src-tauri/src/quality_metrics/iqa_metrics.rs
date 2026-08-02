use std::time::Instant;
use log::{info, warn};

use super::MetricResult;

pub fn compute_iqa_metrics(
    orig_img: &image::DynamicImage,
    dist_img: &image::DynamicImage,
) -> Vec<MetricResult> {
    let mut results = Vec::new();

    let orig_rgb8 = orig_img.to_rgb8();
    let dist_rgb8 = dist_img.to_rgb8();

    let (w1, h1) = orig_rgb8.dimensions();
    let (w2, h2) = dist_rgb8.dimensions();
    if w1 != w2 || h1 != h2 {
        warn!("IQA metrics: dimension mismatch {}x{} vs {}x{}", w1, h1, w2, h2);
    }

    let orig_data: Vec<u8> = orig_rgb8.as_raw().to_vec();
    let dist_data: Vec<u8> = dist_rgb8.as_raw().to_vec();

    let orig = match iqa::Image::srgb8(w1, h1, orig_data) {
        Ok(img) => img,
        Err(e) => {
            warn!("IQA: failed to create orig image: {}", e);
            return results;
        }
    };
    let dist = match iqa::Image::srgb8(w2, h2, dist_data) {
        Ok(img) => img,
        Err(e) => {
            warn!("IQA: failed to create dist image: {}", e);
            return results;
        }
    };

    let t0 = Instant::now();
    match iqa::ssim(&orig, &dist, iqa::SsimOptions::default()) {
        Ok(score) => {
            let ms = t0.elapsed().as_millis() as u64;
            let percent = super::score_to_percent("SSIM", score);
            info!("IQA SSIM: {:.4} = {:.1}% ({}ms)", score, percent, ms);
            results.push(MetricResult {
                metric: "SSIM".to_string(),
                score,
                unit: "0-1".to_string(),
                passed: score >= 0.95,
                target: 0.95,
                compute_ms: ms,
                percent,
            });
        }
        Err(e) => warn!("IQA SSIM failed: {}", e),
    }

    let t0 = Instant::now();
    match iqa::msssim(&orig, &dist, iqa::MsssimOptions::default()) {
        Ok(score) => {
            let ms = t0.elapsed().as_millis() as u64;
            let percent = super::score_to_percent("MS-SSIM", score);
            info!("IQA MS-SSIM: {:.4} = {:.1}% ({}ms)", score, percent, ms);
            results.push(MetricResult {
                metric: "MS-SSIM".to_string(),
                score,
                unit: "0-1".to_string(),
                passed: score >= 0.95,
                target: 0.95,
                compute_ms: ms,
                percent,
            });
        }
        Err(e) => warn!("IQA MS-SSIM failed: {}", e),
    }

    let t0 = Instant::now();
    match iqa::dssim(&orig, &dist, iqa::DssimOptions::default()) {
        Ok(score) => {
            let ms = t0.elapsed().as_millis() as u64;
            let percent = super::score_to_percent("DSSIM", score);
            info!("IQA DSSIM: {:.4} = {:.1}% ({}ms)", score, percent, ms);
            results.push(MetricResult {
                metric: "DSSIM".to_string(),
                score,
                unit: "0-0.5".to_string(),
                passed: score <= 0.05,
                target: 0.05,
                compute_ms: ms,
                percent,
            });
        }
        Err(e) => warn!("IQA DSSIM failed: {}", e),
    }

    let t0 = Instant::now();
    match iqa::butteraugli(&orig, &dist, iqa::ButteraugliOptions::default()) {
        Ok(score) => {
            let ms = t0.elapsed().as_millis() as u64;
            let percent = super::score_to_percent("Butteraugli", score);
            info!("IQA Butteraugli: {:.4} = {:.1}% ({}ms)", score, percent, ms);
            results.push(MetricResult {
                metric: "Butteraugli".to_string(),
                score,
                unit: "0-inf".to_string(),
                passed: score <= 1.5,
                target: 1.5,
                compute_ms: ms,
                percent,
            });
        }
        Err(e) => warn!("IQA Butteraugli failed: {}", e),
    }

    let t0 = Instant::now();
    match iqa::ciede2000(&orig, &dist, iqa::Ciede2000Options::default()) {
        Ok(score) => {
            let ms = t0.elapsed().as_millis() as u64;
            let percent = super::score_to_percent("CIEDE2000", score);
            info!("IQA CIEDE2000: {:.4} = {:.1}% ({}ms)", score, percent, ms);
            results.push(MetricResult {
                metric: "CIEDE2000".to_string(),
                score,
                unit: "0-100".to_string(),
                passed: score <= 2.0,
                target: 2.0,
                compute_ms: ms,
                percent,
            });
        }
        Err(e) => warn!("IQA CIEDE2000 failed: {}", e),
    }

    let t0 = Instant::now();
    match iqa::psnr(&orig, &dist, iqa::PsnrOptions::default()) {
        Ok(score) => {
            let ms = t0.elapsed().as_millis() as u64;
            let percent = super::score_to_percent("PSNR", score);
            info!("IQA PSNR: {:.2} dB = {:.1}% ({}ms)", score, percent, ms);
            results.push(MetricResult {
                metric: "PSNR".to_string(),
                score,
                unit: "dB".to_string(),
                passed: score >= 30.0,
                target: 30.0,
                compute_ms: ms,
                percent,
            });
        }
        Err(e) => warn!("IQA PSNR failed: {}", e),
    }

    let t0 = Instant::now();
    match iqa::iwssim(&orig, &dist, iqa::IwssimOptions::default()) {
        Ok(score) => {
            let ms = t0.elapsed().as_millis() as u64;
            let percent = super::score_to_percent("IW-SSIM", score);
            info!("IQA IW-SSIM: {:.4} = {:.1}% ({}ms)", score, percent, ms);
            results.push(MetricResult {
                metric: "IW-SSIM".to_string(),
                score,
                unit: "0-1".to_string(),
                passed: score >= 0.95,
                target: 0.95,
                compute_ms: ms,
                percent,
            });
        }
        Err(e) => warn!("IQA IW-SSIM failed: {}", e),
    }

    let t0 = Instant::now();
    match iqa::psnr_hvs_m(&orig, &dist, iqa::PsnrHvsOptions::default()) {
        Ok(score) => {
            let ms = t0.elapsed().as_millis() as u64;
            let percent = super::score_to_percent("PSNR-HVS-M", score);
            info!("IQA PSNR-HVS-M: {:.2} dB = {:.1}% ({}ms)", score, percent, ms);
            results.push(MetricResult {
                metric: "PSNR-HVS-M".to_string(),
                score,
                unit: "dB".to_string(),
                passed: score >= 30.0,
                target: 30.0,
                compute_ms: ms,
                percent,
            });
        }
        Err(e) => warn!("IQA PSNR-HVS-M failed: {}", e),
    }

    results
}
