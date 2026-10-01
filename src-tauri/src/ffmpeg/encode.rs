use std::sync::Arc;
use std::sync::atomic::AtomicBool;
use log::{info, warn};

use super::core::{run_command_with_progress, run_command_simple, RunResult};
use super::probe::{get_gpu_info, VideoType};
use crate::process_control::PidTracker;

pub fn chunk_timeline(source_start: f64) -> (f64, f64) {
    let fast_seek = (source_start - 10.0).max(0.0);
    let trim_start = source_start - fast_seek;
    (fast_seek, trim_start)
}

/// Единственный источник правды (SSOT): нужен ли фильтр `pad` для чётных размеров.
///
/// libx264 с 8-битным pix_fmt (`yuv420p`) аппаратно требует чётные width/height.
/// Свойство относится к энкодеру, а не к тайм-линии, поэтому не зависит от VFR-фикса:
/// проверка должна быть одинаковой в энкодере, в VMAF-эталоне и в финальном mux-е.
/// Ошибка здесь = рассогласование размеров чанка и эталона -> падение libvmaf.
pub fn needs_x264_pad(codec: &str, use_hardware: bool) -> bool {
    codec == "libx264" && !use_hardware
}

fn get_content_type_flags(video_type: &VideoType, codec: &str, use_hardware: bool, has_nvenc: bool) -> Vec<String> {
    let mut flags = Vec::new();

    if use_hardware && has_nvenc {
        return flags;
    }

    match video_type {
        VideoType::Animation => {
            match codec {
                "libx265" => {
                    flags.extend(vec![
                        "-tune".to_string(), "animation".to_string(),
                        "-x265-params".to_string(), "aq-mode=3:bframes=8:psy-rd=1.0".to_string(),
                    ]);
                }
                "libx264" => {
                    flags.extend(vec![
                        "-tune".to_string(), "animation".to_string(),
                    ]);
                }
                _ => {}
            }
        }
        VideoType::LiveAction => {}
        VideoType::Rendered => {}
    }

    flags
}

/// `-c:v libsvtav1` аргументы: числовой preset, CRF и параметры из av1-модуля
/// (keyint=10s, tune, scd, film-grain, 10-bit pix_fmt). Hardware для AV1 не используется.
fn svtav1_encode_args(crf_value: i32, preset_value: &str, video_type: &VideoType, grain_ydif: Option<f64>, lp: Option<usize>) -> Vec<String> {
    let mut args = vec![
        "-c:v".to_string(),
        "libsvtav1".to_string(),
        "-crf".to_string(),
        crf_value.to_string(),
        "-preset".to_string(),
        preset_value.to_string(),
    ];
    args.extend(crate::av1::svtav1_args(video_type, grain_ydif, lp));
    args
}

/// Для libsvtav1 FFmpeg не пишет Encoded_Library_Settings (в отличие от x264/x265),
/// поэтому mediainfo/ffprobe не могут найти CRF в готовом файле. Пишем его сами.
///
/// Важно: MP4-муксер ffmpeg отбрасывает нестандартные stream-теги (в т.ч.
/// `EncoderSettings`), поэтому используем стандартное поле `comment`, которое
/// сохраняется и читается и mediainfo, и ffprobe во всех контейнерах (mp4/mkv/webm).
pub(crate) fn svtav1_crf_metadata(crf_value: i32, _output_format: &str) -> Vec<String> {
    vec![
        "-metadata".to_string(),
        format!("comment=crf={}", crf_value),
    ]
}

/// Аудио-кодеки: Opus 112k стерео для AV1/VP9 (дока), иначе AAC 192k.
/// Единственный источник правды (SSOT) для аудио во всех путях сжатия:
/// одиночный энкод и параллельный mux обязаны давать одинаковый результат.
pub(crate) fn audio_args(codec: &str) -> Vec<String> {
    if codec == "libsvtav1" || codec == "libvpx-vp9" {
        vec![
            "-c:a".to_string(),
            "libopus".to_string(),
            "-b:a".to_string(),
            "112k".to_string(),
            "-ac".to_string(),
            "2".to_string(),
        ]
    } else {
        vec![
            "-c:a".to_string(),
            "aac".to_string(),
            "-b:a".to_string(),
            "192k".to_string(),
        ]
    }
}

