use std::sync::Arc;
use std::sync::atomic::AtomicBool;
use log::{info, warn};
use image::GenericImageView;

use crate::ffmpeg::probe::VideoType;
use crate::ffmpeg::encode::{calculate_vmaf, chunk_timeline};
use crate::ffmpeg::core::run_command_simple;
use crate::process_control::PidTracker;

pub struct QualityCheckResult {
    pub score: f64,
    pub metric: String,
}

pub fn check_quality(
    original_path: &str,
    encoded_path: &str,
    video_type: &VideoType,
    start_time: f64,
    duration: f64,
    n_subsample: usize,
    width: usize,
    height: usize,
    video_info: &crate::ffmpeg::probe::VideoInfo,
    force_vfr_fix: bool,
    pad_applied: bool,
    ignore_noise: bool,
    target_vmaf: f64,
    target_ssimulacra2: f64,
    cancel_flag: Arc<AtomicBool>,
    child_pid: Option<PidTracker>,
    metric_override: Option<String>,
) -> Result<QualityCheckResult, String> {
    let use_ssim = match metric_override.as_deref() {
        Some("SSIMULACRA2") => true,
        Some("VMAF") => false,
        _ => matches!(video_type, VideoType::Animation | VideoType::Rendered),
    };

    if use_ssim {
        info!("Quality check: using SSIMULACRA2");
        let score = calculate_ssimulacra2(
            original_path, encoded_path, start_time, duration,
            width, height, force_vfr_fix, ignore_noise, video_info,
            cancel_flag, child_pid,
        )?;
        let passed = score >= target_ssimulacra2;
        info!("Quality check: SSIMULACRA2={:.1} (target > {:.1}) {}",
            score, target_ssimulacra2, if passed { "PASSED" } else { "FAILED" });
        Ok(QualityCheckResult {
            score,
            metric: "SSIMULACRA2".to_string(),
        })
    } else {
        info!("Quality check: using VMAF (model vmaf_v0.6.1neg)");
        let score = calculate_vmaf(
            original_path, encoded_path, start_time, duration,
            n_subsample, width, video_info, force_vfr_fix, pad_applied,
            ignore_noise, cancel_flag, child_pid,
        );
        if score < 0.0 {
            return Err(format!("VMAF calculation failed (score={})", score));
        }
        let passed = score >= target_vmaf;
        info!("Quality check: VMAF={:.1} (target > {:.1}) {}",
            score, target_vmaf, if passed { "PASSED" } else { "FAILED" });
        Ok(QualityCheckResult {
            score,
            metric: "VMAF".to_string(),
        })
    }
}

fn calculate_ssimulacra2(
    original_path: &str,
    encoded_path: &str,
    start_time: f64,
    duration: f64,
    width: usize,
    height: usize,
    force_vfr_fix: bool,
    ignore_noise: bool,
    video_info: &crate::ffmpeg::probe::VideoInfo,
    cancel_flag: Arc<AtomicBool>,
    child_pid: Option<PidTracker>,
) -> Result<f64, String> {
    let tmp_dir = std::env::temp_dir();
    let ts_ms = (start_time * 1000.0) as u64;
    let orig_ppm = tmp_dir.join(format!("ssim_orig_{}_{}.ppm", std::process::id(), ts_ms));
    let dist_ppm = tmp_dir.join(format!("ssim_dist_{}_{}.ppm", std::process::id(), ts_ms));

    let orig_str = orig_ppm.to_string_lossy().to_string();
    let dist_str = dist_ppm.to_string_lossy().to_string();

    let needs_fix = force_vfr_fix || video_info.needs_vfr_fix;
    extract_source_reference_frame(
        original_path, &orig_str, start_time, duration,
        width, height, needs_fix, video_info.vfr_fix_fps, ignore_noise,
        cancel_flag.clone(), child_pid.clone(),
    )?;

    let encoded_timestamp = if duration > 0.0 { duration / 2.0 } else { 0.0 };
    extract_frame_for_ssim(encoded_path, &dist_str, encoded_timestamp, width, height, ignore_noise, cancel_flag.clone(), child_pid)?;

    let orig_img = image::open(&orig_ppm).map_err(|e| {
        let _ = std::fs::remove_file(&orig_ppm);
        let _ = std::fs::remove_file(&dist_ppm);
        format!("Failed to load original frame: {}", e)
    })?;
    let dist_img = image::open(&dist_ppm).map_err(|e| {
        let _ = std::fs::remove_file(&orig_ppm);
        let _ = std::fs::remove_file(&dist_ppm);
        format!("Failed to load distorted frame: {}", e)
    })?;
    let _ = std::fs::remove_file(&orig_ppm);
    let _ = std::fs::remove_file(&dist_ppm);

    let (w1, h1) = orig_img.dimensions();
    let (w2, h2) = dist_img.dimensions();
    if w1 != w2 || h1 != h2 {
        warn!("SSIMULACRA2: dimension mismatch {}x{} vs {}x{}, scaling distorted", w1, h1, w2, h2);
    }

    let orig_rgb = image_to_yuvxyb_rgb(&orig_img);
    let dist_rgb = image_to_yuvxyb_rgb(&dist_img);

    let score = ssimulacra2::compute_frame_ssimulacra2(orig_rgb, dist_rgb)
        .map_err(|e| format!("SSIMULACRA2 computation failed: {}", e))?;

    if cancel_flag.load(std::sync::atomic::Ordering::Relaxed) {
        return Err("Cancelled".to_string());
    }

    Ok(score)
}

