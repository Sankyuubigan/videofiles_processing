use log::{LevelFilter, Log, Metadata, Record, SetLoggerError};
use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::PathBuf;
use std::sync::{Mutex, OnceLock};
use tauri::{AppHandle, Emitter};

static APP_HANDLE: OnceLock<AppHandle> = OnceLock::new();
static MAX_LEVEL: OnceLock<LevelFilter> = OnceLock::new();
static LOG_FILE: OnceLock<Mutex<std::fs::File>> = OnceLock::new();

/// Resolves the project `test/last_logs.txt` path by walking up from the
/// current executable until a `test/` directory is found (project root).
fn last_logs_path() -> Option<PathBuf> {
    let exe = std::env::current_exe().ok()?;
    let mut dir = exe.parent()?;
    loop {
        let test_dir = dir.join("test");
        if test_dir.is_dir() {
            let _ = fs::create_dir_all(&test_dir);
            return Some(test_dir.join("last_logs.txt"));
        }
        dir = dir.parent()?;
    }
}

pub struct TauriLogger;

impl Log for TauriLogger {
    fn enabled(&self, metadata: &Metadata) -> bool {
        metadata.level() <= *MAX_LEVEL.get_or_init(|| LevelFilter::Info)
    }

    fn log(&self, record: &Record) {
        if !self.enabled(record.metadata()) {
            return;
        }

        let ts = chrono::Local::now().format("%Y-%m-%d %H:%M:%S");
        let msg = format!("[{}] [{}] {}: {}", ts, record.level(), record.target(), record.args());

        eprintln!("{}", msg);

        if let Some(handle) = APP_HANDLE.get() {
            let _ = handle.emit("log-message", msg.clone());
        }

        if let Some(file) = LOG_FILE.get() {
            if let Ok(mut f) = file.lock() {
                let _ = writeln!(f, "{}", msg);
                let _ = f.flush();
            }
        }
    }

    fn flush(&self) {}
}

pub fn init(max_level: LevelFilter) -> Result<(), SetLoggerError> {
    let _ = MAX_LEVEL.set(max_level);

    if let Some(path) = last_logs_path() {
        let _ = fs::write(&path, "");
        if let Ok(f) = OpenOptions::new().create(true).append(true).open(&path) {
            let _ = LOG_FILE.set(Mutex::new(f));
        }
    }

    log::set_logger(&TauriLogger)?;
    log::set_max_level(max_level);
    Ok(())
}

pub fn set_app_handle(handle: AppHandle) {
    let _ = APP_HANDLE.set(handle);
}
