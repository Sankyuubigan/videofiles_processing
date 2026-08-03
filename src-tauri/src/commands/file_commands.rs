use serde::{Deserialize, Serialize};
use std::path::Path;
use std::sync::Mutex;
use tauri::State;
use log::{info, error};

use crate::video_processor::compress::get_full_video_info;
use crate::ffmpeg::probe::VideoInfo;
use super::test_commands::NnTestResult;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FileEntry {
    pub path: String,
    pub info: Option<VideoInfo>,
    pub test_result: Option<TestResult>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub nn_test_result: Option<NnTestResult>,
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

pub struct FileQueueState {
    pub files: Mutex<Vec<FileEntry>>,
    pub output_dir: Mutex<Option<String>>,
}

impl Default for FileQueueState {
    fn default() -> Self {
        Self {
            files: Mutex::new(Vec::new()),
            output_dir: Mutex::new(None),
        }
    }
}

#[tauri::command]
pub async fn add_files(paths: Vec<String>, state: tauri::State<'_, FileQueueState>) -> Result<Vec<FileEntry>, String> {
    info!("add_files called with {} path(s)", paths.len());
    let mut valid_paths = Vec::new();
    for path in &paths {
        if Path::new(path).exists() {
            valid_paths.push(path.clone());
        } else {
            error!("File does not exist: {}", path);
        }
    }

    let handles: Vec<_> = valid_paths.into_iter().map(|path| {
        std::thread::spawn(move || {
            info!("Processing file: {}", path);
            let entry_info = match get_full_video_info(&path) {
                Ok(info) => Some(info),
                Err(e) => {
                    error!("Failed to get video info for {}: {}", path, e);
                    None
                }
            };
            FileEntry { path, info: entry_info, test_result: None, nn_test_result: None }
        })
    }).collect();

    let mut added = Vec::new();
    {
        let mut files = state.files.lock().map_err(|e| {
            let msg = format!("Failed to lock file queue: {}", e);
            error!("{}", msg);
            msg
        })?;
        for h in handles {
            if let Ok(entry) = h.join() {
                added.push(entry.clone());
                files.push(entry);
            }
        }
    }
    info!("Added {} files, total in queue: {}", added.len(), added.len());
    Ok(added)
}

#[tauri::command]
pub fn remove_file(index: usize, state: State<FileQueueState>) -> Result<(), String> {
    info!("remove_file called for index {}", index);
    let mut files = state.files.lock().map_err(|e| {
        let msg = format!("Failed to lock file queue: {}", e);
        error!("{}", msg);
        msg
    })?;
    if index < files.len() { files.remove(index); }
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
