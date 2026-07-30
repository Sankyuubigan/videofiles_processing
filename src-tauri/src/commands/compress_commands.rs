use std::sync::{Arc, Mutex, atomic::{AtomicBool, AtomicU32, Ordering}};
use tauri::{AppHandle, Emitter, State};
use log::{info, error, warn};

use crate::commands::file_commands::FileQueueState;
use crate::video_processor::compress::compress_video;

pub struct ProcessingState {
    pub cancel_flag: Arc<AtomicBool>,
    pub is_processing: Arc<Mutex<bool>>,
    pub is_paused: Arc<AtomicBool>,
    pub current_child_pid: Arc<AtomicU32>,
}

impl Default for ProcessingState {
    fn default() -> Self {
        Self {
            cancel_flag: Arc::new(AtomicBool::new(false)),
            is_processing: Arc::new(Mutex::new(false)),
            is_paused: Arc::new(AtomicBool::new(false)),
            current_child_pid: Arc::new(AtomicU32::new(0)),
        }
    }
}

#[tauri::command]
pub async fn start_compress(
    file_index: usize,
    output_format: String,
    codec: String,
    crf_value: i32,
    preset_value: String,
    force_vfr_fix: bool,
    use_hardware: bool,
    auto_crf: bool,
    target_vmaf: f64,
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
    proc_state.current_child_pid.store(0, Ordering::Release);

    let (path, output_dir) = {
        let files = queue_state.files.lock().map_err(|e| {
            let msg = format!("Failed to lock file queue: {}", e);
            error!("{}", msg);
            msg
        })?;
        let file = files.get(file_index).ok_or_else(|| {
            let msg = format!("Invalid file index: {}", file_index);
            error!("{}", msg);
            msg
        })?;
        let path = file.path.clone();
        let output_dir = queue_state.output_dir.lock().map_err(|e| {
            let msg = format!("Failed to lock output dir: {}", e);
            error!("{}", msg);
            msg
        })?.clone();
        (path, output_dir)
    };

    info!("Starting compress: {} -> {} ({}, crf={}, preset={})", path, output_format, codec, crf_value, preset_value);

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
            output_dir.as_deref(), auto_crf, target_vmaf, Some(child_pid),
        )
    }).await.map_err(|_| {
        let msg = "Compress thread panicked".to_string();
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
    proc_state.current_child_pid.store(0, Ordering::Release);

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

        let cancel = proc_state.cancel_flag.clone();
        let app_clone = app.clone();
        let path = file.path.clone();
        let out_dir = output_dir.clone();
        let of = output_format_c.clone();
        let co = codec_c.clone();
        let pv = preset_value_c.clone();
        let child_pid = proc_state.current_child_pid.clone();

        let path_for_log = path.clone();
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
                out_dir.as_deref(), auto_crf, target_vmaf, Some(child_pid),
            )
        }).await.map_err(|_| {
            let msg = "Batch compress thread panicked".to_string();
            error!("{}", msg);
            msg
        })?;

        proc_state.current_child_pid.store(0, Ordering::Release);

        if let Err(ref e) = result {
            error!("Batch compress failed for {}: {}", path_for_log, e);
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
    let pid = proc_state.current_child_pid.load(Ordering::Acquire);
    if pid == 0 {
        warn!("Pause requested but no active FFmpeg process");
        return Err("No active process to pause".to_string());
    }
    crate::process_control::suspend_process(pid)?;
    proc_state.is_paused.store(true, Ordering::Release);
    info!("Processing paused (PID {})", pid);
    Ok(())
}

#[tauri::command]
pub fn resume_processing(proc_state: State<ProcessingState>) -> Result<(), String> {
    let pid = proc_state.current_child_pid.load(Ordering::Acquire);
    if pid == 0 {
        warn!("Resume requested but no active FFmpeg process");
        return Err("No active process to resume".to_string());
    }
    crate::process_control::resume_process(pid)?;
    proc_state.is_paused.store(false, Ordering::Release);
    info!("Processing resumed (PID {})", pid);
    Ok(())
}
