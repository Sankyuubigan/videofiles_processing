use std::io::{BufRead, BufReader};
use std::process::{Command, Stdio};
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};

use crate::process_control::PidTracker;
use crate::settings::{get_actual_ffmpeg_path, get_ffprobe_path};

pub fn parse_progress_line(line: &str, duration_seconds: f64) -> i32 {
    if duration_seconds <= 0.0 {
        return -1;
    }
    let line = line.trim();
    if let Some(rest) = line.strip_prefix("out_time_us=") {
        if rest == "N/A" {
            return -1;
        }
        if let Ok(microseconds) = rest.parse::<i64>() {
            let processed_seconds = microseconds as f64 / 1_000_000.0;
            let percent = ((processed_seconds / duration_seconds) * 100.0) as i32;
            return percent.clamp(0, 100);
        }
        return -1;
    }
    if line.starts_with("progress=end") {
        return 100;
    }
    -1
}

pub struct RunResult {
    pub success: bool,
    pub message: String,
}

fn spawn_stderr_drainer(stderr: std::process::ChildStderr) -> std::thread::JoinHandle<Vec<String>> {
    std::thread::spawn(move || {
        let reader = BufReader::new(stderr);
        let mut error_lines = Vec::new();
        for line_result in reader.lines() {
            if let Ok(line) = line_result {
                let lower = line.to_lowercase();
                if ["error", "failed", "invalid", "cannot", "unable"].iter().any(|k| lower.contains(k)) {
                    error_lines.push(line.trim().to_string());
                }
            }
        }
        error_lines
    })
}

pub fn run_command_with_progress(
    cmd: &[String],
    duration_seconds: Option<f64>,
    stage_name: &str,
    cancel_flag: Arc<AtomicBool>,
    progress_cb: Option<Arc<dyn Fn(i32, String) + Send + Sync>>,
    child_pid: Option<PidTracker>,
) -> RunResult {
    log::debug!("Executing FFmpeg command: {}", cmd.join(" "));
    let ffmpeg_path = get_actual_ffmpeg_path();

    let mut command = Command::new(&ffmpeg_path);
    command.args(cmd.iter().skip(1));
    command.stdout(Stdio::piped()).stderr(Stdio::piped());

    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000);
    }

    let mut child = match command.spawn() {
        Ok(c) => c,
        Err(e) => {
            log::error!("Failed to start FFmpeg: {}", e);
            return RunResult { success: false, message: format!("Failed to start FFmpeg: {}", e) };
        }
    };

    if let Some(ref pid_ref) = child_pid {
        pid_ref.store(child.id());
    }

    let stdout = match child.stdout.take() {
        Some(s) => s,
        None => {
            log::error!("Failed to capture FFmpeg stdout in run_command_with_progress");
            if let Some(ref pid_ref) = child_pid {
                pid_ref.store(0);
            }
            return RunResult { success: false, message: "Failed to capture FFmpeg stdout".to_string() };
        }
    };

    let stderr_handle = child.stderr.take().map(spawn_stderr_drainer);

    let reader = BufReader::new(stdout);

    let mut output_log = Vec::new();
    let mut error_lines = Vec::new();

    for line_result in reader.lines() {
        if cancel_flag.load(Ordering::Relaxed) {
            let _ = child.kill();
            log::warn!("FFmpeg operation cancelled");
            if let Some(ref pid_ref) = child_pid {
                pid_ref.store(0);
            }
            return RunResult { success: false, message: "Operation cancelled".to_string() };
        }

        if let Ok(line) = line_result {
            output_log.push(line.clone());
            let lower = line.to_lowercase();
            if ["error", "failed", "invalid", "cannot", "unable"].iter().any(|k| lower.contains(k)) {
                error_lines.push(line.trim().to_string());
            }
            if let (Some(cb), Some(dur)) = (&progress_cb, duration_seconds) {
                let percent = parse_progress_line(&line, dur);
                if percent != -1 {
                    cb(percent, format!("{}: {}%", stage_name, percent));
                }
            }
        }
    }

    if let Some(handle) = stderr_handle {
        if let Ok(mut stderr_errors) = handle.join() {
            error_lines.append(&mut stderr_errors);
        }
    }

    let wait_result = child.wait();
    if let Some(ref pid_ref) = child_pid {
        pid_ref.store(0);
    }
    match wait_result {
        Ok(return_code) => {
            let full_output = output_log.join("");
            if !return_code.success() {
                let error_summary: Vec<String> = full_output.lines().rev().take(15).map(|s| s.to_string()).collect();
                let error_detail: Vec<String> = error_lines.into_iter().rev().take(10).collect();
                let msg = format!(
                    "FFmpeg error (code {:?}).\nLog:\n{}\n\nDetails:\n{}",
                    return_code.code().unwrap_or(-1),
                    error_summary.iter().rev().cloned().collect::<Vec<_>>().join("\n"),
                    error_detail.join("\n")
                );
                log::error!("{}: {}", stage_name, msg);
                RunResult { success: false, message: msg }
            } else {
                RunResult { success: true, message: "FFmpeg command completed successfully".to_string() }
            }
        }
        Err(e) => {
            log::error!("Failed to wait for FFmpeg: {}", e);
            RunResult { success: false, message: format!("Failed to wait for FFmpeg: {}", e) }
        }
    }
}