pub fn fix_vfr_target_crf(
    input_path: &str, output_path: &str, output_format: &str, codec: &str, crf_value: i32,
    preset_value: &str, duration_seconds: f64, use_hardware: bool, video_info: &super::probe::VideoInfo,
    video_type: &VideoType,
    cancel_flag: Arc<AtomicBool>, progress_cb: Option<Arc<dyn Fn(i32, String) + Send + Sync>>,
    child_pid: Option<PidTracker>,
    svtav1_lp: Option<usize>,
) -> RunResult {
    let gpu_info = get_gpu_info();
    let has_nvenc = gpu_info.contains("NVIDIA NVENC");
    let mut cmd = vec!["ffmpeg".to_string(), "-y".to_string()];
    if video_info.is_hevc && has_nvenc {
        cmd.extend(["-hwaccel".to_string(), "cuda".to_string()]);
    }
    cmd.extend(["-i".to_string(), input_path.to_string()]);
    let mut vf_filters = vec![format!("fps={}", video_info.vfr_fix_fps)];
    
    // Не используем yuv420p для 10-bit источников (потому что цвет оставляем как есть).
    // Для libsvtav1 битность задаётся через `-pix_fmt yuv420p10le` (av1-модуль).
    if video_info.is_10bit && codec != "libx265" && codec != "libsvtav1" {
        vf_filters.push("format=yuv420p".to_string());
    }
    if needs_x264_pad(codec, use_hardware) {
        vf_filters.push("pad=ceil(iw/2)*2:ceil(ih/2)*2".to_string());
    }
    
    cmd.extend(["-vf".to_string(), vf_filters.join(",")]);
    match codec {
        "libvpx-vp9" => {
            if use_hardware && has_nvenc {
                cmd.extend(["-c:v".to_string(), "vp9_nvenc".to_string(), "-crf".to_string(), crf_value.to_string(), "-b:v".to_string(), "0".to_string()]);
            } else {
                cmd.extend(["-c:v".to_string(), "libvpx-vp9".to_string(), "-crf".to_string(), crf_value.to_string(), "-b:v".to_string(), "0".to_string(), "-deadline".to_string(), "good".to_string(), "-cpu-used".to_string(), "2".to_string()]);
            }
            cmd.extend(["-c:a".to_string(), "copy".to_string()]);
        }
        "libsvtav1" => {
            cmd.extend(svtav1_encode_args(crf_value, preset_value, video_type, video_info.grain_ydif, svtav1_lp));
            cmd.extend(svtav1_crf_metadata(crf_value, output_format));
            cmd.extend(["-c:a".to_string(), "copy".to_string()]);
        }
        "libx265" => {
            if use_hardware && has_nvenc {
                cmd.extend(["-c:v".to_string(), "hevc_nvenc".to_string(), "-crf".to_string(), crf_value.to_string(), "-preset".to_string(), "p6".to_string(), "-tune".to_string(), "ll".to_string()]);
            } else {
                cmd.extend(["-c:v".to_string(), "libx265".to_string(), "-crf".to_string(), crf_value.to_string(), "-preset".to_string(), preset_value.to_string()]);
                cmd.extend(get_content_type_flags(video_type, codec, use_hardware, has_nvenc));
            }
            cmd.extend(["-c:a".to_string(), "copy".to_string()]);
        }
        _ => {
            if use_hardware && has_nvenc {
                cmd.extend(["-c:v".to_string(), "h264_nvenc".to_string(), "-cq".to_string(), crf_value.to_string(), "-preset".to_string(), "p6".to_string(), "-tune".to_string(), "ll".to_string()]);
            } else {
                cmd.extend(["-c:v".to_string(), "libx264".to_string(), "-crf".to_string(), crf_value.to_string(), "-preset".to_string(), preset_value.to_string()]);
                cmd.extend(get_content_type_flags(video_type, codec, use_hardware, has_nvenc));
            }
            cmd.extend(["-c:a".to_string(), "copy".to_string()]);
        }
    }
    if video_info.has_subtitles {
        if output_format == "mp4" {
            cmd.extend(["-c:s".to_string(), "mov_text".to_string()]);
        } else {
            cmd.extend(["-c:s".to_string(), "copy".to_string()]);
        }
        cmd.extend(["-map".to_string(), "0:V".to_string(), "-map".to_string(), "0:a".to_string(), "-map".to_string(), "0:s".to_string()]);
    } else {
        cmd.extend(["-map".to_string(), "0:V".to_string(), "-map".to_string(), "0:a".to_string()]);
    }
    if output_format == "mp4" {
        cmd.extend(["-movflags".to_string(), "+faststart".to_string()]);
    }
    cmd.extend(["-progress".to_string(), "pipe:1".to_string(), output_path.to_string()]);
    run_command_with_progress(&cmd, Some(duration_seconds), "VFR-fix+compress", cancel_flag, progress_cb, child_pid)
}

