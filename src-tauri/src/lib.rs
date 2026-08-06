mod config;
mod settings;
mod ffmpeg;
mod video_processor;
mod crf_extractor;
mod estimator;
mod commands;
mod tauri_logger;
mod process_control;
mod nn_quality;

use log::{info, warn};
use std::sync::Arc;
use commands::file_commands::FileQueueState;
use commands::compress_commands::ProcessingState;
use ffmpeg::preview::PreviewJobsState;
use ffmpeg::stream_server::StreamState;
use video_processor::analyzer::Analyzer;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri_logger::init(log::LevelFilter::Debug).expect("Failed to initialize logger");
    info!("Starting VideoFile Pro");

    let stream_port = ffmpeg::stream_server::start_stream_server();

    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_shell::init())
        .manage(FileQueueState::default())
        .manage(ProcessingState::default())
        .manage(Analyzer::default())
        .manage(Arc::new(PreviewJobsState::default()))
        .manage(StreamState { port: stream_port })
        .setup(|app| {
            let handle = app.handle().clone();
            tauri_logger::set_app_handle(handle.clone());
            info!("Application started");

            // Clean up stale preview cache from previous runs
            tauri::async_runtime::spawn(async move {
                ffmpeg::preview::cleanup_old_previews();
            });

            // Initialize ORT for content type classification (neural network)
            if let Err(e) = crate::nn_quality::session::init_ort() {
                warn!("Failed to initialize ORT (content type classification unavailable): {}", e);
            }

            // Auto-download mediainfo if not present (needed for CRF detection)
            tauri::async_runtime::spawn(async move {
                if !std::path::Path::new(&crate::settings::get_mediainfo_path()).exists() {
                    info!("mediainfo.exe not found, auto-downloading...");
                    let _ = crate::ffmpeg::downloader::download_mediainfo(|msg| {
                        info!("{}", msg);
                    }).await;
                }
            });

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            commands::file_commands::add_files,
            commands::file_commands::remove_file,
            commands::file_commands::get_file_list,
            commands::file_commands::set_output_dir,
            commands::file_commands::get_output_dir,
            commands::file_commands::clear_output_dir,
            commands::file_commands::clear_queue,
            commands::file_commands::set_video_type,
            commands::compress_commands::start_compress,
            commands::compress_commands::start_batch_compress,
            commands::compress_commands::cancel_processing,
            commands::compress_commands::pause_processing,
            commands::compress_commands::resume_processing,
            commands::test_commands::run_chunk_test_cmd,
            commands::test_commands::run_batch_test,
            commands::edit_commands::trim_video_cmd,
            commands::edit_commands::normalize_audio_cmd,
            commands::edit_commands::extract_frame_cmd,
            commands::settings_commands::load_settings_cmd,
            commands::settings_commands::save_settings_cmd,
            commands::settings_commands::check_ffmpeg_cmd,
            commands::settings_commands::download_ffmpeg_cmd,
            commands::settings_commands::download_mediainfo_cmd,
            commands::info_commands::get_video_details,
            commands::info_commands::get_gpu_info_cmd,
            commands::compare_commands::get_stream_url,
            commands::preview_commands::generate_preview_gif_cmd,
            commands::preview_commands::prepare_preview_cmd,
            commands::preview_commands::cancel_preview_cmd,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