pub fn run_command_simple(
    cmd: &[String],
    cancel_flag: Arc<AtomicBool>,
    child_pid: Option<PidTracker>,
) -> RunResult {
    log::debug!("Executing FFmpeg command (simple): {}", cmd.join(" "));
    let ffmpeg_path = get_actual_ffmpeg_path();

    let mut command = Command::new(&ffmpeg_path);
    command.args(cmd.iter().skip(1));
    command.stdout(Stdio::piped()).stderr(Stdio::piped());

    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000);
    }

    let mut child = match command.spawn() {
        Ok(c) => c,
        Err(e) => {
            log::error!("Failed to start FFmpeg (simple): {}", e);
            return RunResult { success: false, message: format!("Failed to start FFmpeg (simple): {}", e) };
        }
    };

    if let Some(ref pid_ref) = child_pid {
        pid_ref.store(child.id());
    }

    let stdout_handle = child.stdout.take().map(|stdout| {
        std::thread::spawn(move || {
            let reader = BufReader::new(stdout);
            let mut output_log = Vec::new();
            let mut error_lines = Vec::new();
            for line_result in reader.lines() {
                if let Ok(line) = line_result {
                    output_log.push(line.clone());
                    let lower = line.to_lowercase();
                    if ["error", "failed", "invalid", "cannot", "unable"].iter().any(|k| lower.contains(k)) {
                        error_lines.push(line.trim().to_string());
                    }
                }
            }
            (output_log, error_lines)
        })
    });

    let stderr_handle = child.stderr.take().map(spawn_stderr_drainer);

    let mut cancelled = false;
    let mut wait_error: Option<String> = None;
    loop {
        if cancel_flag.load(Ordering::Relaxed) {
            let _ = child.kill();
            log::warn!("FFmpeg operation cancelled (simple)");
            cancelled = true;
            break;
        }
        match child.try_wait() {
            Ok(Some(_)) => break,
            Ok(None) => std::thread::sleep(std::time::Duration::from_millis(200)),
            Err(e) => {
                log::error!("Failed to wait for FFmpeg (simple): {}", e);
                wait_error = Some(format!("Failed to wait for FFmpeg: {}", e));
                break;
            }
        }
    }

    if let Some(ref pid_ref) = child_pid {
        pid_ref.store(0);
    }

    let (output_log, mut error_lines) = stdout_handle
        .map(|handle| handle.join().unwrap_or_default())
        .unwrap_or_default();

    if let Some(handle) = stderr_handle {
        if let Ok(mut stderr_errors) = handle.join() {
            error_lines.append(&mut stderr_errors);
        }
    }

    if cancelled {
        return RunResult { success: false, message: "Operation cancelled".to_string() };
    }
    if let Some(msg) = wait_error {
        return RunResult { success: false, message: msg };
    }

    match child.wait() {
        Ok(return_code) => {
            let full_output = output_log.join("");
            if !return_code.success() {
                let error_summary: Vec<String> = full_output.lines().rev().take(15).map(|s| s.to_string()).collect();
                let error_detail: Vec<String> = error_lines.into_iter().rev().take(10).collect();
                let msg = format!(
                    "FFmpeg error (code {:?}).\nLog:\n{}\n\nDetails:\n{}",
                    return_code.code().unwrap_or(-1),
                    error_summary.iter().rev().cloned().collect::<Vec<_>>().join("\n"),
                    error_detail.join("\n")
                );
                log::error!("FFmpeg simple command: {}", msg);
                RunResult { success: false, message: msg }
            } else {
                RunResult { success: true, message: "FFmpeg command completed successfully".to_string() }
            }
        }
        Err(e) => {
            log::error!("Failed to wait for FFmpeg: {}", e);
            RunResult { success: false, message: format!("Failed to wait for FFmpeg: {}", e) }
        }
    }
}

pub fn run_ffprobe_json(cmd: &[String]) -> Result<String, String> {
    let ffprobe_path = get_ffprobe_path();
    let mut command = Command::new(&ffprobe_path);
    command.args(cmd.iter().skip(1));
    command.stdout(Stdio::piped()).stderr(Stdio::piped());

    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000);
    }

    let output = command.output().map_err(|e| {
        log::error!("Failed to start ffprobe: {}", e);
        format!("Failed to start ffprobe: {}", e)
    })?;
    Ok(String::from_utf8_lossy(&output.stdout).to_string())
}
