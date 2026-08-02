use std::sync::atomic::Ordering;
use serde::{Serialize, Deserialize};
use tauri::{AppHandle, Emitter, State};
use log::{error, info, warn};

use crate::commands::file_commands::{FileQueueState, TestResult};
use crate::video_processor::chunk_test::run_chunk_test;

use super::compress_commands::ProcessingState;

#[tauri::command]
pub async fn run_chunk_test_cmd(
    file_index: usize,
    codec: String,
    crf_value: i32,
    preset_value: String,
    use_hardware: bool,
    auto_crf: bool,
    target_vmaf: f64,
    target_ssimulacra2: f64,
    force_vfr_fix: bool,
    force_metric: Option<String>,
    queue_state: State<'_, FileQueueState>,
    proc_state: State<'_, ProcessingState>,
) -> Result<TestResult, String> {
    {
        let mut is_proc = proc_state.is_processing.lock().map_err(|e| {
            let msg = format!("Failed to lock processing state: {}", e);
            error!("{}", msg);
            msg
        })?;
        if *is_proc {
            warn!("Chunk test rejected: already processing");
            return Err("Already processing".to_string());
        }
        *is_proc = true;
    }
    proc_state.cancel_flag.store(false, Ordering::Relaxed);

    let path = {
        let files = queue_state.files.lock().map_err(|e| {
            let msg = format!("Failed to lock file queue: {}", e);
            error!("{}", msg);
            msg
        })?;
        files.get(file_index).ok_or_else(|| {
            let msg = format!("Invalid file index: {}", file_index);
            error!("{}", msg);
            msg
        })?.path.clone()
    };

    let path_for_log = path.clone();
    let cancel = proc_state.cancel_flag.clone();
    let result = tokio::task::spawn_blocking(move || {
        run_chunk_test(&path, &codec, crf_value, &preset_value, use_hardware, cancel, auto_crf, target_vmaf, target_ssimulacra2, force_vfr_fix, force_metric)
    }).await.map_err(|e| {
        let msg = format!("Chunk test thread panicked: {}", e);
        error!("{}", msg);
        msg
    })?;

    {
        let mut is_proc = proc_state.is_processing.lock().map_err(|e| {
            let msg = format!("Failed to unlock processing state: {}", e);
            error!("{}", msg);
            msg
        })?;
        *is_proc = false;
    }

    match result {
        Ok(r) => {
            let test_result = TestResult {
                test_diff: r.test_diff,
                test_est_size: r.test_est_size,
                test_est_time: r.test_est_time,
                test_vmaf: r.test_vmaf,
                is_profitable: r.is_profitable,
                test_crf: r.test_crf,
                metric: r.metric,
            };
            if let Ok(mut files) = queue_state.files.lock() {
                if let Some(entry) = files.get_mut(file_index) {
                    entry.test_result = Some(test_result.clone());
                }
            }
            Ok(test_result)
        }
        Err(e) => {
            error!("Chunk test failed for {}: {}", path_for_log, e);
            Err(e)
        }
    }
}