fn build_ssim_grade_filters(
    orig_width: usize,
    orig_height: usize,
    ignore_noise: bool,
) -> Vec<String> {
    let mut vf_filters = Vec::new();

    // Мощный фильтр для игнора 3D CGI рендер-шума (убивает микротекстуры, оставляет макро-структуру)
    if ignore_noise {
        vf_filters.push("hqdn3d=12:9:14:12,gblur=sigma=0.6".to_string());
    }

    // Возвращаем спасительный даунскейл (скорость + низкочастотный фильтр для человеческого зрения)
    if orig_width > 1280 {
        vf_filters.push("scale=1280:-1:flags=bicubic".to_string());
    } else if orig_width > 0 && orig_height > 0 {
        vf_filters.push(format!("scale={}:{}", orig_width, orig_height));
    } else {
        vf_filters.push("scale=-1:720:flags=bicubic".to_string());
    }

    vf_filters
}

fn extend_color_force(cmd: &mut Vec<String>) {
    // Битый VUI у некоторых файлов несёт prim:reserved/trc:reserved, из-за чего swscaler
    // падает с -129 при конвертации в rgb24. Принудительно выставляем bt709 на входе.
    cmd.extend([
        "-color_primaries".to_string(), "bt709".to_string(),
        "-color_trc".to_string(), "bt709".to_string(),
        "-colorspace".to_string(), "bt709".to_string(),
    ]);
}

fn extract_source_reference_frame(
    input_path: &str,
    output_path: &str,
    source_start: f64,
    duration: f64,
    orig_width: usize,
    orig_height: usize,
    needs_fix: bool,
    fix_fps: f64,
    ignore_noise: bool,
    cancel_flag: Arc<AtomicBool>,
    child_pid: Option<PidTracker>,
) -> Result<(), String> {
    // Reference-кадр берём из ТОЙ ЖЕ цепочки, что кодируется чанк (trim+setpts),
    // чтобы обе стороны сидели на одной нормализованной тайм-линии (фикс рассинхрона VFR).
    let (fast_seek, trim_start) = chunk_timeline(source_start);

    let mut vf_filters = vec![
        "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709".to_string(),
        format!("trim=start={:.3}:duration={:.3}", trim_start, duration),
        "setpts=PTS-STARTPTS".to_string(),
    ];
    if needs_fix {
        vf_filters.push(format!("fps={}", fix_fps));
    }
    vf_filters.extend(build_ssim_grade_filters(orig_width, orig_height, ignore_noise));

    let mut cmd = vec![
        "ffmpeg".to_string(), "-y".to_string(),
        "-ss".to_string(), format!("{:.3}", fast_seek),
    ];
    extend_color_force(&mut cmd);
    cmd.extend(["-i".to_string(), input_path.to_string()]);
    cmd.extend(["-vf".to_string(), vf_filters.join(",")]);
    cmd.extend([
        "-ss".to_string(), format!("{:.3}", duration / 2.0),
        "-frames:v".to_string(), "1".to_string(),
        "-pix_fmt".to_string(), "rgb24".to_string(),
        output_path.to_string(),
    ]);

    let result = run_command_simple(&cmd, cancel_flag, child_pid);

    if !result.success {
        return Err(format!("ffmpeg frame extraction failed: {}", result.message));
    }

    Ok(())
}

fn extract_frame_for_ssim(
    input_path: &str,
    output_path: &str,
    timestamp: f64,
    orig_width: usize,
    orig_height: usize,
    ignore_noise: bool,
    cancel_flag: Arc<AtomicBool>,
    child_pid: Option<PidTracker>,
) -> Result<(), String> {
    let mut vf_filters = vec!["setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709".to_string()];
    
    // Мощный фильтр для игнора 3D CGI рендер-шума (убивает микротекстуры, оставляет макро-структуру)
    if ignore_noise {
        vf_filters.push("hqdn3d=12:9:14:12,gblur=sigma=0.6".to_string());
    }

    // Возвращаем спасительный даунскейл (скорость + низкочастотный фильтр для человеческого зрения)
    if orig_width > 1280 {
        vf_filters.push("scale=1280:-1:flags=bicubic".to_string());
    } else if orig_width > 0 && orig_height > 0 {
        vf_filters.push(format!("scale={}:{}", orig_width, orig_height));
    } else {
        vf_filters.push("scale=-1:720:flags=bicubic".to_string());
    }

    let mut cmd = vec![
        "ffmpeg".to_string(), "-y".to_string(),
        "-ss".to_string(), format!("{:.3}", timestamp),
    ];
    extend_color_force(&mut cmd);
    cmd.extend(["-i".to_string(), input_path.to_string()]);

    if !vf_filters.is_empty() {
        cmd.extend(["-vf".to_string(), vf_filters.join(",")]);
    }

    cmd.extend([
        "-frames:v".to_string(), "1".to_string(),
        "-pix_fmt".to_string(), "rgb24".to_string(),
        output_path.to_string(),
    ]);

    let result = run_command_simple(&cmd, cancel_flag, child_pid);

    if !result.success {
        return Err(format!("ffmpeg frame extraction failed: {}", result.message));
    }

    Ok(())
}

fn image_to_yuvxyb_rgb(img: &image::DynamicImage) -> ssimulacra2::Rgb {
    let rgb8 = img.to_rgb8();
    let (w, h) = rgb8.dimensions();
    let data: Vec<[f32; 3]> = rgb8.pixels().map(|p| {
        [p[0] as f32 / 255.0, p[1] as f32 / 255.0, p[2] as f32 / 255.0]
    }).collect();

    ssimulacra2::Rgb::new(
        data,
        w as usize,
        h as usize,
        ssimulacra2::TransferCharacteristic::SRGB,
        ssimulacra2::ColorPrimaries::BT709,
    ).expect("Failed to create Rgb for SSIMULACRA2")
}