pub fn fix_vfr_only_core(
    input_path: &str, output_path: &str, duration_seconds: f64, video_info: &super::probe::VideoInfo,
    cancel_flag: Arc<AtomicBool>, progress_cb: Option<Arc<dyn Fn(i32, String) + Send + Sync>>,
    child_pid: Option<PidTracker>,
    svtav1_lp: Option<usize>,
) -> RunResult {
    let gpu_info = get_gpu_info();
    let has_nvenc = gpu_info.contains("NVIDIA NVENC");
    let mut cmd = vec!["ffmpeg".to_string(), "-y".to_string()];
    if video_info.is_hevc && has_nvenc {
        cmd.extend(["-hwaccel".to_string(), "cuda".to_string()]);
    }
    cmd.extend(["-i".to_string(), input_path.to_string()]);

    // Пережимаем видео в исходном кодеке с высоким качеством, выравнивая тайм-линию по fps.
    let encoder = match video_info.video_codec.as_str() {
        "hevc" => "libx265",
        "vp9" => "libvpx-vp9",
        "av1" => "libsvtav1",
        _ => "libx264",
    };

    let mut vf_filters = vec![format!("fps={}", video_info.vfr_fix_fps)];
    // 10-бит сохраняем как есть для libx265, остальным кодеком оставляем глубину yuv420p.
    // Для libsvtav1 битность задаётся через `-pix_fmt yuv420p10le` (av1-модуль).
    if video_info.is_10bit && encoder != "libx265" {
        if encoder == "libx264" {
            vf_filters.push("format=yuv420p10le".to_string());
        } else if encoder != "libsvtav1" {
            vf_filters.push("format=yuv420p".to_string());
        }
    }
    cmd.extend(["-vf".to_string(), vf_filters.join(",")]);

    let crf = if video_info.is_10bit { 15 } else { 16 };
    match encoder {
        "libx265" => {
            cmd.extend(["-c:v".to_string(), "libx265".to_string(), "-crf".to_string(), crf.to_string(), "-preset".to_string(), "slow".to_string()]);
        }
        "libvpx-vp9" => {
            cmd.extend(["-c:v".to_string(), "libvpx-vp9".to_string(), "-crf".to_string(), "16".to_string(), "-b:v".to_string(), "0".to_string(), "-deadline".to_string(), "good".to_string(), "-cpu-used".to_string(), "2".to_string()]);
        }
        "libsvtav1" => {
            cmd.extend(["-c:v".to_string(), "libsvtav1".to_string(), "-crf".to_string(), "16".to_string(), "-preset".to_string(), "6".to_string()]);
            cmd.extend(crate::av1::svtav1_args(&video_info.video_type, video_info.grain_ydif, svtav1_lp));
            let out_fmt = std::path::Path::new(output_path)
                .extension().map(|e| e.to_string_lossy().to_lowercase()).unwrap_or_default();
            cmd.extend(svtav1_crf_metadata(16, &out_fmt));
        }
        _ => {
            cmd.extend(["-c:v".to_string(), "libx264".to_string(), "-crf".to_string(), crf.to_string(), "-preset".to_string(), "slow".to_string()]);
        }
    }
    cmd.extend(["-c:a".to_string(), "copy".to_string()]);
    if video_info.has_subtitles {
        cmd.extend(["-c:s".to_string(), "copy".to_string()]);
        cmd.extend(["-map".to_string(), "0:V".to_string(), "-map".to_string(), "0:a".to_string(), "-map".to_string(), "0:s".to_string()]);
    } else {
        cmd.extend(["-map".to_string(), "0:V".to_string(), "-map".to_string(), "0:a".to_string()]);
    }
    cmd.extend(["-progress".to_string(), "pipe:1".to_string(), output_path.to_string()]);
    run_command_with_progress(&cmd, Some(duration_seconds), "VFR-fix", cancel_flag, progress_cb, child_pid)
}

