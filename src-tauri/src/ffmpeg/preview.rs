use std::collections::HashMap;
use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};

use log::{error, info, warn};
use serde::{Deserialize, Serialize};
use tauri::Emitter;

use super::core::{parse_progress_line, run_ffprobe_json};
use crate::process_control::PidTracker;
use crate::settings::get_actual_ffmpeg_path;

const PREVIEW_ROOT: &str = "videofile_pro_previews";
const CACHE_MAX_AGE_DAYS: u64 = 7;
const HLS_SEGMENT_SECONDS: u64 = 2;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum PreviewMode {
    Direct,
    Remux,
    Hls,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PreviewInfo {
    pub mode: PreviewMode,
    pub path: String,
    pub hls: bool,
    pub converting: bool,
    pub job_id: String,
}

pub struct PreviewJob {
    pub cancel: Arc<AtomicBool>,
    pub pid: PidTracker,
}

pub struct PreviewJobsState {
    pub jobs: Mutex<HashMap<String, Arc<PreviewJob>>>,
}

impl Default for PreviewJobsState {
    fn default() -> Self {
        Self {
            jobs: Mutex::new(HashMap::new()),
        }
    }
}

#[derive(Deserialize, Default)]
struct ProbeOutput {
    #[serde(default)]
    format: ProbeFormat,
    #[serde(default)]
    streams: Vec<ProbeStream>,
}

#[derive(Deserialize, Default)]
struct ProbeFormat {
    #[serde(default)]
    duration: String,
    #[serde(default)]
    format_name: String,
}

#[derive(Deserialize, Default)]
struct ProbeStream {
    #[serde(default)]
    codec_type: String,
    #[serde(default)]
    codec_name: String,
}

struct MediaProbe {
    container: String,
    codec: String,
    duration: f64,
}

pub fn preview_root() -> PathBuf {
    std::env::temp_dir().join(PREVIEW_ROOT)
}

fn fnv1a(data: &[u8]) -> u64 {
    let mut hash: u64 = 0xcbf2_9ce4_8422_2325;
    for b in data {
        hash ^= *b as u64;
        hash = hash.wrapping_mul(0x0000_0100_0000_01b3);
    }
    hash
}

fn preview_key(path: &str) -> String {
    let mut seed = Vec::with_capacity(path.len() + 32);
    seed.extend_from_slice(path.as_bytes());
    let meta = std::fs::metadata(path)
        .map(|m| (m.len(), m.modified().ok().map(|t| t.duration_since(std::time::UNIX_EPOCH).map(|d| d.as_nanos()).unwrap_or(0))))
        .unwrap_or((0, None));
    seed.extend_from_slice(&meta.0.to_le_bytes());
    if let Some(modified) = meta.1 {
        seed.extend_from_slice(&modified.to_le_bytes());
    }
    format!("{:016x}", fnv1a(&seed))
}

fn probe_media(path: &str) -> Result<MediaProbe, String> {
    if !Path::new(path).exists() {
        log::error!("Preview: file not found: {}", path);
        return Err(format!("File not found: {}", path));
    }
    let cmd = vec![
        "ffprobe".to_string(),
        "-v".to_string(),
        "quiet".to_string(),
        "-print_format".to_string(),
        "json".to_string(),
        "-show_format".to_string(),
        "-show_streams".to_string(),
        path.to_string(),
    ];
    let output = run_ffprobe_json(&cmd).map_err(|e| {
        log::error!("Preview probe failed for {}: {}", path, e);
        e
    })?;
    let data: ProbeOutput = serde_json::from_str(&output).map_err(|e| {
        log::error!("Preview probe parse failed for {}: {}", path, e);
        format!("Failed to parse ffprobe output: {}", e)
    })?;

    let container = data.format.format_name.to_lowercase();
    let codec = data
        .streams
        .iter()
        .find(|s| s.codec_type == "video")
        .map(|s| s.codec_name.to_lowercase())
        .unwrap_or_default();
    let duration = data.format.duration.parse::<f64>().unwrap_or(0.0);

    if container.is_empty() && codec.is_empty() {
        log::error!("Preview: no media streams found in {}", path);
        return Err("No media streams found".to_string());
    }
    Ok(MediaProbe { container, codec, duration })
}

fn is_mp4ish(container: &str) -> bool {
    container.contains("mp4")
        || container.contains("mov")
        || container.contains("m4v")
        || container.contains("3gp")
        || container.contains("quicktime")
}

fn is_webm(container: &str) -> bool {
    container.contains("webm")
}

fn container_playable(container: &str) -> bool {
    is_mp4ish(container) || is_webm(container)
}

fn browser_ok_codec(codec: &str) -> bool {
    matches!(codec, "h264" | "vp8" | "vp9" | "av1")
}

fn has_endlist(playlist: &Path) -> bool {
    match std::fs::read_to_string(playlist) {
        Ok(content) => content.contains("#EXT-X-ENDLIST"),
        Err(_) => false,
    }
}

fn run_remux(input: &str, output: &Path) -> Result<(), String> {
    if output.exists() {
        return Ok(());
    }
    let parent = output.parent().ok_or_else(|| "Invalid output path".to_string())?;
    std::fs::create_dir_all(parent).map_err(|e| {
        log::error!("Failed to create preview dir {}: {}", parent.display(), e);
        format!("Failed to create preview dir: {}", e)
    })?;
    let cmd = vec![
        "ffmpeg".to_string(),
        "-y".to_string(),
        "-i".to_string(),
        input.to_string(),
        "-map".to_string(),
        "0:v:0".to_string(),
        "-map".to_string(),
        "0:a:0?".to_string(),
        "-c".to_string(),
        "copy".to_string(),
        "-sn".to_string(),
        "-movflags".to_string(),
        "+faststart".to_string(),
        output.to_string_lossy().to_string(),
    ];
    let result = super::core::run_command_simple(&cmd, Arc::new(AtomicBool::new(false)), None);
    if result.success {
        info!("Preview remux done: {}", output.display());
        Ok(())
    } else {
        error!("Preview remux failed for {}: {}", input, result.message);
        Err(format!("Remux failed: {}", result.message))
    }
}

pub fn cancel_job(jobs: &PreviewJobsState, job_id: &str) {
    let job = match jobs.jobs.lock() {
        Ok(mut map) => map.remove(job_id),
        Err(e) => {
            warn!("Failed to lock preview jobs: {}", e);
            return;
        }
    };
    if let Some(job) = job {
        job.cancel.store(true, Ordering::Relaxed);
        info!("Preview job {} cancelled", job_id);
    }
}

fn spawn_hls_job(input: &str, dir: &Path, duration: f64, job: Arc<PreviewJob>, app: tauri::AppHandle, job_id: String) {
    let input = input.to_string();
    let dir = dir.to_path_buf();
    let ffmpeg_path = get_actual_ffmpeg_path();

    std::thread::spawn(move || {
        let segment_pattern = dir.join("seg_%05d.ts");
        let playlist = dir.join("index.m3u8");
        let mut command = Command::new(&ffmpeg_path);
        command.args([
            "-y",
            "-i",
            &input,
            "-map",
            "0:v:0",
            "-map",
            "0:a:0?",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            "-profile:v",
            "main",
            "-force_key_frames",
            &format!("expr:gte(t,n_forced*{})", HLS_SEGMENT_SECONDS),
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-ac",
            "2",
            "-sn",
            "-f",
            "hls",
            "-hls_time",
            &HLS_SEGMENT_SECONDS.to_string(),
            "-hls_playlist_type",
            "event",
            "-hls_flags",
            "independent_segments",
            "-hls_segment_filename",
            &segment_pattern.to_string_lossy(),
            "-progress",
            "pipe:1",
            "-nostats",
            &playlist.to_string_lossy(),
        ]);
        command.stdout(Stdio::piped()).stderr(Stdio::piped());

        #[cfg(target_os = "windows")]
        {
            use std::os::windows::process::CommandExt;
            command.creation_flags(0x08000000);
        }

        let mut child = match command.spawn() {
            Ok(c) => c,
            Err(e) => {
                error!("Preview HLS job {} failed to start: {}", job_id, e);
                let _ = app.emit("preview-error", (job_id, format!("Failed to start ffmpeg: {}", e)));
                return;
            }
        };
        job.pid.store(child.id());
        info!("Preview HLS job {} started, pid {}", job_id, child.id());

        let stdout = match child.stdout.take() {
            Some(s) => s,
            None => {
                error!("Preview HLS job {}: failed to capture stdout", job_id);
                job.pid.store(0);
                let _ = app.emit("preview-error", (job_id, "Failed to capture ffmpeg output".to_string()));
                return;
            }
        };
        let stderr_tail = Arc::new(Mutex::new(Vec::<String>::new()));
        let tail = stderr_tail.clone();
        let stderr_handle = child.stderr.take().map(|stderr| {
            std::thread::spawn(move || {
                let reader = BufReader::new(stderr);
                for line in reader.lines().flatten() {
                    let mut guard = match tail.lock() {
                        Ok(g) => g,
                        Err(_) => return,
                    };
                    guard.push(line.trim().to_string());
                    if guard.len() > 15 {
                        guard.remove(0);
                    }
                }
            })
        });

        let reader = BufReader::new(stdout);
        let mut cancelled = false;
        for line in reader.lines().flatten() {
            if job.cancel.load(Ordering::Relaxed) {
                cancelled = true;
                break;
            }
            let percent = parse_progress_line(&line, duration);
            if percent != -1 {
                let _ = app.emit("preview-progress", (job_id.clone(), percent));
            }
        }

        job.pid.store(0);
        let status = child.wait();
        if let Some(handle) = stderr_handle {
            let _ = handle.join();
        }

        if cancelled {
            let _ = child.kill();
            info!("Preview HLS job {} cancelled", job_id);
            return;
        }

        match status {
            Ok(code) if code.success() => {
                info!("Preview HLS job {} finished", job_id);
                let _ = app.emit("preview-ready", job_id.clone());
            }
            Ok(code) => {
                let tail = stderr_tail.lock().map(|g| g.join("\n")).unwrap_or_default();
                let msg = format!("FFmpeg HLS failed (code {:?}): {}", code.code().unwrap_or(-1), tail);
                error!("Preview HLS job {}: {}", job_id, msg);
                let _ = app.emit("preview-error", (job_id, msg));
            }
            Err(e) => {
                let msg = format!("Failed to wait for ffmpeg: {}", e);
                error!("Preview HLS job {}: {}", job_id, msg);
                let _ = app.emit("preview-error", (job_id, msg));
            }
        }
    });
}

pub fn prepare_preview(
    path: &str,
    app: &tauri::AppHandle,
    jobs: &Arc<PreviewJobsState>,
    force_transcode: bool,
) -> Result<PreviewInfo, String> {
    let probe = probe_media(path)?;
    let key = preview_key(path);
    let dir = preview_root().join(&key);

    if !force_transcode {
        if container_playable(&probe.container) {
            info!("Preview direct for {} (container={}, codec={})", path, probe.container, probe.codec);
            return Ok(PreviewInfo {
                mode: PreviewMode::Direct,
                path: path.to_string(),
                hls: false,
                converting: false,
                job_id: String::new(),
            });
        }
        if browser_ok_codec(&probe.codec) {
            info!("Preview remux for {} (container={}, codec={})", path, probe.container, probe.codec);
            let mp4 = dir.join("preview.mp4");
            run_remux(path, &mp4)?;
            return Ok(PreviewInfo {
                mode: PreviewMode::Remux,
                path: mp4.to_string_lossy().to_string(),
                hls: false,
                converting: false,
                job_id: String::new(),
            });
        }
    }

    let playlist = dir.join("index.m3u8");
    if has_endlist(&playlist) {
        info!("Preview HLS cache hit for {}", path);
        return Ok(PreviewInfo {
            mode: PreviewMode::Hls,
            path: playlist.to_string_lossy().to_string(),
            hls: true,
            converting: false,
            job_id: String::new(),
        });
    }

    info!("Preview HLS transcode for {} (container={}, codec={})", path, probe.container, probe.codec);

    if dir.exists() {
        if let Err(e) = std::fs::remove_dir_all(&dir) {
            warn!("Preview: failed to remove stale dir {}: {}", dir.display(), e);
        }
    }
    if let Err(e) = std::fs::create_dir_all(&dir) {
        log::error!("Preview: failed to create dir {}: {}", dir.display(), e);
        return Err(format!("Failed to create preview dir: {}", e));
    }

    let job = Arc::new(PreviewJob {
        cancel: Arc::new(AtomicBool::new(false)),
        pid: PidTracker::default(),
    });
    let job_id = uuid::Uuid::new_v4().to_string();
    {
        let mut map = jobs.jobs.lock().map_err(|e| {
            let msg = format!("Failed to lock preview jobs: {}", e);
            error!("{}", msg);
            msg
        })?;
        map.insert(job_id.clone(), job.clone());
    }

    spawn_hls_job(path, &dir, probe.duration, job, app.clone(), job_id.clone());
    info!("Preview HLS job started for {} ({} mode)", path, probe.container);

    Ok(PreviewInfo {
        mode: PreviewMode::Hls,
        path: playlist.to_string_lossy().to_string(),
        hls: true,
        converting: true,
        job_id,
    })
}

pub fn cleanup_old_previews() {
    let root = preview_root();
    let entries = match std::fs::read_dir(&root) {
        Ok(e) => e,
        Err(_) => return,
    };
    let now = std::time::SystemTime::now();
    let max_age = std::time::Duration::from_secs(CACHE_MAX_AGE_DAYS * 24 * 3600);
    let mut removed = 0usize;
    for entry in entries.flatten() {
        let path = entry.path();
        if !path.is_dir() {
            continue;
        }
        let stale = entry
            .metadata()
            .and_then(|m| m.modified())
            .map(|modified| now.duration_since(modified).map(|age| age > max_age).unwrap_or(false))
            .unwrap_or(false);
        if stale {
            match std::fs::remove_dir_all(&path) {
                Ok(_) => removed += 1,
                Err(e) => warn!("Preview cleanup: failed to remove {}: {}", path.display(), e),
            }
        }
    }
    if removed > 0 {
        info!("Preview cleanup: removed {} stale preview dirs", removed);
    }
}
