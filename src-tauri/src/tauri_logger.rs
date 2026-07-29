use log::{LevelFilter, Log, Metadata, Record, SetLoggerError};
use std::sync::OnceLock;
use tauri::{AppHandle, Emitter};

static APP_HANDLE: OnceLock<AppHandle> = OnceLock::new();
static MAX_LEVEL: OnceLock<LevelFilter> = OnceLock::new();

pub struct TauriLogger;

impl Log for TauriLogger {
    fn enabled(&self, metadata: &Metadata) -> bool {
        metadata.level() <= *MAX_LEVEL.get_or_init(|| LevelFilter::Info)
    }

    fn log(&self, record: &Record) {
        if !self.enabled(record.metadata()) {
            return;
        }

        let msg = format!("[{}] {}: {}", record.level(), record.target(), record.args());

        eprintln!("{}", msg);

        if let Some(handle) = APP_HANDLE.get() {
            let _ = handle.emit("log-message", msg);
        }
    }

    fn flush(&self) {}
}

pub fn init(max_level: LevelFilter) -> Result<(), SetLoggerError> {
    let _ = MAX_LEVEL.set(max_level);
    log::set_logger(&TauriLogger)?;
    log::set_max_level(max_level);
    Ok(())
}

pub fn set_app_handle(handle: AppHandle) {
    let _ = APP_HANDLE.set(handle);
}
