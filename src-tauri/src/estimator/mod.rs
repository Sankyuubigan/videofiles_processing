pub fn format_duration(seconds: f64) -> String {
    if seconds < 60.0 {
        format!("{}s", seconds as i32)
    } else if seconds < 3600.0 {
        let mins = seconds as i32 / 60;
        let secs = seconds as i32 % 60;
        format!("{}m {}s", mins, secs)
    } else {
        let hours = seconds as i32 / 3600;
        let mins = (seconds as i32 % 3600) / 60;
        let secs = seconds as i32 % 60;
        format!("{}h {}m {}s", hours, mins, secs)
    }
}

pub fn estimate_video_complexity(video_info: &crate::ffmpeg::probe::VideoInfo) -> (i32, String) {
    let mut score = 0;
    let typical_bitrate = if video_info.width >= 3840 { 15000 } else if video_info.width >= 1920 { 5000 } else if video_info.width >= 1280 { 3000 } else { 1500 };
    if video_info.duration > 0.0 {
        let ratio = video_info.video_bitrate as f64 / typical_bitrate as f64;
        if ratio > 2.0 { score += 4; }
        else if ratio > 1.2 { score += 2; }
        else if ratio < 0.5 { score -= 2; }
    }
    if video_info.needs_vfr_fix { score += 2; }
    if video_info.width >= 3840 { score += 2; }
    else if video_info.width >= 2560 { score += 1; }
    if video_info.fps > 50.0 { score += 1; }
    if ["mpeg2", "mpeg4", "dvvideo", "h263", "msmpeg4"].contains(&video_info.video_codec.to_lowercase().as_str()) { score += 2; }
    if video_info.pixel_format.ends_with("10le") || video_info.pixel_format.ends_with("10be") { score += 1; }
    score = score.clamp(1, 10);
    let desc = if score <= 3 { "Low" } else if score <= 6 { "Medium" } else { "High" };
    (score, desc.to_string())
}
