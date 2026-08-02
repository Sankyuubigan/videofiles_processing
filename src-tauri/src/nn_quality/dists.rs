use std::process::Command;
use std::sync::Arc;
use std::sync::atomic::AtomicBool;
use std::time::Instant;
use log::info;
use ort::value::Tensor;

use super::session;

/// Calculate DISTS score between original and distorted video frames.
/// Returns a score where LOWER means more similar (0 = identical).
///
/// DISTS range: [0, 1] approximately
/// - 0.0 = identical
/// - 0.05 = very similar
/// - 0.15 = noticeable difference
/// - 0.3+ = very different
///
/// DISTS is better than LPIPS for compression because it separately measures
/// structure loss and texture loss, which aligns with human perception of
/// compression artifacts.
pub fn calculate_dists(
    original_path: &str,
    encoded_path: &str,
    start_time: f64,
    duration: f64,
    width: usize,
    height: usize,
    ignore_noise: bool,
    cancel_flag: Arc<AtomicBool>,
) -> Result<f64, String> {
    let t0 = Instant::now();

    let tmp_dir = std::env::temp_dir();
    let ts_ms = (start_time * 1000.0) as u64;
    let orig_png = tmp_dir.join(format!("dists_orig_{}_{}.png", std::process::id(), ts_ms));
    let dist_png = tmp_dir.join(format!("dists_dist_{}_{}.png", std::process::id(), ts_ms));

    let orig_str = orig_png.to_string_lossy().to_string();
    let dist_str = dist_png.to_string_lossy().to_string();

    // Extract frames from both videos
    let orig_timestamp = start_time + if duration > 0.0 { duration / 2.0 } else { 0.0 };
    extract_frame_for_dists(
        original_path,
        &orig_str,
        orig_timestamp,
        width,
        height,
        ignore_noise,
    )?;

    if cancel_flag.load(std::sync::atomic::Ordering::Relaxed) {
        let _ = std::fs::remove_file(&orig_png);
        let _ = std::fs::remove_file(&dist_png);
        return Err("Cancelled".to_string());
    }

    let encoded_timestamp = if duration > 0.0 { duration / 2.0 } else { 0.0 };
    extract_frame_for_dists(
        encoded_path,
        &dist_str,
        encoded_timestamp,
        width,
        height,
        ignore_noise,
    )?;

    // Load images and preprocess
    let orig_img = image::open(&orig_png).map_err(|e| {
        let _ = std::fs::remove_file(&orig_png);
        let _ = std::fs::remove_file(&dist_png);
        format!("Failed to load original frame for DISTS: {}", e)
    })?;
    let dist_img = image::open(&dist_png).map_err(|e| {
        let _ = std::fs::remove_file(&orig_png);
        let _ = std::fs::remove_file(&dist_png);
        format!("Failed to load distorted frame for DISTS: {}", e)
    })?;
    let _ = std::fs::remove_file(&orig_png);
    let _ = std::fs::remove_file(&dist_png);

    let preprocess_start = Instant::now();

    let target_size = 480;
    let (orig_shape, orig_data) = image_to_dists_tensor(&orig_img, target_size)?;
    let (dist_shape, dist_data) = image_to_dists_tensor(&dist_img, target_size)?;

    info!(
        "DISTS preprocess: {}ms",
        preprocess_start.elapsed().as_millis()
    );

    if cancel_flag.load(std::sync::atomic::Ordering::Relaxed) {
        return Err("Cancelled".to_string());
    }

    // Run inference
    session::ensure_dists_loaded()?;

    let infer_start = Instant::now();

    let score = {
        let mut guard = session::DISTS_SESSION.lock().map_err(|e| {
            format!("Failed to lock DISTS session: {}", e)
        })?;
        let sess = guard.as_mut().ok_or("DISTS session not loaded")?;

        let input_names: Vec<String> = sess.inputs().iter().map(|i| i.name().to_string()).collect();

        info!("DISTS model inputs: {:?}", input_names);

        let outputs = if input_names.len() >= 2 {
            let orig_ort = Tensor::from_array((orig_shape, orig_data.into_boxed_slice()))
                .map_err(|e| format!("Failed to create ort tensor for DISTS orig: {}", e))?;
            let dist_ort = Tensor::from_array((dist_shape, dist_data.into_boxed_slice()))
                .map_err(|e| format!("Failed to create ort tensor for DISTS dist: {}", e))?;
            sess.run(ort::inputs![
                input_names[0].as_str() => orig_ort,
                input_names[1].as_str() => dist_ort
            ])
            .map_err(|e| format!("DISTS inference failed: {}", e))?
        } else if input_names.len() == 1 {
            let mut combined_data = orig_data;
            combined_data.extend_from_slice(&dist_data);
            let combined_shape = vec![2i64, 3, orig_shape[2], orig_shape[3]];
            let combined_ort = Tensor::from_array((combined_shape, combined_data.into_boxed_slice()))
                .map_err(|e| format!("Failed to create ort tensor for DISTS combined: {}", e))?;
            sess.run(ort::inputs![combined_ort])
                .map_err(|e| format!("DISTS inference failed: {}", e))?
        } else {
            return Err("DISTS model has no inputs".to_string());
        };

        if outputs.len() == 0 {
            return Err("DISTS model produced no outputs".to_string());
        }

        let (_shape, data) = outputs[0].try_extract_tensor::<f32>()
            .map_err(|e| format!("Failed to extract DISTS output: {}", e))?;
        *data.first().ok_or("DISTS output is empty")? as f64
    };

    let inference_ms = infer_start.elapsed().as_millis() as u64;
    info!("DISTS inference: {}ms", inference_ms);

    let total_ms = t0.elapsed().as_millis() as u64;
    info!(
        "DISTS total: {}ms (preprocess + inference + postprocess), score={:.4}",
        total_ms, score
    );

    Ok(score)
}

