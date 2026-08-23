use regex::Regex;
use log::{debug, warn};

fn crf_regex() -> Regex {
    Regex::new(r"(?i)\bcrf[=:\s]+(\d+\.?\d*)")
        .expect("CRF regex must compile — this is a programming error")
}

/// Рекурсивно обходит весь JSON mediainfo и возвращает первый найденный CRF.
/// Это покрывает любые поля (Encoded_Library_Settings, Comment, extra.ENCODERSETTINGS
/// и т.д.), включая вложенные объекты, вместо жёсткой проверки одного поля.
fn search_crf_in_json(value: &serde_json::Value, re: &Regex) -> Option<f64> {
    match value {
        serde_json::Value::String(s) => {
            if let Some(caps) = re.captures(s) {
                if let Some(m) = caps.get(1) {
                    if let Ok(v) = m.as_str().parse::<f64>() {
                        return Some(v);
                    }
                }
            }
            None
        }
        serde_json::Value::Array(arr) => {
            for v in arr {
                if let Some(r) = search_crf_in_json(v, re) {
                    return Some(r);
                }
            }
            None
        }
        serde_json::Value::Object(map) => {
            for (_k, v) in map {
                if let Some(r) = search_crf_in_json(v, re) {
                    return Some(r);
                }
            }
            None
        }
        _ => None,
    }
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

    match search_crf_in_json(&data, &re) {
        Some(crf) => {
            debug!("CRF from mediainfo for {}: {}", file_path, crf);
            Some(crf)
        }
        None => {
            debug!("CRF pattern not found in mediainfo output for {}", file_path);
            None
        }
    }
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

#[cfg(test)]
mod tests {
    use super::*;

    fn parse(json: &str) -> serde_json::Value {
        serde_json::from_str(json).expect("test json must parse")
    }

    #[test]
    fn extracts_crf_from_comment_mp4() {
        let v = parse(r#"{"media":{"track":[{"@type":"Video","Comment":"crf=40"}]}}"#);
        let re = crf_regex();
        assert_eq!(search_crf_in_json(&v, &re), Some(40.0));
    }

    #[test]
    fn extracts_crf_from_extra_encoder_settings_mkv() {
        let v = parse(r#"{"media":{"track":[{"@type":"Video","extra":{"ENCODERSETTINGS":"crf=40"}}]}}"#);
        let re = crf_regex();
        assert_eq!(search_crf_in_json(&v, &re), Some(40.0));
    }

    #[test]
    fn extracts_crf_from_encoded_library_settings_x264() {
        let v = parse(r#"{"media":{"track":[{"@type":"Video","Encoded_Library_Settings":"cabac=1:ref=3:crf=23:qcomp=0.6"}]}}"#);
        let re = crf_regex();
        assert_eq!(search_crf_in_json(&v, &re), Some(23.0));
    }

    #[test]
    fn extracts_crf_from_deeply_nested_field() {
        let v = parse(r#"{"media":{"track":[{"@type":"Video","foo":{"bar":{"baz":"x264 crf=28 anything"}}}]}}"#);
        let re = crf_regex();
        assert_eq!(search_crf_in_json(&v, &re), Some(28.0));
    }

    #[test]
    fn returns_none_when_no_crf() {
        let v = parse(r#"{"media":{"track":[{"@type":"Video","Encoded_Library":"libsvtav1"}]}}"#);
        let re = crf_regex();
        assert_eq!(search_crf_in_json(&v, &re), None);
    }
}
