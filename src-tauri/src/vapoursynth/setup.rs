use std::os::windows::process::CommandExt as _;
use std::path::Path;
use tokio::io::AsyncBufReadExt;
use tokio::process::Command;
use crate::vapoursynth;

pub const INSTALLER_PS1_URL: &str =
    "https://raw.githubusercontent.com/vapoursynth/vapoursynth/master/installer/install-portable-vapoursynth.ps1";
pub const RELEASES_URL: &str = "https://api.github.com/repos/vapoursynth/vapoursynth/releases";
pub const SM_DEGRAIN_PACKAGE: &str = "smdegrain-bis";
pub const SEVENZR_URL: &str = "https://www.7-zip.org/a/7zr.exe";
pub const SEVENZ_EXTRA_URL: &str = "https://www.7-zip.org/a/7z2602-extra.7z";
const SAFE_SUB_CODECS: [&str; 6] = ["subrip", "srt", "ass", "ssa", "webvtt", "text"];

/// Idempotent: installs portable VapourSynth + plugins if missing,
/// otherwise only ensures plugins/scripts are present.
pub async fn ensure_installed<F: Fn(String) + Clone>(progress: F) -> Result<(), String> {
    if vapoursynth::is_installed() {
        progress("VapourSynth already installed".to_string());
        return ensure_plugins(progress).await;
    }
    install_portable(progress.clone()).await?;
    ensure_plugins(progress).await
}

async fn download_file<F: Fn(String)>(
    url: &str,
    dest: &Path,
    label: &str,
    progress: &F,
) -> Result<(), String> {
    progress(format!("Downloading {}...", label));
    let client = reqwest::Client::new();
    let response = client
        .get(url)
        .send()
        .await
        .map_err(|e| format!("Failed to start download of {}: {}", label, e))?;
    let bytes = response
        .bytes()
        .await
        .map_err(|e| format!("Failed to download {}: {}", label, e))?;
    std::fs::write(dest, &bytes)
        .map_err(|e| format!("Failed to write {}: {}", label, e))
}

async fn latest_vs_version() -> Result<Option<(String, String)>, String> {
    let client = reqwest::Client::new();
    let releases: serde_json::Value = client
        .get(RELEASES_URL)
        .header("User-Agent", "VideoFile-Pro")
        .send()
        .await
        .map_err(|e| format!("Failed to fetch VapourSynth releases: {}", e))?
        .json()
        .await
        .map_err(|e| format!("Failed to parse VapourSynth releases: {}", e))?;
    let arr = releases
        .as_array()
        .ok_or_else(|| "Unexpected GitHub releases response".to_string())?;
    for release in arr {
        if release["prerelease"].as_bool().unwrap_or(true) {
            continue;
        }
        let tag = release["tag_name"]
            .as_str()
            .unwrap_or("")
            .trim_start_matches('R')
            .to_string();
        if tag.is_empty() {
            continue;
        }
        let (base, extra) = match tag.find('.') {
            Some(idx) => (tag[..idx].to_string(), tag[idx..].to_string()),
            None => (tag.clone(), String::new()),
        };
        if base.parse::<i32>().is_ok() {
            return Ok(Some((base, extra)));
        }
    }
    Ok(None)
}

/// The repo script starts with the *tail* of its `param()` block (the header
/// is prepended by `make_portable.bat` at release build time):
///
///     [string]$TargetFolder = ".\vapoursynth-portable",
///     [int]$PythonVersionMajor = 3,
///     [int]$PythonVersionMinor = 14,
///     [switch]$Unattended
///     )
///
/// We remove that orphan block and prepend a complete one, and make output
/// streamable (Write-Host -> Write-Output).
fn patch_installer_script(original: &str, version_args: &[String]) -> String {
    let mut version = "79".to_string();
    let mut extra = String::new();
    if version_args.len() >= 4 {
        version = version_args[1].clone();
        extra = version_args[3].clone();
    }
    let header = format!(
        "param(\n\
         \x20   [int]$VSVersion = {},\n\
         \x20   [string]$VSVersionExtra = \"{}\",\n\
         \x20   [string]$TargetFolder = \".\\vapoursynth-portable\",\n\
         \x20   [int]$PythonVersionMajor = 3,\n\
         \x20   [int]$PythonVersionMinor = 14,\n\
         \x20   [switch]$Unattended\n\
         )\n\n",
        version, extra
    );
    let mut body = String::new();
    let mut in_block = false;
    for line in original.lines() {
        let trimmed = line.trim();
        if !in_block
            && (trimmed.starts_with("param(") || trimmed.starts_with("[string]$TargetFolder"))
        {
            in_block = true;
        }
        if in_block {
            if trimmed == ")" {
                in_block = false;
            }
            continue;
        }
        body.push_str(line);
        body.push('\n');
    }
    let body = body.replace("-ForegroundColor Green", "");
    let body = body.replace("Write-Host", "Write-Output");
    format!("{}{}", header, body)
}

