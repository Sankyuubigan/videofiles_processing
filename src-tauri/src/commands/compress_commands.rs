use std::sync::{Arc, Mutex, atomic::{AtomicBool, Ordering}};
use tauri::{AppHandle, Emitter, State};
use log::{info, error, warn};

use crate::commands::file_commands::FileQueueState;
use crate::process_control::{PidRegistry, PidTracker};
use crate::video_processor::compress::compress_video;

pub struct ProcessingState {
    pub cancel_flag: Arc<AtomicBool>,
    pub is_processing: Arc<Mutex<bool>>,
    pub is_paused: Arc<AtomicBool>,
    pub child_pids: PidRegistry,
    pub current_child_pid: PidTracker,
}

impl Default for ProcessingState {
    fn default() -> Self {
        let child_pids = PidRegistry::default();
        Self {
            cancel_flag: Arc::new(AtomicBool::new(false)),
            is_processing: Arc::new(Mutex::new(false)),
            is_paused: Arc::new(AtomicBool::new(false)),
            current_child_pid: PidTracker::new(child_pids.clone()),
            child_pids,
        }
    }
}

#[tauri::command]
pub async fn start_compress(
    path: String,
    output_format: String,
    codec: String,
    crf_value: i32,
    preset_value: String,
    force_vfr_fix: bool,
    use_hardware: bool,
    auto_crf: bool,
    target_vmaf: f64,
    target_ssimulacra2: f64,
    app: AppHandle,
    queue_state: State<'_, FileQueueState>,
    proc_state: State<'_, ProcessingState>,
) -> Result<String, String> {
    {
        let mut is_proc = proc_state.is_processing.lock().map_err(|e| {
            let msg = format!("Failed to lock processing state: {}", e);
            error!("{}", msg);
            msg
        })?;
        if *is_proc {
            warn!("Compress rejected: already processing");
            return Err("Already processing".to_string());
        }
        *is_proc = true;
    }
    proc_state.cancel_flag.store(false, Ordering::Relaxed);
    proc_state.is_paused.store(false, Ordering::Relaxed);
    proc_state.current_child_pid.store(0);

    let (path, output_dir, test_result) = {
        let files = queue_state.files.lock().map_err(|e| {
            let msg = format!("Failed to lock file queue: {}", e);
            error!("{}", msg);
            msg
        })?;
        let file = files.iter().find(|e| e.path == path).ok_or_else(|| {
            let msg = format!("File not found in queue: {}", path);
            error!("{}", msg);
            msg
        })?;
        let path = file.path.clone();
        let test_result = file.test_result.clone();
        let output_dir = queue_state.output_dir.lock().map_err(|e| {
            let msg = format!("Failed to lock output dir: {}", e);
            error!("{}", msg);
            msg
        })?.clone();
        (path, output_dir, test_result)
    };

    info!("Starting compress: {} -> {} ({}, crf={}, preset={})", path, output_format, codec, crf_value, preset_value);

    let _ = app.emit("current-file", path.clone());
    let path_for_log = path.clone();
    let cancel = proc_state.cancel_flag.clone();
    let app_clone = app.clone();
    let child_pid = proc_state.current_child_pid.clone();
    let result = tokio::task::spawn_blocking(move || {
        let progress_cb = {
            let app = app_clone.clone();
            Arc::new(move |percent: i32, msg: String| {
                let _ = app.emit("compress-progress", (percent, msg));
            }) as Arc<dyn Fn(i32, String) + Send + Sync>
        };
        compress_video(
            &path, &output_format, &codec, crf_value, &preset_value,
            force_vfr_fix, use_hardware, cancel, Some(progress_cb),
            output_dir.as_deref(), auto_crf, target_vmaf, target_ssimulacra2,
            test_result.as_ref(), Some(child_pid),
        )
    }).await.map_err(|e| {
        let msg = format!("Compress thread panicked: {}", e);
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
    if let Err(ref e) = result {
        error!("Compress failed for {}: {}", path_for_log, e);
    }
    let success = result.is_ok();
    let _ = app.emit("file-done", serde_json::json!({
        "path": path_for_log,
        "success": success
    }));
    if success {
        if let Ok(mut files) = queue_state.files.lock() {
            let before = files.len();
            files.retain(|e| e.path != path_for_log);
            if files.len() == before {
                warn!("Compress: file not found in queue for removal: {}", path_for_log);
            }
        }
    }
    let _ = app.emit("compress-finished", result.clone());
    result
}

#[tauri::command]
pub async fn start_batch_compress(
    output_format: String,
    codec: String,
    crf_value: i32,
    preset_value: String,
    force_vfr_fix: bool,
    use_hardware: bool,
    auto_crf: bool,
    target_vmaf: f64,
    target_ssimulacra2: f64,
    app: AppHandle,
    queue_state: State<'_, FileQueueState>,
    proc_state: State<'_, ProcessingState>,
) -> Result<Vec<Result<String, String>>, String> {
    {
        let mut is_proc = proc_state.is_processing.lock().map_err(|e| {
            let msg = format!("Failed to lock processing state: {}", e);
            error!("{}", msg);
            msg
        })?;
        if *is_proc {
            warn!("Batch compress rejected: already processing");
            return Err("Already processing".to_string());
        }
        *is_proc = true;
    }
    proc_state.cancel_flag.store(false, Ordering::Relaxed);
    proc_state.is_paused.store(false, Ordering::Relaxed);
    proc_state.current_child_pid.store(0);

    let (files_vec, output_dir) = {
        let files = queue_state.files.lock().map_err(|e| {
            let msg = format!("Failed to lock file queue: {}", e);
            error!("{}", msg);
            msg
        })?;
        let files_vec = files.clone();
        let output_dir = queue_state.output_dir.lock().map_err(|e| {
            let msg = format!("Failed to lock output dir: {}", e);
            error!("{}", msg);
            msg
        })?.clone();
        (files_vec, output_dir)
    };
    let total = files_vec.len();
    let mut results = Vec::new();
    let output_format_c = output_format.clone();
    let codec_c = codec.clone();
    let preset_value_c = preset_value.clone();

    for (i, file) in files_vec.iter().enumerate() {
        if proc_state.cancel_flag.load(Ordering::Relaxed) { break; }

        while proc_state.is_paused.load(Ordering::Acquire) {
            tokio::time::sleep(std::time::Duration::from_millis(200)).await;
            if proc_state.cancel_flag.load(Ordering::Relaxed) { break; }
        }
        if proc_state.cancel_flag.load(Ordering::Relaxed) { break; }

        let _ = app.emit("current-file", file.path.clone());

        let cancel = proc_state.cancel_flag.clone();
        let app_clone = app.clone();
        let path = file.path.clone();
        let out_dir = output_dir.clone();
        let of = output_format_c.clone();
        let co = codec_c.clone();
        let pv = preset_value_c.clone();
        let child_pid = proc_state.current_child_pid.clone();

        let path_for_log = path.clone();
        let file_test_result = file.test_result.clone();
        let result = tokio::task::spawn_blocking(move || {
            let progress_cb = {
                let app = app_clone.clone();
                Arc::new(move |percent: i32, msg: String| {
                    let overall = ((i as f64 + percent as f64 / 100.0) / total as f64 * 100.0) as i32;
                    let _ = app.emit("compress-progress", (overall, msg));
                }) as Arc<dyn Fn(i32, String) + Send + Sync>
            };
            compress_video(
                &path, &of, &co, crf_value, &pv,
                force_vfr_fix, use_hardware, cancel, Some(progress_cb),
                out_dir.as_deref(), auto_crf, target_vmaf, target_ssimulacra2,
                file_test_result.as_ref(), Some(child_pid),
            )
        }).await.map_err(|e| {
            let msg = format!("Batch compress thread panicked: {}", e);
            error!("{}", msg);
            msg
        })?;

        proc_state.current_child_pid.store(0);

        if let Err(ref e) = result {
            error!("Batch compress failed for {}: {}", path_for_log, e);
        }
        let success = result.is_ok();
        let _ = app.emit("file-done", serde_json::json!({
            "path": path_for_log,
            "success": success
        }));
        if success {
            if let Ok(mut files) = queue_state.files.lock() {
                let before = files.len();
                files.retain(|e| e.path != path_for_log);
                if files.len() == before {
                    warn!("Batch compress: file not found in queue for removal: {}", path_for_log);
                }
            }
        }
        results.push(result);
    }

    {
        let mut is_proc = proc_state.is_processing.lock().map_err(|e| {
            let msg = format!("Failed to unlock processing state: {}", e);
            error!("{}", msg);
            msg
        })?;
        *is_proc = false;
    }
    let _ = app.emit("batch-finished", ());
    Ok(results)
}

#[tauri::command]
pub fn cancel_processing(proc_state: State<ProcessingState>) -> Result<(), String> {
    proc_state.cancel_flag.store(true, Ordering::Relaxed);
    proc_state.is_paused.store(false, Ordering::Relaxed);
    Ok(())
}

#[tauri::command]
pub fn pause_processing(proc_state: State<ProcessingState>) -> Result<(), String> {
    let count = proc_state.child_pids.suspend_all()?;
    proc_state.is_paused.store(true, Ordering::Release);
    info!("Processing paused ({} processes)", count);
    Ok(())
}

#[tauri::command]
pub fn resume_processing(proc_state: State<ProcessingState>) -> Result<(), String> {
    let count = proc_state.child_pids.resume_all()?;
    proc_state.is_paused.store(false, Ordering::Release);
    info!("Processing resumed ({} processes)", count);
    Ok(())
}