#[tauri::command]
pub async fn run_batch_test(
    codec: String,
    crf_value: i32,
    preset_value: String,
    use_hardware: bool,
    auto_crf: bool,
    target_vmaf: f64,
    target_ssimulacra2: f64,
    force_vfr_fix: bool,
    app: AppHandle,
    queue_state: State<'_, FileQueueState>,
    proc_state: State<'_, ProcessingState>,
) -> Result<Vec<TestResult>, String> {
    {
        let mut is_proc = proc_state.is_processing.lock().map_err(|e| {
            let msg = format!("Failed to lock processing state: {}", e);
            error!("{}", msg);
            msg
        })?;
        if *is_proc {
            warn!("Batch test rejected: already processing");
            return Err("Already processing".to_string());
        }
        *is_proc = true;
    }
    proc_state.cancel_flag.store(false, Ordering::Relaxed);

    let (files_vec, total) = {
        let files = queue_state.files.lock().map_err(|e| {
            let msg = format!("Failed to lock file queue: {}", e);
            error!("{}", msg);
            msg
        })?;
        let v = files.clone();
        (v.clone(), v.len())
    };
    let mut results = Vec::new();

    for (i, file) in files_vec.iter().enumerate() {
        if proc_state.cancel_flag.load(Ordering::Relaxed) { break; }
        let cancel = proc_state.cancel_flag.clone();
        let path = file.path.clone();
        let codec = codec.clone();
        let preset = preset_value.clone();

        let result = tokio::task::spawn_blocking(move || {
            run_chunk_test(&path, &codec, crf_value, &preset, use_hardware, cancel, auto_crf, target_vmaf, target_ssimulacra2, force_vfr_fix, None)
        }).await.map_err(|e| {
            let msg = format!("Batch test thread panicked for {}: {}", file.path, e);
            error!("{}", msg);
            msg
        })?;

        match result {
            Ok(r) => {
                let test_result = TestResult {
                    test_diff: r.test_diff,
                    test_est_size: r.test_est_size,
                    test_est_time: r.test_est_time,
                    test_vmaf: r.test_vmaf,
                    is_profitable: r.is_profitable,
                    test_crf: r.test_crf,
                    metric: r.metric,
                };
                if let Ok(mut files) = queue_state.files.lock() {
                    if let Some(entry) = files.get_mut(i) {
                        entry.test_result = Some(test_result.clone());
                    }
                }
                let _ = app.emit("batch-test-progress", (i + 1, total));
                results.push(test_result);
            }
            Err(e) => {
                error!("Error testing file {}: {}", file.path, e);
            }
        }
    }

    {
        let mut is_proc = proc_state.is_processing.lock().map_err(|e| {
            let msg = format!("Failed to unlock processing state: {}", e);
            error!("{}", msg);
            msg
        })?;
        *is_proc = false;
    }
    let _ = app.emit("batch-test-finished", ());
    Ok(results)
}