async fn install_portable<F: Fn(String)>(progress: F) -> Result<(), String> {
    vapoursynth::ensure_dir(&vapoursynth::vs_root_dir())?;

    let ps1_path = vapoursynth::installer_ps1_path();
    download_file(INSTALLER_PS1_URL, &ps1_path, "VapourSynth installer", &progress).await?;

    let version_args: Vec<String> = match latest_vs_version().await {
        Ok(Some((base, extra))) => {
            progress(format!("Installing VapourSynth R{}{}...", base, extra));
            vec![
                "-VSVersion".to_string(),
                base,
                "-VSVersionExtra".to_string(),
                extra,
            ]
        }
        Ok(None) => {
            log::warn!("Could not determine latest VapourSynth version, using installer defaults");
            progress("Installing VapourSynth (latest stable)...".to_string());
            Vec::new()
        }
        Err(e) => {
            log::warn!("Failed to fetch VapourSynth version ({}), using installer defaults", e);
            progress("Installing VapourSynth (latest stable)...".to_string());
            Vec::new()
        }
    };
    let target = vapoursynth::portable_dir().to_string_lossy().to_string();

    // The raw repo script has no `param()` block (it is prepended at release build time),
    // and Write-Host output does not go to stdout. Patch both before running.
    let original = std::fs::read_to_string(&ps1_path).map_err(|e| {
        format!("Failed to read installer script {:?}: {}", ps1_path, e)
    })?;
    let patched = patch_installer_script(&original, &version_args);
    let patched_path = vapoursynth::vs_root_dir().join("install-portable-vapoursynth.patched.ps1");
    std::fs::write(&patched_path, patched).map_err(|e| {
        format!("Failed to write patched installer script: {}", e)
    })?;

    let mut child = Command::new("powershell");
    child.creation_flags(0x08000000);
    child.args(["-NoProfile", "-ExecutionPolicy", "Bypass", "-File"]);
    child.arg(patched_path.to_string_lossy().as_ref());
    child.args(&version_args);
    child.args(["-TargetFolder", target.as_str(), "-Unattended"]);
    child.stdout(std::process::Stdio::piped()).stderr(std::process::Stdio::piped());
    let mut child = child
        .spawn()
        .map_err(|e| format!("Failed to start PowerShell installer: {}", e))?;

    let mut captured: Vec<String> = Vec::new();
    if let Some(stdout) = child.stdout.take() {
        let mut reader = tokio::io::BufReader::new(stdout).lines();
        while let Ok(Some(line)) = reader.next_line().await {
            let line = line.trim().to_string();
            if !line.is_empty() {
                captured.push(line.clone());
                progress(line);
            }
        }
    }
    if let Some(stderr) = child.stderr.take() {
        let mut reader = tokio::io::BufReader::new(stderr).lines();
        while let Ok(Some(line)) = reader.next_line().await {
            let line = line.trim().to_string();
            if !line.is_empty() {
                captured.push(line.clone());
            }
        }
    }
    let status = child
        .wait()
        .await
        .map_err(|e| format!("Failed to wait for PowerShell installer: {}", e))?;
    if !status.success() {
        let tail: Vec<String> = captured.into_iter().rev().take(20).collect();
        return Err(format!(
            "VapourSynth installer failed (code {:?}).\n{}",
            status.code(),
            tail.join("\n")
        ));
    }

    if !vapoursynth::is_installed() {
        return Err("VapourSynth installed but vspipe.bat was not found".to_string());
    }
    progress("VapourSynth installed successfully".to_string());
    Ok(())
}

