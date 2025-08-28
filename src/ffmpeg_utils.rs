use crate::config::{AppConfig, OutputFormat};
use crate::ffmpeg_bin::{get_ffmpeg_path, get_ffprobe_path, is_ffmpeg_available};
use std::path::{Path, PathBuf};
use std::process::Command;
use serde_json::Value;

#[derive(Debug, Clone)]
pub struct VideoInfo {
    pub path: PathBuf,
    pub duration: f64,
    pub size_bytes: u64,
    pub bitrate: u64,
    pub width: u32,
    pub height: u32,
    pub fps: f64,
    pub needs_vfr_fix: bool,
    pub estimated_compressed_size: f64,
    pub gpu_info: String,
    pub processing_mode: String,
}

pub struct FFmpegUtils {
    config: AppConfig,
}

impl FFmpegUtils {
    pub fn new() -> Self {
        if !is_ffmpeg_available() {
            panic!("FFmpeg not available. Please ensure FFmpeg is installed or included with the application.");
        }
        
        Self {
            config: AppConfig::default(),
        }
    }
    
    pub async fn get_video_info(&self, path: &Path) -> VideoInfo {
        let path = path.to_path_buf();
        
        // Получаем информацию о видео через ffprobe
        let info_output = Command::new(get_ffprobe_path())
            .args([
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                path.to_str().unwrap()
            ])
            .output();
        
        let (duration, size_bytes, bitrate, width, height, fps, needs_vfr_fix) = match info_output {
            Ok(output) => {
                if let Ok(json) = serde_json::from_slice::<Value>(&output.stdout) {
                    Self::parse_video_info(&json)
                } else {
                    (0.0, 0, 0, 0, 0, 0.0, false)
                }
            }
            Err(_) => (0.0, 0, 0, 0, 0, 0.0, false),
        };
        
        // Расчет примерного размера после сжатия
        let estimated_compressed_size = if bitrate > 0 {
            (bitrate as f64 * 0.7 * duration) / 8.0 / 1024.0 / 1024.0 // Примерно 70% от оригинала
        } else {
            0.0
        };
        
        // Получаем информацию о GPU
        let gpu_info = self.get_gpu_info();
        
        // Определяем режим обработки
        let processing_mode = if self.is_gpu_available() {
            "GPU".to_string()
        } else {
            "CPU".to_string()
        };
        
        VideoInfo {
            path,
            duration,
            size_bytes,
            bitrate,
            width,
            height,
            fps,
            needs_vfr_fix,
            estimated_compressed_size,
            gpu_info,
            processing_mode,
        }
    }
    
