use std::sync::Arc;
use std::sync::atomic::Ordering;
use tauri::{AppHandle, Emitter, State};
use log::{error, warn};

use crate::commands::file_commands::{FileQueueState, TestResult};
use crate::video_processor::chunk_test::run_chunk_test;

use super::compress_commands::ProcessingState;

#[tauri::command]
pub async fn run_chunk_test_cmd(
    path: String,
    codec: String,
    crf_value: i32,
    preset_value: String,
    use_hardware: bool,
    auto_crf: bool,
    target_vmaf: f64,
    target_ssimulacra2: f64,
    force_vfr_fix: bool,
    force_metric: Option<String>,
    app: AppHandle,
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
        files.iter().find(|e| e.path == path).ok_or_else(|| {
            let msg = format!("File not found in queue: {}", path);
            error!("{}", msg);
            msg
        })?.path.clone()
    };

    let path_for_log = path.clone();
    let cancel = proc_state.cancel_flag.clone();
    let child_pid = proc_state.current_child_pid.clone();
    let progress_cb: Option<Arc<dyn Fn(i32, String) + Send + Sync>> = {
        let app = app.clone();
        Some(Arc::new(move |percent: i32, message: String| {
            let _ = app.emit("test-progress", (percent, message));
        }))
    };
    let result = tokio::task::spawn_blocking(move || {
        run_chunk_test(&path, &codec, crf_value, &preset_value, use_hardware, cancel, auto_crf, target_vmaf, target_ssimulacra2, force_vfr_fix, force_metric, progress_cb, Some(child_pid))
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
                if let Some(entry) = files.iter_mut().find(|e| e.path == path_for_log) {
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
        let child_pid = proc_state.current_child_pid.clone();
        let path = file.path.clone();
        let codec = codec.clone();
        let preset = preset_value.clone();
        let progress_cb: Option<Arc<dyn Fn(i32, String) + Send + Sync>> = {
            let app = app.clone();
            Some(Arc::new(move |percent: i32, message: String| {
                let _ = app.emit("batch-test-progress", (i, total, percent, message));
            }))
        };

        let result = tokio::task::spawn_blocking(move || {
            run_chunk_test(&path, &codec, crf_value, &preset, use_hardware, cancel, auto_crf, target_vmaf, target_ssimulacra2, force_vfr_fix, None, progress_cb, Some(child_pid))
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