async fn ensure_plugins<F: Fn(String) + Clone>(progress: F) -> Result<(), String> {
    let python = vapoursynth::python_exe_path();
    if !python.exists() {
        return Err("VapourSynth python.exe not found".to_string());
    }

    // 1. Ensure vsrepo is available
    progress("Ensuring vsrepo...".to_string());
    if !vapoursynth::vsrepo_exe_path().exists() {
        let (code, _out) = run_capture(
            &python,
            &["-m", "pip", "install", "--no-warn-script-location", "vsrepo"],
        )
        .await;
        if code != 0 {
            log::warn!("pip install vsrepo failed (code {})", code);
        }
    }

    // 2. vsrepo needs 7z.exe next to it to extract plugin archives
    ensure_7zip(progress.clone()).await?;

    // 3. Update vsrepo index
    let (code, out) = vsrepo(&["update"]).await;
    if code != 0 {
        log::warn!("vsrepo update failed (code {}): {}", code, out);
    }

    // 4. Install plugins and helper scripts (best effort)
    for item in ["mvtools", "bm3d", "bm3dcuda", "knlmeanscl", "ffms2", "fmtconv", "havsfunc", "mvsfunc", "lsmashsource"] {
        progress(format!("Installing VapourSynth plugin/script: {}", item));
        let (code, out) = vsrepo(&["install", item]).await;
        if code != 0 {
            log::warn!("vsrepo install {} failed (code {}): {}", item, code, out);
        }
    }

    // 5. Ensure SMDegrain (smdegrain_bis pip package)
    ensure_smdegrain(progress.clone()).await?;

    // 6. Ensure the native mvuscale plugin (UHDhalf vector scaler for
    //    SMDegrain on UHD inputs). Best-effort: if it cannot be installed the
    //    generated scripts fall back to UHDhalf=False, so denoise still works.
    ensure_mvuscale(progress).await
}

/// Installs `vapoursynth-mvuscale` (the native `core.mvuscale` plugin needed by
/// `smdegrain_bis` for `UHDhalf=True` on 4K sources). The package self-registers
/// through `_ensure_mvuscale` in the generated vpy. Failure is not fatal — the
/// vpy falls back to a full-res SMDegrain search.
async fn ensure_mvuscale<F: Fn(String)>(progress: F) -> Result<(), String> {
    let python = vapoursynth::python_exe_path();
    progress("Installing vapoursynth-mvuscale...".to_string());
    let (code, out) = run_capture(
        &python,
        &["-m", "pip", "install", "--no-warn-script-location", "vapoursynth-mvuscale"],
    )
    .await;
    if code != 0 {
        log::warn!(
            "pip install vapoursynth-mvuscale failed (code {}): {} — denoise will use UHDhalf=False on UHD",
            code,
            out
        );
        progress("vapoursynth-mvuscale unavailable (fallback to full-res SMDegrain)".to_string());
    } else {
        progress("vapoursynth-mvuscale installed".to_string());
    }
    Ok(())
}

/// vsrepo extracts plugin archives with 7z; it looks for 7z.exe next to itself.
/// We download the standalone 7zr (handles .7z) and use it to unpack the
/// official "extra" package, then place 7za.exe (all formats) as 7z.exe.
async fn ensure_7zip<F: Fn(String) + Clone>(progress: F) -> Result<(), String> {
    let seven_exe = vapoursynth::vsrepo_7z_path();
    if seven_exe.exists() {
        progress("7-Zip already present".to_string());
        return Ok(());
    }
    progress("Installing 7-Zip for vsrepo...".to_string());
    let root = vapoursynth::vs_root_dir();
    vapoursynth::ensure_dir(&root)?;
    let sevenzr = root.join("7zr.exe");
    let extra = root.join("7z2602-extra.7z");
    download_file(SEVENZR_URL, &sevenzr, "7-Zip (7zr)", &progress).await?;
    download_file(SEVENZ_EXTRA_URL, &extra, "7-Zip extra", &progress).await?;

    let out_dir = root.join("7zextra");
    vapoursynth::ensure_dir(&out_dir)?;
    let extra_str = extra.to_string_lossy().to_string();
    let out_arg = format!("-o{}", out_dir.to_string_lossy());
    let (code, out) = run_capture(&sevenzr, &["e", &extra_str, &out_arg, "7za.exe"]).await;
    if code != 0 {
        let _ = std::fs::remove_dir_all(&out_dir);
        return Err(format!("7-Zip extraction failed (code {}): {}", code, out));
    }
    let extracted = out_dir.join("7za.exe");
    if !extracted.exists() {
        let _ = std::fs::remove_dir_all(&out_dir);
        return Err("7-Zip extraction produced no 7za.exe".to_string());
    }
    let vsrepo_dir = vapoursynth::vsrepo_dir();
    vapoursynth::ensure_dir(&vsrepo_dir)?;
    std::fs::copy(&extracted, &seven_exe)
        .map_err(|e| format!("Failed to place 7z.exe: {}", e))?;
    let _ = std::fs::remove_dir_all(&out_dir);
    let _ = std::fs::remove_file(&extra);
    let _ = std::fs::remove_file(&sevenzr);
    progress("7-Zip installed".to_string());
    Ok(())
}