/// Convert an image to DISTS tensor format: [1, 3, H, W] normalized for VGG16
/// Returns (shape as Vec<i64>, flat data as Vec<f32>)
fn image_to_dists_tensor(
    img: &image::DynamicImage,
    target_size: u32,
) -> Result<(Vec<i64>, Vec<f32>), String> {
    let resized = img.resize_exact(target_size, target_size, image::imageops::FilterType::Lanczos3);
    let rgb = resized.to_rgb8();
    let (w, h) = rgb.dimensions();

    // VGG16 normalization: mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]
    let mean = [0.485f32, 0.456, 0.406];
    let std = [0.229f32, 0.224, 0.225];

    let mut data = Vec::with_capacity((3 * h * w) as usize);
    for y in 0..h {
        for x in 0..w {
            let p = rgb.get_pixel(x, y);
            data.push((p[0] as f32 / 255.0 - mean[0]) / std[0]);
            data.push((p[1] as f32 / 255.0 - mean[1]) / std[1]);
            data.push((p[2] as f32 / 255.0 - mean[2]) / std[2]);
        }
    }

    let shape = vec![1i64, 3, h as i64, w as i64];
    Ok((shape, data))
}

/// Extract a frame from video using ffmpeg for DISTS analysis
fn extract_frame_for_dists(
    input_path: &str,
    output_path: &str,
    timestamp: f64,
    _orig_width: usize,
    _orig_height: usize,
    ignore_noise: bool,
) -> Result<(), String> {
    let mut vf_filters = Vec::new();

    if ignore_noise {
        vf_filters.push("hqdn3d=12:9:14:12,gblur=sigma=0.6".to_string());
    }

    vf_filters.push("scale=480:480:flags=lanczos".to_string());

    let ffmpeg_path = crate::settings::get_actual_ffmpeg_path();
    let mut cmd = Command::new(&ffmpeg_path);

    cmd.args(["-y", "-ss", &format!("{:.3}", timestamp), "-i", input_path]);

    if !vf_filters.is_empty() {
        cmd.args(["-vf", &vf_filters.join(",")]);
    }

    cmd.args([
        "-frames:v", "1",
        "-pix_fmt", "rgb24",
        output_path,
    ]);

    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x08000000);
    }

    let output = cmd
        .output()
        .map_err(|e| format!("ffmpeg launch failed for DISTS frame: {}", e))?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(format!(
            "ffmpeg frame extraction failed for DISTS: {}",
            stderr.lines().last().unwrap_or("unknown")
        ));
    }

    Ok(())
}
