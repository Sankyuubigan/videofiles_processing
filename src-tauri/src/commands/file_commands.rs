use serde::{Deserialize, Serialize};
use std::path::Path;
use std::sync::Mutex;
use tauri::State;
use log::{info, error, warn};

use crate::video_processor::analyzer::{AnalysisState, Analyzer};
use crate::ffmpeg::probe::VideoInfo;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FileEntry {
    pub path: String,
    pub info: Option<VideoInfo>,
    pub test_result: Option<TestResult>,
    #[serde(default)]
    pub analysis_state: AnalysisState,
    #[serde(default)]
    pub error: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TestResult {
    pub test_diff: String,
    pub test_est_size: String,
    pub test_est_time: String,
    pub test_vmaf: f64,
    pub is_profitable: bool,
    pub test_crf: i32,
    pub metric: String,
}

#[derive(Clone)]
pub struct FileQueueState {
    pub files: std::sync::Arc<Mutex<Vec<FileEntry>>>,
    pub output_dir: std::sync::Arc<Mutex<Option<String>>>,
}

impl Default for FileQueueState {
    fn default() -> Self {
        Self {
            files: std::sync::Arc::new(Mutex::new(Vec::new())),
            output_dir: std::sync::Arc::new(Mutex::new(None)),
        }
    }
}

#[tauri::command]
pub async fn add_files(paths: Vec<String>, app: tauri::AppHandle, state: State<'_, FileQueueState>, analyzer: State<'_, Analyzer>) -> Result<Vec<FileEntry>, String> {
    info!("add_files called with {} path(s)", paths.len());
    let mut valid_paths = Vec::new();
    for path in &paths {
        if Path::new(path).exists() {
            valid_paths.push(path.clone());
        } else {
            error!("File does not exist: {}", path);
        }
    }

    let mut entries = Vec::new();
    for path in &valid_paths {
        entries.push(FileEntry {
            path: path.clone(),
            info: None,
            test_result: None,
            analysis_state: AnalysisState::Pending,
            error: None,
        });
    }

    {
        let mut files = state.files.lock().map_err(|e| {
            let msg = format!("Failed to lock file queue: {}", e);
            error!("{}", msg);
            msg
        })?;
        files.extend(entries.clone());
    }

    analyzer.enqueue(app, state.inner().clone(), valid_paths);
    info!("Queued {} file(s) for background analysis", entries.len());
    Ok(entries)
}

#[tauri::command]
pub fn remove_file(path: String, state: State<FileQueueState>) -> Result<(), String> {
    info!("remove_file called for path {}", path);
    let mut files = state.files.lock().map_err(|e| {
        let msg = format!("Failed to lock file queue: {}", e);
        error!("{}", msg);
        msg
    })?;
    let before = files.len();
    files.retain(|e| e.path != path);
    if files.len() == before {
        warn!("remove_file: path not found in queue: {}", path);
    }
    Ok(())
}

#[tauri::command]
pub fn get_file_list(state: State<FileQueueState>) -> Result<Vec<FileEntry>, String> {
    let files = state.files.lock().map_err(|e| {
        let msg = format!("Failed to lock file queue: {}", e);
        error!("{}", msg);
        msg
    })?;
    Ok(files.clone())
}

#[tauri::command]
pub fn set_output_dir(path: String, state: State<FileQueueState>) -> Result<(), String> {
    info!("set_output_dir: {}", path);
    let mut dir = state.output_dir.lock().map_err(|e| {
        let msg = format!("Failed to lock output dir: {}", e);
        error!("{}", msg);
        msg
    })?;
    *dir = Some(path);
    Ok(())
}

#[tauri::command]
pub fn get_output_dir(state: State<FileQueueState>) -> Result<Option<String>, String> {
    let dir = state.output_dir.lock().map_err(|e| {
        let msg = format!("Failed to lock output dir: {}", e);
        error!("{}", msg);
        msg
    })?;
    Ok(dir.clone())
}

#[tauri::command]
pub fn set_video_type(path: String, video_type: String, state: State<FileQueueState>) -> Result<(), String> {
    let parsed = match video_type.as_str() {
        "Animation" => crate::ffmpeg::probe::VideoType::Animation,
        "LiveAction" => crate::ffmpeg::probe::VideoType::LiveAction,
        "Rendered" => crate::ffmpeg::probe::VideoType::Rendered,
        _ => return Err(format!("Invalid video type: {}", video_type)),
    };
    info!("set_video_type: {} -> {}", path, parsed);

    crate::video_processor::content_type::set_override(&path, &parsed)?;

    let mut files = state.files.lock().map_err(|e| {
        let msg = format!("Failed to lock file queue: {}", e);
        error!("{}", msg);
        msg
    })?;
    for entry in files.iter_mut() {
        if entry.path == path {
            if let Some(info) = entry.info.as_mut() {
                info.video_type = parsed.clone();
                info!("Updated video_type in queue for {}: {:?}", path, parsed);
            }
        }
    }
    Ok(())
}

#[tauri::command]
pub fn clear_queue(state: State<FileQueueState>) -> Result<(), String> {
    info!("clear_queue called");
    let mut files = state.files.lock().map_err(|e| {
        let msg = format!("Failed to lock file queue: {}", e);
        error!("{}", msg);
        msg
    })?;
    files.clear();
    Ok(())
}