pub fn compress_video_core(
    input_path: &str, output_path: &str, output_format: &str, codec: &str, crf_value: i32,
    preset_value: &str, duration_seconds: f64, video_info: &super::probe::VideoInfo,
    video_type: &VideoType, use_hardware: bool, cancel_flag: Arc<AtomicBool>,
    progress_cb: Option<Arc<dyn Fn(i32, String) + Send + Sync>>,
    child_pid: Option<PidTracker>,
    svtav1_lp: Option<usize>,
) -> RunResult {
    let gpu_info = get_gpu_info();
    let has_nvenc = gpu_info.contains("NVIDIA NVENC");
    let mut cmd = vec!["ffmpeg".to_string(), "-y".to_string()];
    if video_info.is_hevc && has_nvenc {
        cmd.extend(["-hwaccel".to_string(), "cuda".to_string()]);
    }
    cmd.extend(["-i".to_string(), input_path.to_string()]);
    let mut vf_filters = Vec::new();
    
    if video_info.is_10bit && codec != "libx265" && codec != "libsvtav1" {
        vf_filters.push("format=yuv420p".to_string());
    }
    if needs_x264_pad(codec, use_hardware) {
        vf_filters.push("pad=ceil(iw/2)*2:ceil(ih/2)*2".to_string());
    }
    if !vf_filters.is_empty() {
        cmd.extend(["-vf".to_string(), vf_filters.join(",")]);
    }
    match codec {
        "libvpx-vp9" => {
            if use_hardware && has_nvenc {
                cmd.extend(["-c:v".to_string(), "vp9_nvenc".to_string(), "-crf".to_string(), crf_value.to_string(), "-b:v".to_string(), "0".to_string()]);
            } else {
                cmd.extend(["-c:v".to_string(), "libvpx-vp9".to_string(), "-crf".to_string(), crf_value.to_string(), "-b:v".to_string(), "0".to_string(), "-deadline".to_string(), "good".to_string(), "-cpu-used".to_string(), "2".to_string()]);
            }
        }
        "libx265" => {
            if use_hardware && has_nvenc {
                cmd.extend(["-c:v".to_string(), "hevc_nvenc".to_string(), "-crf".to_string(), crf_value.to_string(), "-preset".to_string(), "p6".to_string(), "-tune".to_string(), "ll".to_string()]);
            } else {
                cmd.extend(["-c:v".to_string(), "libx265".to_string(), "-crf".to_string(), crf_value.to_string(), "-preset".to_string(), preset_value.to_string()]);
                cmd.extend(get_content_type_flags(video_type, codec, use_hardware, has_nvenc));
            }
        }
        "libsvtav1" => {
            if use_hardware {
                warn!("Hardware encoding is not available for AV1, using software SVT-AV1");
            }
            cmd.extend(svtav1_encode_args(crf_value, preset_value, video_type, video_info.grain_ydif, svtav1_lp));
            cmd.extend(svtav1_crf_metadata(crf_value, output_format));
        }
        _ => {
            if use_hardware && has_nvenc {
                cmd.extend(["-c:v".to_string(), "h264_nvenc".to_string(), "-cq".to_string(), crf_value.to_string(), "-preset".to_string(), "p6".to_string(), "-tune".to_string(), "ll".to_string(), "-spatial_aq".to_string(), "1".to_string(), "-temporal_aq".to_string(), "1".to_string(), "-rc-lookahead".to_string(), "20".to_string(), "-aq-strength".to_string(), "15".to_string()]);
            } else {
                cmd.extend(["-c:v".to_string(), "libx264".to_string(), "-crf".to_string(), crf_value.to_string(), "-preset".to_string(), preset_value.to_string()]);
                cmd.extend(get_content_type_flags(video_type, codec, use_hardware, has_nvenc));
            }
        }
    }
    cmd.extend(audio_args(codec));
    if video_info.has_subtitles {
        if output_format == "mp4" {
            cmd.extend(["-c:s".to_string(), "mov_text".to_string()]);
        } else {
            cmd.extend(["-c:s".to_string(), "copy".to_string()]);
        }
        cmd.extend(["-map".to_string(), "0:V".to_string(), "-map".to_string(), "0:a".to_string(), "-map".to_string(), "0:s".to_string()]);
    } else {
        cmd.extend(["-map".to_string(), "0:V".to_string(), "-map".to_string(), "0:a".to_string()]);
    }
    if output_format == "mp4" {
        cmd.extend(["-movflags".to_string(), "+faststart".to_string()]);
    }
    cmd.extend(["-progress".to_string(), "pipe:1".to_string(), output_path.to_string()]);
    run_command_with_progress(&cmd, Some(duration_seconds), "Compress", cancel_flag, progress_cb, child_pid)
}

