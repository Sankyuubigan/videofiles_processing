use crate::video_processor::compress::get_full_video_info;
use crate::ffmpeg::probe::VideoInfo;

#[tauri::command]
pub fn get_video_details(file_path: String) -> Result<VideoInfo, String> {
    get_full_video_info(&file_path)
}

#[tauri::command]
pub fn get_gpu_info_cmd() -> Result<String, String> {
    Ok(crate::ffmpeg::probe::get_gpu_info())
}