    fn parse_video_info(json: &Value) -> (f64, u64, u64, u32, u32, f64, bool) {
        let mut duration = 0.0;
        let mut size_bytes = 0;
        let mut bitrate = 0;
        let mut width = 0;
        let mut height = 0;
        let mut fps = 0.0;
        let mut needs_vfr_fix = false;
        
        // Получаем информацию из формата
        if let Some(format) = json.get("format") {
            if let Some(dur) = format.get("duration").and_then(|d| d.as_str()) {
                duration = dur.parse().unwrap_or(0.0);
            }
            if let Some(size) = format.get("size").and_then(|s| s.as_str()) {
                size_bytes = size.parse().unwrap_or(0);
            }
            if let Some(bit) = format.get("bit_rate").and_then(|b| b.as_str()) {
                bitrate = bit.parse().unwrap_or(0);
            }
        }
        
        // Получаем информацию из потоков
        if let Some(streams) = json.get("streams").and_then(|s| s.as_array()) {
            for stream in streams {
                if let Some(codec_type) = stream.get("codec_type").and_then(|t| t.as_str()) {
                    if codec_type == "video" {
                        if let Some(w) = stream.get("width").and_then(|w| w.as_u64()) {
                            width = w as u32;
                        }
                        if let Some(h) = stream.get("height").and_then(|h| h.as_u64()) {
                            height = h as u32;
                        }
                        
                        // Получаем FPS
                        if let Some(r_frame_rate) = stream.get("r_frame_rate").and_then(|r| r.as_str()) {
                            if let Some(avg_frame_rate) = stream.get("avg_frame_rate").and_then(|a| a.as_str()) {
                                // Проверяем на VFR
                                if r_frame_rate == "1000/1" || r_frame_rate == "0/0" || avg_frame_rate == "0/0" {
                                    needs_vfr_fix = true;
                                }
                                
                                // Парсим FPS
                                if let Some((num, den)) = avg_frame_rate.split_once('/') {
                                    let num: f64 = num.parse().unwrap_or(0.0);
                                    let den: f64 = den.parse().unwrap_or(1.0);
                                    if den != 0.0 {
                                        fps = num / den;
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        
        (duration, size_bytes, bitrate, width, height, fps, needs_vfr_fix)
    }
    
    pub async fn compress_video<F>(
        &self,
        input_path: &Path,
        output_format: OutputFormat,
        crf_value: u8,
        force_vfr_fix: bool,
        progress_callback: F,
    ) -> Result<PathBuf, String>
    where
        F: Fn(f32) + Send + 'static + Clone,
    {
        let input_path = input_path.to_path_buf();
        
        // Получаем информацию о видео
        let video_info = self.get_video_info(&input_path).await;
        
        // Определяем пути для временных файлов
        let temp_file = if force_vfr_fix || video_info.needs_vfr_fix {
            let mut temp_path = input_path.clone();
            let extension = temp_path.extension().unwrap().to_str().unwrap();
            temp_path.set_file_name(format!(
                "{}_temp_fixed_cfr.{}",
                temp_path.file_stem().unwrap().to_str().unwrap(),
                extension
            ));
            Some(temp_path)
        } else {
            None
        };
        
        // Формируем путь для выходного файла
        let output_path = {
            let mut output_path = input_path.clone();
            output_path.set_file_name(format!(
                "{}_compressed.{}",
                output_path.file_stem().unwrap().to_str().unwrap(),
                output_format.extension()
            ));
            output_path
        };
        
        // Если нужно исправление VFR
        if let Some(ref temp_path) = temp_file {
            self.fix_vfr(&input_path, temp_path, progress_callback.clone()).await?;
        }
        
        // Сжатие видео
        let current_input = temp_file.as_ref().unwrap_or(&input_path);
        self.compress_video_core(
            current_input,
            &output_path,
            output_format,
            crf_value,
            progress_callback,
        ).await?;
        
        // Удаляем временный файл, если он был создан
        if let Some(ref temp_path) = temp_file {
            std::fs::remove_file(temp_path).map_err(|e| format!("Ошибка удаления временного файла: {}", e))?;
        }
        
        Ok(output_path)
    }
    
    async fn fix_vfr<F>(&self, input_path: &Path, output_path: &Path, progress_callback: F) -> Result<(), String>
    where
        F: Fn(f32) + Send + 'static + Clone,
    {
        let input_path = input_path.to_path_buf();
        let output_path = output_path.to_path_buf();
        
        tokio::task::spawn_blocking(move || {
            let output = Command::new(get_ffmpeg_path())
                .args([
                    "-y",
                    "-i", input_path.to_str().unwrap(),
                    "-vf", "fps=25",
                    "-c:v", "libx264",
                    "-crf", "18",
                    "-preset", "medium",
                    "-c:a", "copy",
                    output_path.to_str().unwrap()
                ])
                .output();
            
            match output {
                Ok(_) => {
                    progress_callback(0.5);
                    Ok(())
                }
                Err(e) => Err(format!("Ошибка при исправлении VFR: {}", e)),
            }
        }).await.map_err(|e| format!("Ошибка при исправлении VFR: {}", e))?
    }
    
    async fn compress_video_core<F>(
        &self,
        input_path: &Path,
        output_path: &Path,
        output_format: OutputFormat,
        crf_value: u8,
        progress_callback: F,
    ) -> Result<(), String>
    where
        F: Fn(f32) + Send + 'static + Clone,
    {
        let input_path = input_path.to_path_buf();
        let output_path = output_path.to_path_buf();
        
        tokio::task::spawn_blocking(move || {
            let mut args = vec![
                "-y".to_string(),
                "-i".to_string(),
                input_path.to_str().unwrap().to_string(),
            ];
            
            // Проверяем доступность GPU и выбираем энкодер
            let gpu_check = Command::new(get_ffmpeg_path())
                .args(["-encoders"])
                .output();
            
            let use_gpu = if let Ok(output) = gpu_check {
                let output_str = String::from_utf8_lossy(&output.stdout);
                output_str.contains("nvenc") || output_str.contains("amf") || output_str.contains("qsv")
            } else {
                false
            };
            
            // Добавляем параметры для видео
            if output_format == OutputFormat::WebM {
                if use_gpu {
                    args.extend([
                        "-c:v".to_string(),
                        "vp9_nvenc".to_string(),
                        "-crf".to_string(),
                        crf_value.to_string(),
                        "-b:v".to_string(),
                        "0".to_string(),
                        "-rc".to_string(),
                        "vbr".to_string(),
                    ]);
                } else {
                    args.extend([
                        "-c:v".to_string(),
                        "libvpx-vp9".to_string(),
                        "-crf".to_string(),
                        crf_value.to_string(),
                        "-b:v".to_string(),
                        "0".to_string(),
                        "-deadline".to_string(),
                        "good".to_string(),
                        "-cpu-used".to_string(),
                        "2".to_string(),
                    ]);
                }
            } else {
                if use_gpu {
                    args.extend([
                        "-c:v".to_string(),
                        "h264_nvenc".to_string(),
                        "-crf".to_string(),
                        crf_value.to_string(),
                        "-preset".to_string(),
                        "medium".to_string(),
                        "-tune".to_string(),
                        "ll".to_string(),
                    ]);
                } else {
                    args.extend([
                        "-c:v".to_string(),
                        "libx264".to_string(),
                        "-crf".to_string(),
                        crf_value.to_string(),
                        "-preset".to_string(),
                        "medium".to_string(),
                        "-pix_fmt".to_string(),
                        "yuv420p".to_string(),
                        "-vf".to_string(),
                        "pad=ceil(iw/2)*2:ceil(ih/2)*2".to_string(),
                    ]);
                }
                
                if output_format == OutputFormat::MP4 {
                    args.extend([
                        "-movflags".to_string(),
                        "+faststart".to_string(),
                    ]);
                }
            }
            
            // Добавляем параметры для аудио
            if output_format == OutputFormat::WebM {
                args.extend([
                    "-c:a".to_string(),
                    "libopus".to_string(),
                    "-b:a".to_string(),
                    "128k".to_string(),
                ]);
            } else {
                args.extend([
                    "-c:a".to_string(),
                    "aac".to_string(),
                    "-b:a".to_string(),
                    "128k".to_string(),
                ]);
            }
            
            args.push(output_path.to_str().unwrap().to_string());
            
            let output = Command::new(get_ffmpeg_path())
                .args(&args)
                .output();
            
            match output {
                Ok(_) => {
                    progress_callback(1.0);
                    Ok(())
                }
                Err(e) => Err(format!("Ошибка при сжатии видео: {}", e)),
            }
        }).await.map_err(|e| format!("Ошибка при сжатии видео: {}", e))?
    }
    
    fn get_gpu_info(&self) -> String {
        // Проверяем доступные GPU через FFmpeg
        let output = Command::new(get_ffmpeg_path())
            .args(["-encoders"])
            .output();
        
        match output {
            Ok(output) => {
                let output_str = String::from_utf8_lossy(&output.stdout);
                
                // Ищем доступные GPU энкодеры
                let mut gpu_encoders = Vec::new();
                
                if output_str.contains("h264_nvenc") {
                    gpu_encoders.push("NVIDIA NVENC (h264)");
                }
                if output_str.contains("hevc_nvenc") {
                    gpu_encoders.push("NVIDIA NVENC (hevc)");
                }
                if output_str.contains("h264_amf") {
                    gpu_encoders.push("AMD AMF (h264)");
                }
                if output_str.contains("hevc_amf") {
                    gpu_encoders.push("AMD AMF (hevc)");
                }
                if output_str.contains("h264_qsv") {
                    gpu_encoders.push("Intel Quick Sync (h264)");
                }
                if output_str.contains("hevc_qsv") {
                    gpu_encoders.push("Intel Quick Sync (hevc)");
                }
                
                if gpu_encoders.is_empty() {
                    "GPU не обнаружены".to_string()
                } else {
                    format!("Доступные GPU: {}", gpu_encoders.join(", "))
                }
            }
            Err(_) => "Не удалось получить информацию о GPU".to_string(),
        }
    }
    
    fn is_gpu_available(&self) -> bool {
        let output = Command::new(get_ffmpeg_path())
            .args(["-encoders"])
            .output();
        
        match output {
            Ok(output) => {
                let output_str = String::from_utf8_lossy(&output.stdout);
                output_str.contains("nvenc") || output_str.contains("amf") || output_str.contains("qsv")
            }
            Err(_) => false,
        }
    }
}