use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::sync::atomic::AtomicBool;
use log::{error, warn};

use crate::ffmpeg::core::{run_command_with_progress, RunResult};
use crate::process_control::PidTracker;

const PREVIEW_SEGMENTS: usize = 5;
const PREVIEW_SEGMENT_DURATION: f64 = 3.0;
const PREVIEW_FPS: i32 = 10;
const PREVIEW_SCALE: &str = "320:-2";

struct SimpleRng(u64);

impl SimpleRng {
    fn next(&mut self) -> u64 {
        let mut x = self.0;
        x ^= x << 13;
        x ^= x >> 7;
        x ^= x << 17;
        self.0 = x;
        x
    }

    fn range(&mut self, min: f64, max: f64) -> f64 {
        if max <= min {
            return min;
        }
        let r = self.next() as f64 / u64::MAX as f64;
        min + r * (max - min)
    }
}

fn fnv1a(s: &str) -> u64 {
    let mut h: u64 = 0xcbf29ce484222325;
    for b in s.as_bytes() {
        h ^= *b as u64;
        h = h.wrapping_mul(0x100000001b3);
    }
    h
}

fn timestamp_seed() -> u64 {
    match std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH) {
        Ok(d) => d.as_nanos() as u64,
        Err(e) => {
            warn!("System clock before UNIX epoch, using fallback seed: {}", e);
            0
        }
    }
}

fn previews_dir() -> Result<PathBuf, String> {
    let exe_dir = std::env::current_exe()
        .map_err(|e| format!("Failed to resolve executable path: {}", e))?
        .parent()
        .ok_or_else(|| "Executable has no parent directory".to_string())?
        .to_path_buf();
    let dir = exe_dir.join("previews");
    std::fs::create_dir_all(&dir).map_err(|e| format!("Failed to create previews dir: {}", e))?;
    Ok(dir)
}

fn cleanup_previews(dir: &Path) -> Result<(), String> {
    let entries = std::fs::read_dir(dir).map_err(|e| format!("Failed to read previews dir: {}", e))?;
    for entry in entries {
        let entry = match entry {
            Ok(e) => e,
            Err(e) => {
                warn!("Failed to read preview entry: {}", e);
                continue;
            }
        };
        let path = entry.path();
        let is_gif = path.extension().and_then(|e| e.to_str()) == Some("gif");
        if is_gif {
            if let Err(e) = std::fs::remove_file(&path) {
                warn!("Failed to remove stale preview {}: {}", path.display(), e);
            }
        }
    }
    Ok(())
}

fn pick_segment_starts(duration: f64, seed: u64, count: usize) -> (Vec<f64>, f64) {
    let band_start = duration * 0.2;
    let band_end = duration * 0.8;
    let mut seg_dur = PREVIEW_SEGMENT_DURATION;
    let band_len = band_end - band_start;
    if band_len < count as f64 * seg_dur {
        seg_dur = (band_len / count as f64).max(0.1);
    }
    let max_start = band_end - seg_dur;
    let mut rng = SimpleRng(seed);
    let mut starts = Vec::with_capacity(count);
    for _ in 0..count {
        starts.push(rng.range(band_start, max_start));
    }
    (starts, seg_dur)
}

fn build_gif_command(input_path: &str, output_path: &str, starts: &[f64], seg_dur: f64) -> Vec<String> {
    let mut cmd = vec!["ffmpeg".to_string(), "-y".to_string()];
    for &s in starts {
        cmd.extend([
            "-ss".to_string(),
            format!("{:.3}", s),
            "-t".to_string(),
            format!("{:.3}", seg_dur),
            "-i".to_string(),
            input_path.to_string(),
        ]);
    }
    let n = starts.len();
    let mut filters: Vec<String> = (0..n)
        .map(|i| format!("[{}:v]setpts=PTS-STARTPTS,scale={}[v{}]", i, PREVIEW_SCALE, i))
        .collect();
    let mut concat_in = String::new();
    for i in 0..n {
        concat_in.push_str(&format!("[v{}]", i));
    }
    filters.push(format!(
        "{}concat=n={}:v=1:a=0,fps={}[cc]",
        concat_in, n, PREVIEW_FPS
    ));
    filters.push("[cc]split[x][y];[y]palettegen[pg];[x][pg]paletteuse[out]".to_string());
    cmd.extend([
        "-filter_complex".to_string(),
        filters.join(";"),
        "-map".to_string(),
        "[out]".to_string(),
        "-an".to_string(),
        output_path.to_string(),
    ]);
    cmd
}

pub fn generate_preview_gif(
    input_path: &str,
    cancel_flag: Arc<AtomicBool>,
    progress_cb: Option<Arc<dyn Fn(i32, String) + Send + Sync>>,
    child_pid: Option<PidTracker>,
) -> Result<String, String> {
    let video_info = crate::video_processor::compress::get_video_info_basic(input_path)
        .map_err(|e| {
            error!("Failed to get video info for preview {}: {}", input_path, e);
            e
        })?;
    let duration = video_info.duration;
    if duration <= 0.0 || video_info.width == 0 {
        let msg = "Could not determine video duration or dimensions".to_string();
        error!("{} for {}", msg, input_path);
        return Err(msg);
    }

    let input_p = Path::new(input_path);
    let stem = input_p
        .file_stem()
        .map(|s| s.to_string_lossy().to_string())
        .unwrap_or_else(|| input_path.to_string());
    let hash = fnv1a(input_path);
    let filename = format!("{}_{:016x}_preview.gif", stem, hash);

    let dir = previews_dir()?;
    cleanup_previews(&dir)?;
    let output_path = dir.join(filename);
    let output_str = output_path.to_string_lossy().to_string();

    let seed = hash ^ timestamp_seed();
    let (starts, seg_dur) = pick_segment_starts(duration, seed, PREVIEW_SEGMENTS);
    let cmd = build_gif_command(input_path, &output_str, &starts, seg_dur);
    let total_duration = starts.len() as f64 * seg_dur;

    let result: RunResult = run_command_with_progress(
        &cmd, Some(total_duration), "Preview", cancel_flag, progress_cb, child_pid,
    );
    if !result.success {
        error!("Preview generation error for {}: {}", input_path, result.message);
        return Err(format!("Preview generation error: {}", result.message));
    }
    if !output_path.exists() {
        let msg = "Preview generation produced no output".to_string();
        error!("{} for {}", msg, input_path);
        return Err(msg);
    }
    Ok(output_str)
}