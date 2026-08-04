use std::sync::Arc;
use std::sync::atomic::Ordering;
use tauri::{AppHandle, Emitter, State};
use log::{error, warn};

use super::compress_commands::ProcessingState;
use crate::video_processor::preview_gif::generate_preview_gif;

#[tauri::command]
pub async fn generate_preview_gif_cmd(
    path: String,
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
            warn!("Preview generation rejected: already processing");
            return Err("Already processing".to_string());
        }
        *is_proc = true;
    }
    proc_state.cancel_flag.store(false, Ordering::Relaxed);

    let path_for_log = path.clone();
    let _ = app.emit("current-file", path.clone());
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
        generate_preview_gif(&path, cancel, Some(progress_cb), Some(child_pid))
    })
    .await
    .map_err(|e| {
        let msg = format!("Preview thread panicked: {}", e);
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
        error!("Preview generation failed for {}: {}", path_for_log, e);
    }
    result
}