pub fn compress_video_core_no_subtitles(
    input_path: &str, output_path: &str, output_format: &str, codec: &str, crf_value: i32,
    preset_value: &str, duration_seconds: f64, video_info: &super::probe::VideoInfo,
    video_type: &VideoType, use_hardware: bool, cancel_flag: Arc<AtomicBool>,
    progress_cb: Option<Arc<dyn Fn(i32, String) + Send + Sync>>,
    child_pid: Option<PidTracker>,
    svtav1_lp: Option<usize>,
) -> RunResult {
    let mut info_clone = video_info.clone();
    info_clone.has_subtitles = false;
    compress_video_core(input_path, output_path, output_format, codec, crf_value, preset_value, duration_seconds, &info_clone, video_type, use_hardware, cancel_flag, progress_cb, child_pid, svtav1_lp)
}

pub fn compress_video_core_full_map(
    input_path: &str, output_path: &str, output_format: &str, codec: &str, crf_value: i32,
    preset_value: &str, duration_seconds: f64, video_type: &VideoType, grain_ydif: Option<f64>,
    cancel_flag: Arc<AtomicBool>,
    progress_cb: Option<Arc<dyn Fn(i32, String) + Send + Sync>>,
    child_pid: Option<PidTracker>,
    svtav1_lp: Option<usize>,
) -> RunResult {
    let mut cmd = vec!["ffmpeg".to_string(), "-y".to_string(), "-i".to_string(), input_path.to_string()];
    match codec {
        "libsvtav1" => {
            cmd.extend(svtav1_encode_args(crf_value, preset_value, video_type, grain_ydif, svtav1_lp));
            cmd.extend(svtav1_crf_metadata(crf_value, output_format));
        }
        "libvpx-vp9" => cmd.extend([
            "-c:v".to_string(), "libvpx-vp9".to_string(), "-crf".to_string(), crf_value.to_string(),
            "-b:v".to_string(), "0".to_string(), "-deadline".to_string(), "good".to_string(), "-cpu-used".to_string(), "2".to_string(),
        ]),
        "libx265" => cmd.extend([
            "-c:v".to_string(), "libx265".to_string(), "-crf".to_string(), crf_value.to_string(),
            "-preset".to_string(), preset_value.to_string(),
        ]),
        _ => cmd.extend([
            "-c:v".to_string(), "libx264".to_string(), "-crf".to_string(), crf_value.to_string(),
            "-preset".to_string(), preset_value.to_string(),
        ]),
    }
    cmd.extend(audio_args(codec));
    cmd.extend(["-map".to_string(), "0".to_string(), "-map".to_string(), "-0:d".to_string(), "-progress".to_string(), "pipe:1".to_string(), output_path.to_string()]);
    run_command_with_progress(&cmd, Some(duration_seconds), "Compress (fallback)", cancel_flag, progress_cb, child_pid)
}

/// Опциональные параметры чанкового кодирования.
///
/// Сгруппированы в структуру, а не переданы позиционными аргументами: у позиционных
/// вариантов легко перепутать местами `None`-ы (их было четыре подряд), а любая
/// перестановка здесь молча меняет поведение кодирования.
pub struct ChunkEncodeOptions<'a> {
    /// Колбэк прогресса. `Some` включает `-progress pipe:1` и чтение stdout.
    pub progress_cb: Option<Arc<dyn Fn(i32, String) + Send + Sync>>,
    /// Длительность чанка для расчёта процента прогресса.
    pub duration_seconds: Option<f64>,
    /// Доп. параметры x264 (снижают накладные расходы при параллельном кодировании).
    pub x264_extra_params: Option<&'a str>,
    /// Число потоков на один чанк. `None` = решение ffmpeg по умолчанию (все ядра),
    /// что при параллельном кодировании даёт oversubscription по числу чанков.
    pub threads: Option<usize>,
}

