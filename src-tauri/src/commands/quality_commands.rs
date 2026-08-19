use std::sync::atomic::Ordering;

use log::{error, info, warn};
use tauri::{AppHandle, Emitter, State};

use crate::commands::compress_commands::ProcessingState;
use crate::commands::file_commands::FileQueueState;
use crate::nn_quality::assess::{assess_video_quality, QualityAssessment};

#[tauri::command]
pub async fn assess_quality_cmd(
    path: String,
    app: AppHandle,
    queue_state: State<'_, FileQueueState>,
    proc_state: State<'_, ProcessingState>,
) -> Result<QualityAssessment, String> {
    {
        let mut is_proc = proc_state.is_processing.lock().map_err(|e| {
            let msg = format!("Failed to lock processing state: {}", e);
            error!("{}", msg);
            msg
        })?;
        if *is_proc {
            warn!("Quality check rejected: already processing");
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
    let _ = app.emit("current-file", path_for_log.clone());

    let result = tokio::task::spawn_blocking(move || {
        assess_video_quality(&path, cancel)
    }).await.map_err(|e| {
        let msg = format!("Quality check thread panicked: {}", e);
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

    match &result {
        Ok(r) => {
            info!("Quality check done for {}: {} ({} frames)", path_for_log, r.verdict, r.frames_used);
            Ok(r.clone())
        }
        Err(e) => {
            error!("Quality check failed for {}: {}", path_for_log, e);
            Err(e.clone())
        }
    }
}