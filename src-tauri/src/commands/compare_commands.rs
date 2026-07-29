use tauri::State;
use crate::ffmpeg::stream_server::StreamState;

#[tauri::command]
pub fn get_stream_url(state: State<StreamState>) -> Result<String, String> {
    Ok(format!("http://127.0.0.1:{}", state.port))
}
