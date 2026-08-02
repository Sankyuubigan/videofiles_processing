use std::sync::Mutex;
use log::{info, error};
use ort::session::Session;

use super::models;

pub(crate) static LPIPS_SESSION: Mutex<Option<Session>> = Mutex::new(None);
pub(crate) static DISTS_SESSION: Mutex<Option<Session>> = Mutex::new(None);

/// Initialize ORT environment (call once at startup)
pub fn init_ort() -> Result<(), String> {
    let inited = ort::init()
        .with_name("VideoFilePro")
        .commit();
    if !inited {
        return Err("ORT already initialized or failed".to_string());
    }
    info!("ORT initialized successfully");
    Ok(())
}

/// Ensure LPIPS session is loaded (lazy singleton)
pub fn ensure_lpips_loaded() -> Result<(), String> {
    let mut guard = LPIPS_SESSION.lock().map_err(|e| {
        let msg = format!("Failed to lock LPIPS session mutex: {}", e);
        error!("{}", msg);
        msg
    })?;
    if guard.is_some() {
        return Ok(());
    }

    let model_path = models::lpips_model_path();
    if !model_path.exists() {
        return Err(format!(
            "LPIPS model not found at {:?}. Place the ONNX model file there manually.",
            model_path
        ));
    }

    info!("Loading LPIPS ONNX model from {:?}", model_path);
    let session = Session::builder()
        .map_err(|e| format!("Failed to build LPIPS session: {}", e))?
        .commit_from_file(&model_path)
        .map_err(|e| format!("Failed to load LPIPS model from {:?}: {}", model_path, e))?;

    *guard = Some(session);
    info!("LPIPS session loaded successfully");
    Ok(())
}

/// Ensure DISTS session is loaded (lazy singleton)
pub fn ensure_dists_loaded() -> Result<(), String> {
    let mut guard = DISTS_SESSION.lock().map_err(|e| {
        let msg = format!("Failed to lock DISTS session mutex: {}", e);
        error!("{}", msg);
        msg
    })?;
    if guard.is_some() {
        return Ok(());
    }

    let model_path = models::dists_model_path();
    if !model_path.exists() {
        return Err(format!(
            "DISTS model not found at {:?}. Place the ONNX model file there manually.",
            model_path
        ));
    }

    info!("Loading DISTS ONNX model from {:?}", model_path);
    let session = Session::builder()
        .map_err(|e| format!("Failed to build DISTS session: {}", e))?
        .commit_from_file(&model_path)
        .map_err(|e| format!("Failed to load DISTS model from {:?}: {}", model_path, e))?;

    *guard = Some(session);
    info!("DISTS session loaded successfully");
    Ok(())
}
