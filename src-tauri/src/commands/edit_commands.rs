use std::sync::{Arc, atomic::Ordering};
use tauri::{AppHandle, Emitter, State};
use log::{error, warn};

use super::compress_commands::ProcessingState;
use crate::video_processor::trim::trim_video;
use crate::video_processor::normalize::normalize_audio;
use crate::video_processor::extract_frame::extract_frame as extract_frame_task;

#[tauri::command]
pub async fn trim_video_cmd(
    file_path: String,
    seconds: f64,
    from_start: bool,
    output_dir: Option<String>,
    app: AppHandle,
    proc_state: State<'_, ProcessingState>,
) -> Result<String, String> {
    {
        let mut is_proc = proc_state.is_processing.lock().map_err(|e| {
            let msg = format!("Failed to lock processing state: {}", e);
            error!("{}", msg);
            msg
        })?;
        if *is_proc {
            warn!("Trim rejected: already processing");
            return Err("Already processing".to_string());
        }
        *is_proc = true;
    }
    proc_state.cancel_flag.store(false, Ordering::Relaxed);

    let file_path_for_log = file_path.clone();
    let cancel = proc_state.cancel_flag.clone();
    let app2 = app.clone();
    let result = tokio::task::spawn_blocking(move || {
        let progress_cb = {
            let app = app2.clone();
            Arc::new(move |percent: i32, msg: String| {
                let _ = app.emit("compress-progress", (percent, msg));
            }) as Arc<dyn Fn(i32, String) + Send + Sync>
        };
        trim_video(&file_path, seconds, from_start, cancel, Some(progress_cb), output_dir.as_deref())
    }).await.map_err(|_| {
        let msg = "Trim thread panicked".to_string();
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
        error!("Trim failed for {}: {}", file_path_for_log, e);
    }
    let _ = app.emit("compress-finished", result.clone());
    result
}

#[tauri::command]
pub async fn normalize_audio_cmd(
    file_path: String,
    output_dir: Option<String>,
    app: AppHandle,
    proc_state: State<'_, ProcessingState>,
) -> Result<String, String> {
    {
        let mut is_proc = proc_state.is_processing.lock().map_err(|e| {
            let msg = format!("Failed to lock processing state: {}", e);
            error!("{}", msg);
            msg
        })?;
        if *is_proc {
            warn!("Normalize rejected: already processing");
            return Err("Already processing".to_string());
        }
        *is_proc = true;
    }
    proc_state.cancel_flag.store(false, Ordering::Relaxed);

    let file_path_for_log = file_path.clone();
    let cancel = proc_state.cancel_flag.clone();
    let app2 = app.clone();
    let result = tokio::task::spawn_blocking(move || {
        let progress_cb = {
            let app = app2.clone();
            Arc::new(move |percent: i32, msg: String| {
                let _ = app.emit("compress-progress", (percent, msg));
            }) as Arc<dyn Fn(i32, String) + Send + Sync>
        };
        normalize_audio(&file_path, cancel, Some(progress_cb), output_dir.as_deref())
    }).await.map_err(|_| {
        let msg = "Normalize thread panicked".to_string();
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
        error!("Normalize failed for {}: {}", file_path_for_log, e);
    }
    let _ = app.emit("compress-finished", result.clone());
    result
}

#[tauri::command]
pub async fn extract_frame_cmd(
    file_path: String,
    frame_number: usize,
    output_dir: Option<String>,
    proc_state: State<'_, ProcessingState>,
) -> Result<String, String> {
    {
        let mut is_proc = proc_state.is_processing.lock().map_err(|e| {
            let msg = format!("Failed to lock processing state: {}", e);
            error!("{}", msg);
            msg
        })?;
        if *is_proc {
            warn!("Extract frame rejected: already processing");
            return Err("Already processing".to_string());
        }
        *is_proc = true;
    }
    proc_state.cancel_flag.store(false, Ordering::Relaxed);

    let file_path_for_log = file_path.clone();
    let cancel = proc_state.cancel_flag.clone();
    let result = tokio::task::spawn_blocking(move || {
        extract_frame_task(&file_path, frame_number, cancel, output_dir.as_deref())
    }).await.map_err(|_| {
        let msg = "Extract frame thread panicked".to_string();
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
        error!("Extract frame failed for {}: {}", file_path_for_log, e);
    }
    result
}
