use std::process::Command;
use std::sync::Arc;
use std::sync::atomic::AtomicBool;
use std::time::Instant;
use log::info;
use ort::value::Tensor;

use super::session;

/// Calculate LPIPS score between original and distorted video frames.
/// Returns a score where LOWER means more similar (0 = identical).
///
/// LPIPS range: [0, 1] approximately
/// - 0.0 = identical
/// - 0.1 = very similar
/// - 0.3 = noticeable difference
/// - 0.5+ = very different
pub fn calculate_lpips(
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
    let orig_png = tmp_dir.join(format!("lpips_orig_{}_{}.png", std::process::id(), ts_ms));
    let dist_png = tmp_dir.join(format!("lpips_dist_{}_{}.png", std::process::id(), ts_ms));

    let orig_str = orig_png.to_string_lossy().to_string();
    let dist_str = dist_png.to_string_lossy().to_string();

    // Extract frames from both videos
    let orig_timestamp = start_time + if duration > 0.0 { duration / 2.0 } else { 0.0 };
    extract_frame_for_nn(
        original_path,
        &orig_str,
        orig_timestamp,
        width,
        height,
        ignore_noise,
        256,
    )?;

    if cancel_flag.load(std::sync::atomic::Ordering::Relaxed) {
        let _ = std::fs::remove_file(&orig_png);
        let _ = std::fs::remove_file(&dist_png);
        return Err("Cancelled".to_string());
    }

    let encoded_timestamp = if duration > 0.0 { duration / 2.0 } else { 0.0 };
    extract_frame_for_nn(
        encoded_path,
        &dist_str,
        encoded_timestamp,
        width,
        height,
        ignore_noise,
        256,
    )?;

    // Load images and preprocess
    let orig_img = image::open(&orig_png).map_err(|e| {
        let _ = std::fs::remove_file(&orig_png);
        let _ = std::fs::remove_file(&dist_png);
        format!("Failed to load original frame for LPIPS: {}", e)
    })?;
    let dist_img = image::open(&dist_png).map_err(|e| {
        let _ = std::fs::remove_file(&orig_png);
        let _ = std::fs::remove_file(&dist_png);
        format!("Failed to load distorted frame for LPIPS: {}", e)
    })?;
    let _ = std::fs::remove_file(&orig_png);
    let _ = std::fs::remove_file(&dist_png);

    let preprocess_start = Instant::now();

    // Resize to 256x256 and normalize to [-1, 1]
    let (orig_shape, orig_data) = image_to_lpips_tensor(&orig_img, 256)?;
    let (dist_shape, dist_data) = image_to_lpips_tensor(&dist_img, 256)?;

    info!(
        "LPIPS preprocess: {}ms",
        preprocess_start.elapsed().as_millis()
    );

    if cancel_flag.load(std::sync::atomic::Ordering::Relaxed) {
        return Err("Cancelled".to_string());
    }

    // Run inference
    session::ensure_lpips_loaded()?;

    let infer_start = Instant::now();

    let score = {
        let mut guard = session::LPIPS_SESSION.lock().map_err(|e| {
            format!("Failed to lock LPIPS session: {}", e)
        })?;
        let sess = guard.as_mut().ok_or("LPIPS session not loaded")?;

        let input_names: Vec<String> = sess.inputs().iter().map(|i| i.name().to_string()).collect();

        info!("LPIPS model inputs: {:?}", input_names);

        let outputs = if input_names.len() >= 2 {
            let orig_ort = Tensor::from_array((orig_shape, orig_data.into_boxed_slice()))
                .map_err(|e| format!("Failed to create ort tensor for orig: {}", e))?;
            let dist_ort = Tensor::from_array((dist_shape, dist_data.into_boxed_slice()))
                .map_err(|e| format!("Failed to create ort tensor for dist: {}", e))?;
            sess.run(ort::inputs![
                input_names[0].as_str() => orig_ort,
                input_names[1].as_str() => dist_ort
            ])
            .map_err(|e| format!("LPIPS inference failed: {}", e))?
        } else if input_names.len() == 1 {
            let mut combined_data = orig_data;
            combined_data.extend_from_slice(&dist_data);
            let combined_shape = vec![2i64, 3, orig_shape[2], orig_shape[3]];
            let combined_ort = Tensor::from_array((combined_shape, combined_data.into_boxed_slice()))
                .map_err(|e| format!("Failed to create ort tensor for combined: {}", e))?;
            sess.run(ort::inputs![combined_ort])
                .map_err(|e| format!("LPIPS inference failed: {}", e))?
        } else {
            return Err("LPIPS model has no inputs".to_string());
        };

        if outputs.len() == 0 {
            return Err("LPIPS model produced no outputs".to_string());
        }

        let (_shape, data) = outputs[0].try_extract_tensor::<f32>()
            .map_err(|e| format!("Failed to extract LPIPS output: {}", e))?;
        *data.first().ok_or("LPIPS output is empty")? as f64
    };

    let inference_ms = infer_start.elapsed().as_millis() as u64;
    info!("LPIPS inference: {}ms", inference_ms);

    let total_ms = t0.elapsed().as_millis() as u64;
    info!(
        "LPIPS total: {}ms (preprocess + inference + postprocess), score={:.4}",
        total_ms, score
    );

    Ok(score)
}

/// Convert an image to LPIPS tensor format: [1, 3, H, W] normalized to [-1, 1]
/// Returns (shape as Vec<i64>, flat data as Vec<f32>)
fn image_to_lpips_tensor(
    img: &image::DynamicImage,
    target_size: u32,
) -> Result<(Vec<i64>, Vec<f32>), String> {
    let resized = img.resize_exact(target_size, target_size, image::imageops::FilterType::Lanczos3);
    let rgb = resized.to_rgb8();
    let (w, h) = rgb.dimensions();

    // Normalize to [-1, 1] (ImageNet normalization for AlexNet)
    let mut data = Vec::with_capacity((3 * h * w) as usize);
    for y in 0..h {
        for x in 0..w {
            let p = rgb.get_pixel(x, y);
            data.push(p[0] as f32 / 127.5 - 1.0);
            data.push(p[1] as f32 / 127.5 - 1.0);
            data.push(p[2] as f32 / 127.5 - 1.0);
        }
    }

    let shape = vec![1i64, 3, h as i64, w as i64];
    Ok((shape, data))
}

/// Extract a frame from video using ffmpeg, resized for neural network input
fn extract_frame_for_nn(
    input_path: &str,
    output_path: &str,
    timestamp: f64,
    _orig_width: usize,
    _orig_height: usize,
    ignore_noise: bool,
    target_size: u32,
) -> Result<(), String> {
    let mut vf_filters = Vec::new();

    if ignore_noise {
        vf_filters.push("hqdn3d=12:9:14:12,gblur=sigma=0.6".to_string());
    }

    // Scale to target size for neural network
    vf_filters.push(format!("scale={}:{}:flags=lanczos", target_size, target_size));

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
        .map_err(|e| format!("ffmpeg launch failed for LPIPS frame: {}", e))?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(format!(
            "ffmpeg frame extraction failed for LPIPS: {}",
            stderr.lines().last().unwrap_or("unknown")
        ));
    }

    Ok(())
}