/// Run neural network quality test (LPIPS or DISTS) on a single file.
/// This compares the original file with a hypothetical compressed version
/// at the given CRF, using a neural network perceptual metric.
#[tauri::command]
pub async fn run_nn_quality_test_cmd(
    file_index: usize,
    codec: String,
    crf_value: i32,
    preset_value: String,
    use_hardware: bool,
    force_vfr_fix: bool,
    metric: String,
    queue_state: State<'_, FileQueueState>,
    proc_state: State<'_, ProcessingState>,
) -> Result<NnTestResult, String> {
    {
        let mut is_proc = proc_state.is_processing.lock().map_err(|e| {
            let msg = format!("Failed to lock processing state: {}", e);
            error!("{}", msg);
            msg
        })?;
        if *is_proc {
            warn!("NN quality test rejected: already processing");
            return Err("Already processing".to_string());
        }
        *is_proc = true;
    }
    proc_state.cancel_flag.store(false, Ordering::Relaxed);

    let path = {
        let files = queue_state.files.lock().map_err(|e| {
            let msg = format!("Failed to lock file queue: {}", e);
            error!("{}", msg);
            msg
        })?;
        files.get(file_index).ok_or_else(|| {
            let msg = format!("Invalid file index: {}", file_index);
            error!("{}", msg);
            msg
        })?.path.clone()
    };

    let path_for_log = path.clone();
    let cancel = proc_state.cancel_flag.clone();
    let metric_clone = metric.clone();

    let result = tokio::task::spawn_blocking(move || {
        run_nn_quality_test(
            &path, &codec, crf_value, &preset_value, use_hardware,
            cancel, force_vfr_fix, &metric_clone,
        )
    }).await.map_err(|e| {
        let msg = format!("NN quality test thread panicked: {}", e);
        error!("{}", msg);
        msg
    })?;

    {
        let mut is_proc = proc_state.is_processing.lock().map_err(|e| {
            let msg = format!("Failed to unlock processing state: {}", e);
            error!("{}", msg);
            msg
        })?;
        *is_proc = false;
    }

    match result {
        Ok(r) => Ok(r),
        Err(e) => {
            error!("NN quality test failed for {}: {}", path_for_log, e);
            Err(e)
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NnTestResult {
    pub score: f64,
    pub metric: String,
    pub inference_ms: u64,
    pub target: f64,
    pub passed: bool,
}

fn run_nn_quality_test(
    input_path: &str,
    codec: &str,
    crf_value: i32,
    preset_value: &str,
    use_hardware: bool,
    cancel_flag: std::sync::Arc<std::sync::atomic::AtomicBool>,
    force_vfr_fix: bool,
    metric: &str,
) -> Result<NnTestResult, String> {
    let settings = crate::settings::load_settings();
    let video_info = crate::ffmpeg::probe::get_video_info_raw(input_path)
        .map_err(|e| format!("Failed to get video info: {}", e))?;

    let width = video_info.width;
    let height = video_info.height;
    let duration = video_info.duration;
    let needs_fix = force_vfr_fix || video_info.needs_vfr_fix;

    // Create temp directory for test
    let temp_dir = std::env::temp_dir().join(format!("nn_test_{}", std::process::id()));
    std::fs::create_dir_all(&temp_dir).map_err(|e| format!("Failed to create temp dir: {}", e))?;

    let encoded_path = temp_dir.join(format!("test_encoded.{}", 
        if codec.contains("x265") || codec.contains("hevc") { "mkv" } else { "mp4" }
    ));
    let encoded_str = encoded_path.to_string_lossy().to_string();

    // Encode a chunk with the given CRF
    info!("NN test: encoding chunk with CRF {} codec {} preset {}", crf_value, codec, preset_value);
    let video_type = &video_info.video_type;
    let encode_result = crate::ffmpeg::encode::encode_chunk(
        input_path,
        &encoded_str,
        0.0,
        duration.min(5.0), // Use up to 5 seconds for testing
        codec,
        crf_value,
        preset_value,
        use_hardware,
        &video_info,
        video_type,
        needs_fix,
        cancel_flag.clone(),
    );

    if !encode_result.success {
        let _ = std::fs::remove_dir_all(&temp_dir);
        return Err(format!("Encoding failed: {}", encode_result.message));
    }

    if cancel_flag.load(Ordering::Relaxed) {
        let _ = std::fs::remove_dir_all(&temp_dir);
        return Err("Cancelled".to_string());
    }

    // Run NN quality check
    let nn_result = crate::video_processor::quality_check::check_quality_nn(
        input_path,
        &encoded_str,
        0.0,
        duration.min(5.0),
        width,
        height,
        settings.vmaf_ignore_noise,
        cancel_flag,
        metric,
    )?;

    // Cleanup
    let _ = std::fs::remove_dir_all(&temp_dir);

    Ok(NnTestResult {
        score: nn_result.score,
        metric: nn_result.metric,
        inference_ms: nn_result.inference_ms.unwrap_or(0),
        target: nn_result.target,
        passed: nn_result.passed,
    })
}

/// Run ALL quality metrics on a single file: iqa + oximedia + ONNX LPIPS/DISTS.
/// Logs every result and returns an NnTestResult with the primary metric for the table.
#[tauri::command]
pub async fn run_all_metrics_cmd(
    file_index: usize,
    codec: String,
    crf_value: i32,
    preset_value: String,
    use_hardware: bool,
    force_vfr_fix: bool,
    queue_state: State<'_, FileQueueState>,
    proc_state: State<'_, ProcessingState>,
) -> Result<NnTestResult, String> {
    {
        let mut is_proc = proc_state.is_processing.lock().map_err(|e| {
            let msg = format!("Failed to lock processing state: {}", e);
            error!("{}", msg);
            msg
        })?;
        if *is_proc {
            warn!("All metrics test rejected: already processing");
            return Err("Already processing".to_string());
        }
        *is_proc = true;
    }
    proc_state.cancel_flag.store(false, Ordering::Relaxed);

    let path = {
        let files = queue_state.files.lock().map_err(|e| {
            let msg = format!("Failed to lock file queue: {}", e);
            error!("{}", msg);
            msg
        })?;
        files.get(file_index).ok_or_else(|| {
            let msg = format!("Invalid file index: {}", file_index);
            error!("{}", msg);
            msg
        })?.path.clone()
    };

    let path_for_log = path.clone();
    let cancel = proc_state.cancel_flag.clone();

    let result = tokio::task::spawn_blocking(move || {
        run_all_metrics_test(
            &path, &codec, crf_value, &preset_value, use_hardware,
            cancel, force_vfr_fix,
        )
    }).await.map_err(|e| {
        let msg = format!("All metrics test thread panicked: {}", e);
        error!("{}", msg);
        msg
    })?;

    {
        let mut is_proc = proc_state.is_processing.lock().map_err(|e| {
            let msg = format!("Failed to unlock processing state: {}", e);
            error!("{}", msg);
            msg
        })?;
        *is_proc = false;
    }

    match result {
        Ok(r) => Ok(r),
        Err(e) => {
            error!("All metrics test failed for {}: {}", path_for_log, e);
            Err(e)
        }
    }
}

fn run_all_metrics_test(
    input_path: &str,
    codec: &str,
    crf_value: i32,
    preset_value: &str,
    use_hardware: bool,
    cancel_flag: std::sync::Arc<std::sync::atomic::AtomicBool>,
    force_vfr_fix: bool,
) -> Result<NnTestResult, String> {
    let settings = crate::settings::load_settings();
    let video_info = crate::ffmpeg::probe::get_video_info_raw(input_path)
        .map_err(|e| format!("Failed to get video info: {}", e))?;

    let width = video_info.width;
    let height = video_info.height;
    let duration = video_info.duration;
    let needs_fix = force_vfr_fix || video_info.needs_vfr_fix;

    let temp_dir = std::env::temp_dir().join(format!("allmetrics_test_{}", std::process::id()));
    std::fs::create_dir_all(&temp_dir).map_err(|e| format!("Failed to create temp dir: {}", e))?;

    let encoded_path = temp_dir.join(format!("test_encoded.{}",
        if codec.contains("x265") || codec.contains("hevc") { "mkv" } else { "mp4" }
    ));
    let encoded_str = encoded_path.to_string_lossy().to_string();

    info!("All metrics test: encoding chunk with CRF {} codec {} preset {}", crf_value, codec, preset_value);
    let video_type = &video_info.video_type;
    let encode_result = crate::ffmpeg::encode::encode_chunk(
        input_path,
        &encoded_str,
        0.0,
        duration.min(5.0),
        codec,
        crf_value,
        preset_value,
        use_hardware,
        &video_info,
        video_type,
        needs_fix,
        cancel_flag.clone(),
    );

    if !encode_result.success {
        let _ = std::fs::remove_dir_all(&temp_dir);
        return Err(format!("Encoding failed: {}", encode_result.message));
    }

    if cancel_flag.load(Ordering::Relaxed) {
        let _ = std::fs::remove_dir_all(&temp_dir);
        return Err("Cancelled".to_string());
    }

    let all_results = crate::video_processor::quality_check::check_quality_all(
        input_path,
        &encoded_str,
        0.0,
        duration.min(5.0),
        width,
        height,
        settings.vmaf_ignore_noise,
        cancel_flag,
    )?;

    let _ = std::fs::remove_dir_all(&temp_dir);

    if all_results.is_empty() {
        return Err("No metrics computed".to_string());
    }

    // Use SSIM as primary for table (first iqa metric, or first overall)
    let primary = all_results.iter()
        .find(|m| m.metric == "SSIM")
        .or_else(|| all_results.iter().find(|m| m.metric == "LPIPS (oximedia)"))
        .or_else(|| all_results.first())
        .ok_or("No primary metric found in all metrics results")?;

    Ok(NnTestResult {
        score: primary.score,
        metric: primary.metric.clone(),
        inference_ms: primary.compute_ms,
        target: primary.target,
        passed: primary.passed,
    })
}