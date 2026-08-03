use std::sync::mpsc::{self, Receiver, Sender};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use log::{error, info, warn};
use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Emitter};

use crate::commands::file_commands::{FileEntry, FileQueueState};
use crate::video_processor::compress::get_video_info_basic;

const WORKER_COUNT: usize = 3;

#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum AnalysisState {
    Pending,
    Probing,
    Detecting,
    Done,
    Failed,
}

impl Default for AnalysisState {
    fn default() -> Self {
        AnalysisState::Pending
    }
}

pub struct Analyzer {
    tx: Mutex<Option<Sender<String>>>,
    rx: Arc<Mutex<Receiver<String>>>,
    started: AtomicBool,
}

impl Default for Analyzer {
    fn default() -> Self {
        let (tx, rx) = mpsc::channel();
        Self {
            tx: Mutex::new(Some(tx)),
            rx: Arc::new(Mutex::new(rx)),
            started: AtomicBool::new(false),
        }
    }
}

impl Analyzer {
    pub fn enqueue(&self, app: AppHandle, queue: FileQueueState, paths: Vec<String>) {
        let guard = match self.tx.lock() {
            Ok(g) => g,
            Err(_) => return,
        };
        let tx = match guard.as_ref() {
            Some(tx) => tx,
            None => return,
        };
        for path in paths {
            if let Err(e) = tx.send(path) {
                warn!("Failed to enqueue file for analysis: {}", e);
                break;
            }
        }
        drop(guard);

        if !self.started.swap(true, Ordering::SeqCst) {
            let rx = self.rx.clone();
            for _ in 0..WORKER_COUNT {
                let app = app.clone();
                let queue = queue.clone();
                let rx = rx.clone();
                std::thread::spawn(move || worker_loop(app, queue, rx));
            }
        }
    }
}

fn worker_loop(app: AppHandle, queue: FileQueueState, rx: Arc<Mutex<Receiver<String>>>) {
    loop {
        let path = {
            let guard = match rx.lock() {
                Ok(g) => g,
                Err(_) => return,
            };
            match guard.recv() {
                Ok(p) => p,
                Err(_) => return,
            }
        };
        analyze_file(app.clone(), queue.clone(), path);
    }
}

fn analyze_file(app: AppHandle, queue: FileQueueState, path: String) {
    let state = AnalysisState::Probing;
    emit_and_update(&app, &queue, &path, |entry| {
        entry.info = None;
        entry.error = None;
        entry.analysis_state = state;
    });

    let basic = get_video_info_basic(&path);
    let mut info = match basic {
        Ok(info) => info,
        Err(e) => {
            error!("Failed to analyze {}: {}", path, e);
            emit_and_update(&app, &queue, &path, |entry| {
                entry.error = Some(e.clone());
                entry.analysis_state = AnalysisState::Failed;
            });
            return;
        }
    };

    let duration = info.duration;
    emit_and_update(&app, &queue, &path, |entry| {
        entry.info = Some(info.clone());
        entry.error = None;
        entry.analysis_state = AnalysisState::Detecting;
    });

    let video_type = crate::video_processor::content_type::detect_content_type(&path, duration);
    let final_type = crate::video_processor::content_type::get_override(&path).unwrap_or(video_type);
    info!("Content type for {}: {:?}", path, final_type);
    info.video_type = final_type;

    emit_and_update(&app, &queue, &path, |entry| {
        entry.info = Some(info.clone());
        entry.error = None;
        entry.analysis_state = AnalysisState::Done;
    });
}

fn emit_and_update(
    app: &AppHandle,
    queue: &FileQueueState,
    path: &str,
    update: impl FnOnce(&mut FileEntry),
) {
    let entry = {
        let mut files = match queue.files.lock() {
            Ok(g) => g,
            Err(e) => {
                error!("Failed to lock file queue for {}: {}", path, e);
                return;
            }
        };
        match files.iter_mut().find(|e| e.path == path) {
            Some(entry) => {
                update(entry);
                entry.clone()
            }
            None => return,
        }
    };
    let _ = app.emit("file-entry-updated", entry);
}