/// Runs `vsrepo <args>` with the portable install's python.
async fn vsrepo(args: &[&str]) -> (i32, String) {
    let python = vapoursynth::python_exe_path();
    if vapoursynth::vsrepo_exe_path().exists() {
        return run_capture(&vapoursynth::vsrepo_exe_path(), args).await;
    }
    let mut full: Vec<String> = vec!["-m".to_string(), "vapoursynth.vsrepo".to_string()];
    full.extend(args.iter().map(|a| a.to_string()));
    let strs: Vec<&str> = full.iter().map(|s| s.as_str()).collect();
    run_capture(&python, &strs).await
}

async fn ensure_smdegrain<F: Fn(String)>(progress: F) -> Result<(), String> {
    let python = vapoursynth::python_exe_path();
    let (check_code, _out) = run_capture(&python, &["-c", "import smdegrain_bis"]).await;
    if check_code == 0 {
        progress("SMDegrain already present".to_string());
        return Ok(());
    }
    progress("Installing SMDegrain (smdegrain-bis)...".to_string());
    let (code, out) = run_capture(
        &python,
        &["-m", "pip", "install", "--no-warn-script-location", SM_DEGRAIN_PACKAGE],
    )
    .await;
    if code != 0 {
        return Err(format!(
            "Failed to install smdegrain-bis (code {}): {}",
            code, out
        ));
    }
    progress("SMDegrain installed".to_string());
    Ok(())
}

async fn run_capture(program: &Path, args: &[&str]) -> (i32, String) {
    let output = match Command::new(program).creation_flags(0x08000000).args(args).output().await {
        Ok(o) => o,
        Err(e) => return (1, format!("Failed to start {:?}: {}", program, e)),
    };
    let mut text = String::from_utf8_lossy(&output.stdout).to_string();
    if !output.stderr.is_empty() {
        text.push_str(&String::from_utf8_lossy(&output.stderr));
    }
    (
        output.status.code().unwrap_or(-1),
        text.lines().rev().take(10).collect::<Vec<_>>().join("\n"),
    )
}

/// True if the file has subtitles and all subtitle codecs are safe to copy into mkv.
pub fn subtitles_compatible(input: &str) -> bool {
    let ffprobe = crate::settings::get_ffprobe_path();
    let output = match std::process::Command::new(&ffprobe)
        .creation_flags(0x08000000)
        .args([
            "-v", "error", "-show_entries",
            "stream=codec_type,codec_name", "-of", "json", input,
        ])
        .output()
    {
        Ok(o) => o,
        Err(e) => {
            log::warn!("Failed to run ffprobe for subtitles check: {}", e);
            return false;
        }
    };
    let json: serde_json::Value = match serde_json::from_slice(&output.stdout) {
        Ok(v) => v,
        Err(_) => return false,
    };
    let mut sub_streams = 0usize;
    let mut all_safe = true;
    if let Some(streams) = json["streams"].as_array() {
        for stream in streams {
            if stream["codec_type"].as_str() != Some("subtitle") {
                continue;
            }
            sub_streams += 1;
            let codec = stream["codec_name"].as_str().unwrap_or("");
            if !SAFE_SUB_CODECS.contains(&codec) {
                all_safe = false;
            }
        }
    }
    sub_streams > 0 && all_safe
}