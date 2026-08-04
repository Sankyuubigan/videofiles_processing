use regex::Regex;
use log::{debug, warn};

fn crf_regex() -> Regex {
    Regex::new(r"(?i)\bcrf[=:\s]+(\d+\.?\d*)")
        .expect("CRF regex must compile — this is a programming error")
}

fn try_mediainfo(file_path: &str) -> Option<f64> {
    let mediainfo_path = crate::settings::get_mediainfo_path();
    if !std::path::Path::new(&mediainfo_path).exists() {
        debug!("mediainfo not found at {}", mediainfo_path);
        return None;
    }

    let mut cmd = std::process::Command::new(&mediainfo_path);
    cmd.args(["--Output=JSON", file_path]);
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x08000000);
    }
    let output = match cmd.output()
    {
        Ok(o) => o,
        Err(e) => {
            warn!("mediainfo failed to execute for {}: {}", file_path, e);
            return None;
        }
    };

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        warn!("mediainfo exited with error for {}: {}", file_path, stderr);
        return None;
    }

    let text = String::from_utf8_lossy(&output.stdout);
    if text.trim().is_empty() {
        warn!("mediainfo returned empty output for {}", file_path);
        return None;
    }

    let data: serde_json::Value = match serde_json::from_str(&text) {
        Ok(d) => d,
        Err(e) => {
            warn!("mediainfo JSON parse error for {}: {}", file_path, e);
            return None;
        }
    };

    let re = crf_regex();

    let tracks = match data.get("media")
        .and_then(|m| m.get("track")).and_then(|t| t.as_array())
    {
        Some(t) => t,
        None => {
            warn!("mediainfo JSON structure unexpected for {}: no track array found. Keys: {:?}",
                file_path,
                data.get("media").map(|m| m.as_object().map(|o| o.keys().collect::<Vec<_>>())).flatten());
            return None;
        }
    };

    for track in tracks {
        if track.get("@type").and_then(|v| v.as_str()) == Some("Video") {
            let settings_str = track.get("Encoded_Library_Settings")
                .or_else(|| track.get("encoding_settings"))
                .and_then(|v| v.as_str());
            match settings_str {
                Some(settings) => {
                    debug!("mediainfo Encoded_Library_Settings for {}: {}", file_path, settings);
                    if let Some(caps) = re.captures(settings) {
                        if let Some(val) = caps.get(1) {
                            match val.as_str().parse::<f64>() {
                                Ok(crf) => {
                                    debug!("CRF from mediainfo for {}: {}", file_path, crf);
                                    return Some(crf);
                                }
                                Err(e) => {
                                    warn!("CRF parse error '{}' for {}: {}", val.as_str(), file_path, e);
                                }
                            }
                        }
                    } else {
                        debug!("CRF pattern not found in Encoded_Library_Settings for {}", file_path);
                    }
                }
                None => {
                    debug!("No Encoded_Library_Settings in video track for {}", file_path);
                }
            }
        }
    }

    None
}

fn try_ffprobe_tags(file_path: &str) -> Option<f64> {
    let ffprobe_path = crate::settings::get_ffprobe_path();
    let mut cmd = std::process::Command::new(&ffprobe_path);
    cmd.args(["-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", file_path]);
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x08000000);
    }
    let output = match cmd.output()
    {
        Ok(o) => o,
        Err(e) => {
            warn!("ffprobe failed to execute for {}: {}", file_path, e);
            return None;
        }
    };

    let text = String::from_utf8_lossy(&output.stdout);
    let data: serde_json::Value = match serde_json::from_str(&text) {
        Ok(d) => d,
        Err(e) => {
            warn!("ffprobe JSON parse error for {}: {}", file_path, e);
            return None;
        }
    };

    let re = crf_regex();

    let search_tags = |tags: Option<&serde_json::Map<String, serde_json::Value>>| -> Option<f64> {
        if let Some(tags_map) = tags {
            for (_key, value) in tags_map {
                if let Some(val_str) = value.as_str() {
                    if let Some(caps) = re.captures(val_str) {
                        if let Some(val) = caps.get(1) {
                            return val.as_str().parse::<f64>().ok();
                        }
                    }
                }
            }
        }
        None
    };

    if let Some(streams) = data.get("streams").and_then(|s| s.as_array()) {
        for stream in streams {
            if stream.get("codec_type").and_then(|s| s.as_str()) == Some("video") {
                if let Some(crf) = search_tags(stream.get("tags").and_then(|t| t.as_object())) {
                    return Some(crf);
                }
            }
        }
    }

    search_tags(data.get("format").and_then(|f| f.get("tags")).and_then(|t| t.as_object()))
}

pub fn get_crf_from_file(file_path: &str) -> Option<f64> {
    if let Some(crf) = try_mediainfo(file_path) {
        return Some(crf);
    }

    if let Some(crf) = try_ffprobe_tags(file_path) {
        return Some(crf);
    }

    debug!("CRF not found for {}", file_path);
    None
}