impl<'a> Default for ChunkEncodeOptions<'a> {
    fn default() -> Self {
        Self { progress_cb: None, duration_seconds: None, x264_extra_params: None, threads: None }
    }
}

pub fn encode_chunk(
    input_path: &str, output_path: &str, start_time: f64, duration: f64,
    codec: &str, crf_value: i32, preset_value: &str, use_hardware: bool,
    video_info: &super::probe::VideoInfo, video_type: &VideoType, force_vfr_fix: bool,
    cancel_flag: Arc<AtomicBool>,
    child_pid: Option<PidTracker>,
    svtav1_lp: Option<usize>,
) -> RunResult {
    encode_chunk_with_progress(input_path, output_path, start_time, duration, codec, crf_value, preset_value, use_hardware, video_info, video_type, force_vfr_fix, cancel_flag, child_pid, svtav1_lp, ChunkEncodeOptions::default())
}

pub fn encode_chunk_with_progress(
    input_path: &str, output_path: &str, start_time: f64, duration: f64,
    codec: &str, crf_value: i32, preset_value: &str, use_hardware: bool,
    video_info: &super::probe::VideoInfo, video_type: &VideoType, force_vfr_fix: bool,
    cancel_flag: Arc<AtomicBool>,
    child_pid: Option<PidTracker>,
    svtav1_lp: Option<usize>,
    opts: ChunkEncodeOptions,
) -> RunResult {
    let gpu_info = get_gpu_info();
    let has_nvenc = gpu_info.contains("NVIDIA NVENC");
    
    let (fast_seek, trim_start) = chunk_timeline(start_time);

    let mut cmd = vec![
        "ffmpeg".to_string(), "-y".to_string(), 
        "-ss".to_string(), format!("{:.3}", fast_seek), 
        "-i".to_string(), input_path.to_string(),
        "-t".to_string(), format!("{:.3}", trim_start + duration),
    ];
    if let Some(threads) = opts.threads {
        cmd.extend(["-threads".to_string(), threads.to_string()]);
    }
    
    let needs_fix = force_vfr_fix || video_info.needs_vfr_fix;
    
    let mut vf_filters = vec![
        format!("trim=start={:.3}:duration={:.3}", trim_start, duration),
        "setpts=PTS-STARTPTS".to_string()
    ];
    
    if needs_fix {
        vf_filters.push(format!("fps={}", video_info.vfr_fix_fps));
    }
    if video_info.is_10bit && codec != "libx265" && codec != "libsvtav1" {
        vf_filters.push("format=yuv420p".to_string());
    }
    if needs_x264_pad(codec, use_hardware) {
        vf_filters.push("pad=ceil(iw/2)*2:ceil(ih/2)*2".to_string());
    }
    
    if !vf_filters.is_empty() {
        cmd.extend(["-vf".to_string(), vf_filters.join(",")]);
    }
    
    match codec {
        "libvpx-vp9" => {
            if use_hardware && has_nvenc {
                cmd.extend(["-c:v".to_string(), "vp9_nvenc".to_string(), "-crf".to_string(), crf_value.to_string(), "-b:v".to_string(), "0".to_string()]);
            } else {
                cmd.extend(["-c:v".to_string(), "libvpx-vp9".to_string(), "-crf".to_string(), crf_value.to_string(), "-b:v".to_string(), "0".to_string(), "-deadline".to_string(), "good".to_string(), "-cpu-used".to_string(), "2".to_string()]);
            }
        }
        "libx265" => {
            if use_hardware && has_nvenc {
                cmd.extend(["-c:v".to_string(), "hevc_nvenc".to_string(), "-crf".to_string(), crf_value.to_string(), "-preset".to_string(), "p6".to_string(), "-tune".to_string(), "ll".to_string()]);
            } else {
                cmd.extend(["-c:v".to_string(), "libx265".to_string(), "-crf".to_string(), crf_value.to_string(), "-preset".to_string(), preset_value.to_string()]);
                cmd.extend(get_content_type_flags(video_type, codec, use_hardware, has_nvenc));
            }
        }
        "libsvtav1" => {
            cmd.extend(svtav1_encode_args(crf_value, preset_value, video_type, video_info.grain_ydif, svtav1_lp));
        }
        _ => {
            if use_hardware && has_nvenc {
                cmd.extend(["-c:v".to_string(), "h264_nvenc".to_string(), "-cq".to_string(), crf_value.to_string(), "-preset".to_string(), "p6".to_string(), "-tune".to_string(), "ll".to_string()]);
            } else {
                cmd.extend(["-c:v".to_string(), "libx264".to_string(), "-crf".to_string(), crf_value.to_string(), "-preset".to_string(), preset_value.to_string()]);
                cmd.extend(get_content_type_flags(video_type, codec, use_hardware, has_nvenc));
                if let Some(extra) = opts.x264_extra_params {
                    cmd.extend(["-x264-params".to_string(), extra.to_string()]);
                }
            }
        }
    }
    
    cmd.extend(["-an".to_string(), "-sn".to_string()]);
    if opts.progress_cb.is_some() {
        cmd.extend(["-progress".to_string(), "pipe:1".to_string()]);
    }
    cmd.push(output_path.to_string());
    if let Some(cb) = opts.progress_cb {
        run_command_with_progress(&cmd, opts.duration_seconds, "Chunk encode", cancel_flag, Some(cb), child_pid)
    } else {
        run_command_simple(&cmd, cancel_flag, child_pid)
    }
}

