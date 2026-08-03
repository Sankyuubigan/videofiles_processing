use std::path::PathBuf;
use log::warn;

pub const CONTENT_TYPE_MODEL_FILENAME: &str = "content_classifier_b0.onnx";

/// Get the directory where NN models are stored
pub fn models_dir() -> PathBuf {
    let exe_dir = match std::env::current_exe() {
        Ok(p) => p.parent().map(|p| p.to_path_buf()),
        Err(e) => {
            warn!("current_exe() failed in models_dir: {}", e);
            None
        }
    }
    .unwrap_or_else(|| std::env::current_dir().unwrap_or_default());

    exe_dir.join("nn_models")
}

/// Get full path to content type classifier model
pub fn content_type_model_path() -> PathBuf {
    models_dir().join(CONTENT_TYPE_MODEL_FILENAME)
}


