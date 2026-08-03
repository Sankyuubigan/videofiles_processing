use log::{info, warn};
use ort::value::Tensor;

use crate::ffmpeg::probe::VideoType;

use super::session;

/// Raw RGB frame extracted from a video.
pub struct RgbFrame {
    pub width: u32,
    pub height: u32,
    pub data: Vec<u8>,
}

const INPUT_SIZE: usize = 224;
const MEAN: [f32; 3] = [0.485, 0.456, 0.406];
const STD: [f32; 3] = [0.229, 0.224, 0.225];

/// Classify video content type from extracted frames (model: efficientnet_b0,
/// classes: anime / real / rendered). The decision rule matches the validated
/// pipeline: LiveAction only when "real" probability dominates anime+rendered.
pub fn classify_frames(frames: &[RgbFrame]) -> Result<VideoType, String> {
    if frames.is_empty() {
        return Err("no frames to classify".to_string());
    }

    session::ensure_content_type_loaded()?;

    let mut acc = [0.0f32; 3];
    for frame in frames {
        let probs = classify_frame(frame)?;
        for (a, p) in acc.iter_mut().zip(probs.iter()) {
            *a += p;
        }
    }

    let n = frames.len() as f32;
    let mean = [acc[0] / n, acc[1] / n, acc[2] / n];
    info!(
        "Content type NN: mean probs anime={:.4} real={:.4} rendered={:.4}",
        mean[0], mean[1], mean[2]
    );

    Ok(if mean[1] > mean[0] + mean[2] {
        VideoType::LiveAction
    } else {
        VideoType::Animation
    })
}

fn classify_frame(frame: &RgbFrame) -> Result<[f32; 3], String> {
    let img = image::RgbImage::from_raw(frame.width, frame.height, frame.data.clone())
        .ok_or_else(|| "invalid frame buffer".to_string())?;
    let resized = image::imageops::resize(
        &img,
        INPUT_SIZE as u32,
        INPUT_SIZE as u32,
        image::imageops::FilterType::Triangle,
    );

    let shape = vec![1i64, 3, INPUT_SIZE as i64, INPUT_SIZE as i64];
    let mut data = Vec::with_capacity(3 * INPUT_SIZE * INPUT_SIZE);
    for c in 0..3 {
        for y in 0..INPUT_SIZE {
            for x in 0..INPUT_SIZE {
                let p = resized.get_pixel(x as u32, y as u32);
                let v = (p[c] as f32 / 255.0 - MEAN[c]) / STD[c];
                data.push(v);
            }
        }
    }
    let input = Tensor::from_array((shape, data.into_boxed_slice()))
        .map_err(|e| format!("failed to create input tensor: {}", e))?;

    let probs = {
        let mut guard = session::CONTENT_TYPE_SESSION.lock()
            .map_err(|e| format!("failed to lock content type session: {}", e))?;
        let sess = guard.as_mut().ok_or("content type session not loaded")?;
        let input_name = sess.inputs().first()
            .map(|i| i.name().to_string())
            .ok_or("content type model has no inputs")?;
        let outputs = sess.run(ort::inputs![input_name.as_str() => input])
            .map_err(|e| format!("content type inference failed: {}", e))?;
        if outputs.len() == 0 {
            return Err("content type model produced no outputs".to_string());
        }
        let (_shape, data) = outputs[0].try_extract_tensor::<f32>()
            .map_err(|e| format!("failed to extract content type output: {}", e))?;
        if data.len() < 3 {
            warn!("Content type model output too small: {} values", data.len());
            return Err("content type output too small".to_string());
        }

        let max = data.iter().fold(f32::MIN, |a, b| a.max(*b));
        let mut exp_sum = 0.0f32;
        let mut exps = [0.0f32; 3];
        for i in 0..3 {
            exps[i] = (data[i] - max).exp();
            exp_sum += exps[i];
        }
        [exps[0] / exp_sum, exps[1] / exp_sum, exps[2] / exp_sum]
    };

    Ok(probs)
}
