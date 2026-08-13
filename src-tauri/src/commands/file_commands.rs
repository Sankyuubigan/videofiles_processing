use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};
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
    #[serde(default)]
    pub error: Option<String>,
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

const VIDEO_EXTENSIONS: [&str; 5] = ["mp4", "avi", "mkv", "mov", "webm"];

fn is_video_file(path: &Path) -> bool {
    match path.extension().and_then(|e| e.to_str()) {
        Some(ext) => {
            let ext_lower = ext.to_ascii_lowercase();
            VIDEO_EXTENSIONS.contains(&ext_lower.as_str())
        }
        None => false,
    }
}

fn collect_video_files(path: &Path, out: &mut Vec<String>, depth: usize) {
    if path.is_file() {
        if is_video_file(path) {
            out.push(path.to_string_lossy().to_string());
        } else {
            info!("Skipping non-video file: {:?}", path);
        }
        return;
    }
    if path.is_dir() {
        if depth >= 20 {
            warn!("Directory scan depth limit reached, skipping: {:?}", path);
            return;
        }
        match std::fs::read_dir(path) {
            Ok(entries) => {
                let mut child_paths: Vec<PathBuf> = entries.filter_map(|e| e.ok().map(|e| e.path())).collect();
                child_paths.sort();
                for child in child_paths {
                    collect_video_files(&child, out, depth + 1);
                }
            }
            Err(e) => warn!("Failed to read directory {:?}: {}", path, e),
        }
    }
}

#[tauri::command]
pub async fn add_files(paths: Vec<String>, app: tauri::AppHandle, state: State<'_, FileQueueState>, analyzer: State<'_, Analyzer>) -> Result<Vec<FileEntry>, String> {
    info!("add_files called with {} path(s)", paths.len());
    let mut expanded_paths = Vec::new();
    for path in &paths {
        let p = Path::new(path);
        if !p.exists() {
            error!("Path does not exist: {}", path);
            continue;
        }
        if p.is_dir() {
            let before = expanded_paths.len();
            collect_video_files(p, &mut expanded_paths, 0);
            info!("Folder {:?} contributed {} video file(s)", path, expanded_paths.len() - before);
        } else if is_video_file(p) {
            expanded_paths.push(path.clone());
        } else {
            warn!("Skipping non-video file: {}", path);
        }
    }

    let mut existing_paths: Vec<String> = Vec::new();
    {
        let files = state.files.lock().map_err(|e| {
            let msg = format!("Failed to lock file queue: {}", e);
            error!("{}", msg);
            msg
        })?;
        existing_paths.extend(files.iter().map(|f| f.path.clone()));
    }
    let mut unique_paths = Vec::new();
    for path in expanded_paths {
        if existing_paths.contains(&path) {
            info!("Already in queue, skipping: {}", path);
            continue;
        }
        unique_paths.push(path);
    }

    let mut entries = Vec::new();
    for path in &unique_paths {
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

    analyzer.enqueue(app, state.inner().clone(), unique_paths);
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
pub fn clear_output_dir(state: State<FileQueueState>) -> Result<(), String> {
    info!("clear_output_dir");
    let mut dir = state.output_dir.lock().map_err(|e| {
        let msg = format!("Failed to lock output dir: {}", e);
        error!("{}", msg);
        msg
    })?;
    *dir = None;
    Ok(())
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