pub fn calculate_vmaf(
    original_path: &str, chunk_path: &str, start_time: f64, duration: f64,
    n_subsample: usize, width: usize, video_info: &super::probe::VideoInfo,
    force_vfr_fix: bool, pad_applied: bool, ignore_noise: bool, cancel_flag: Arc<AtomicBool>,
    child_pid: Option<PidTracker>,
) -> f64 {
    let tmp_dir = std::env::temp_dir();
    let json_filename = format!("vmaf_{}_{}.json", std::process::id(), chrono::Utc::now().timestamp_millis());
    let json_path = tmp_dir.join(&json_filename);
    let json_path_ff = json_path.to_string_lossy().replace('\\', "/").replace(':', "\\:");

    let (fast_seek, trim_start) = chunk_timeline(start_time);

    let needs_fix = force_vfr_fix || video_info.needs_vfr_fix;

    let mut ref_filters = format!("setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709,trim=start={:.3}:duration={:.3},setpts=PTS-STARTPTS", trim_start, duration);
    if needs_fix {
        ref_filters.push_str(&format!(",fps={}", video_info.vfr_fix_fps));
    }
    
    if pad_applied {
        ref_filters.push_str(",pad=ceil(iw/2)*2:ceil(ih/2)*2");
    }

    if ignore_noise {
        // Усиленный фильтр для игнора 3D CGI шума в VMAF
        ref_filters.push_str(",hqdn3d=12:9:14:12,gblur=sigma=0.6");
    }

    let scale_filter = if width > 1920 { ",scale=1920:-1:flags=bicubic" } else { "" };
    ref_filters.push_str(scale_filter);

    let mut dist_filters = format!("setpts=PTS-STARTPTS");
    if ignore_noise {
        dist_filters.push_str(",hqdn3d=12:9:14:12,gblur=sigma=0.6");
    }
    dist_filters.push_str(scale_filter);

    let filter_complex = format!(
        "[0:v]{}[ref];[1:v]{}[dist];[dist][ref]libvmaf=model=version=vmaf_v0.6.1neg:log_fmt=json:log_path='{}':n_subsample={}",
        ref_filters, dist_filters, json_path_ff, n_subsample
    );

    // `-t` on the input limits the decode window to the chunk (trim_start +
    // duration) instead of decoding the whole tail of the file from the seek
    // point — without it a 4K file decodes from `-ss` all the way to the end,
    // which took ~6 minutes per VMAF check. `-threads 4` keeps the ~5 parallel
    // VMAF processes from oversubscribing the CPU.
    let cmd = vec![
        "ffmpeg".to_string(), "-y".to_string(),
        "-threads".to_string(), "4".to_string(),
        "-ss".to_string(), format!("{:.3}", fast_seek),
        "-t".to_string(), format!("{:.3}", trim_start + duration),
        "-i".to_string(), original_path.to_string(),
        "-i".to_string(), chunk_path.to_string(),
        "-filter_complex".to_string(), filter_complex,
        "-f".to_string(), "null".to_string(),
        "-".to_string(),
    ];

    let result = run_command_simple(&cmd, cancel_flag, child_pid);
    let mut score = -1.0;

    if json_path.exists() {
        if let Ok(content) = std::fs::read_to_string(&json_path) {
            if let Ok(data) = serde_json::from_str::<serde_json::Value>(&content) {
                if let Some(pooled) = data.get("pooled_metrics") {
                    if let Some(vmaf) = pooled.get("vmaf")
                        .and_then(|v| v.get("mean"))
                        .and_then(|v| v.as_f64())
                    {
                        score = vmaf;
                    }
                    if let Some(obj) = pooled.as_object() {
                        let features: Vec<String> = obj.iter()
                            .filter(|(k, _)| *k != "vmaf")
                            .map(|(k, v)| {
                                let mean = v.get("mean")
                                    .and_then(|v| v.as_f64())
                                    .map(|v| format!("{:.4}", v))
                                    .unwrap_or_else(|| "N/A".to_string());
                                format!("{}={}", k, mean)
                            })
                            .collect();
                        info!("VMAF features: vmaf={:.2} | {}", score, features.join(" | "));
                    }
                }
            }
        }
        if let Err(e) = std::fs::remove_file(&json_path) {
            warn!("Failed to remove VMAF json {:?}: {}", json_path, e);
        }
    }

    if score == -1.0 && !result.success {
        if result.message.contains("No such filter: 'libvmaf'") {
            return -2.0;
        }
    }
    score
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn chunk_timeline_at_zero() {
        let (fast_seek, trim_start) = chunk_timeline(0.0);
        assert_eq!(fast_seek, 0.0);
        assert_eq!(trim_start, 0.0);
    }

    #[test]
    fn chunk_timeline_below_10_seconds() {
        let (fast_seek, trim_start) = chunk_timeline(5.0);
        assert_eq!(fast_seek, 0.0);
        assert_eq!(trim_start, 5.0);
    }

    #[test]
    fn chunk_timeline_exactly_10_seconds() {
        let (fast_seek, trim_start) = chunk_timeline(10.0);
        assert_eq!(fast_seek, 0.0);
        assert_eq!(trim_start, 10.0);
    }

    #[test]
    fn chunk_timeline_normal_case() {
        let (fast_seek, trim_start) = chunk_timeline(100.0);
        assert_eq!(fast_seek, 90.0);
        assert_eq!(trim_start, 10.0);
    }

    #[test]
    fn chunk_timeline_large_value() {
        let (fast_seek, trim_start) = chunk_timeline(1000.0);
        assert_eq!(fast_seek, 990.0);
        assert_eq!(trim_start, 10.0);
    }

    #[test]
    fn chunk_timeline_sum_equals_source_start() {
        for source_start in [0.0, 5.0, 10.0, 25.0, 100.0, 500.0, 2121.0] {
            let (fast_seek, trim_start) = chunk_timeline(source_start);
            assert_eq!(fast_seek + trim_start, source_start,
                "fast_seek({}) + trim_start({}) should equal source_start({})", fast_seek, trim_start, source_start);
        }
    }

    #[test]
    fn chunk_timeline_negative_not_possible() {
        for source_start in [0.0, 0.001, 5.0] {
            let (fast_seek, trim_start) = chunk_timeline(source_start);
            assert!(fast_seek >= 0.0, "fast_seek should be >= 0, got {}", fast_seek);
            assert!(trim_start >= 0.0, "trim_start should be >= 0, got {}", trim_start);
        }
    }

    #[test]
    fn chunk_timeline_trim_start_max_10() {
        for source_start in [10.0, 100.0, 500.0, 2121.0] {
            let (_, trim_start) = chunk_timeline(source_start);
            assert!(trim_start <= 10.01, "trim_start should be <= 10, got {} for source_start={}", trim_start, source_start);
        }
    }

    #[test]
    fn chunk_timeline_first_chunk_no_seek() {
        let (fast_seek, trim_start) = chunk_timeline(0.0);
        assert_eq!(fast_seek, 0.0);
        assert_eq!(trim_start, 0.0);
    }
}