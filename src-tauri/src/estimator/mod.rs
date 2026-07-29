pub fn detect_cpu_performance() -> i32 {
    if cfg!(target_os = "windows") {
        let mut cmd = std::process::Command::new("wmic");
        cmd.args(["cpu", "get", "name,NumberOfCores,MaxClockSpeed", "/format:list"]);
        #[cfg(target_os = "windows")]
        {
            use std::os::windows::process::CommandExt;
            cmd.creation_flags(0x08000000);
        }
        let output = cmd.output();
        if let Ok(o) = output {
            let text = String::from_utf8_lossy(&o.stdout);
            let mut score = 500;

            if text.contains("Intel") {
                if text.contains("i9") || text.contains("Xeon") { score = 1500; }
                else if text.contains("i7") {
                    if ["10900", "11700", "12700", "13700"].iter().any(|x| text.contains(x)) { score = 1200; }
                    else if ["10700", "9700", "8700"].iter().any(|x| text.contains(x)) { score = 1000; }
                    else { score = 800; }
                }
                else if text.contains("i5") {
                    if ["12600", "13600"].iter().any(|x| text.contains(x)) { score = 900; }
                    else if ["10600", "11400", "12400"].iter().any(|x| text.contains(x)) { score = 700; }
                    else { score = 600; }
                }
                else if text.contains("i3") { score = 400; }
            } else if text.contains("AMD") {
                if text.contains("Ryzen 9") { score = 1400; }
                else if text.contains("Ryzen 7") {
                    if ["5800", "7700", "7950"].iter().any(|x| text.contains(x)) { score = 1200; }
                    else if ["5700", "5600"].iter().any(|x| text.contains(x)) { score = 1000; }
                    else { score = 800; }
                }
                else if text.contains("Ryzen 5") {
                    if ["7600", "7500"].iter().any(|x| text.contains(x)) { score = 900; }
                    else if ["5600", "5500"].iter().any(|x| text.contains(x)) { score = 700; }
                    else { score = 600; }
                }
                else if text.contains("Ryzen 3") { score = 500; }
            }

            // Core count correction
            for line in text.lines() {
                if line.contains("NumberOfCores") {
                    if let Some(val) = line.split('=').nth(1) {
                        if let Ok(cores) = val.trim().parse::<i32>() {
                            if cores >= 16 { score = (score as f64 * 1.3) as i32; }
                            else if cores >= 12 { score = (score as f64 * 1.2) as i32; }
                            else if cores >= 8 { score = (score as f64 * 1.1) as i32; }
                            else if cores <= 4 { score = (score as f64 * 0.8) as i32; }
                        }
                        break;
                    }
                }
            }

            // Clock speed correction
            for line in text.lines() {
                if line.contains("MaxClockSpeed") {
                    if let Some(val) = line.split('=').nth(1) {
                        if let Ok(mhz) = val.trim().parse::<f64>() {
                            let ghz = mhz / 1000.0;
                            if ghz >= 5.0 { score = (score as f64 * 1.2) as i32; }
                            else if ghz >= 4.0 { score = (score as f64 * 1.1) as i32; }
                            else if ghz <= 2.5 { score = (score as f64 * 0.9) as i32; }
                        }
                        break;
                    }
                }
            }

            return score;
        }
    }
    800
}

pub fn estimate_compression_time(
    duration: f64, width: usize, _height: usize, preset: &str,
    codec: &str, use_hardware: bool,
) -> f64 {
    let preset_factors = [
        ("ultrafast", 0.02), ("veryfast", 0.04), ("faster", 0.06), ("fast", 0.1),
        ("medium", 0.15), ("slow", 0.2), ("slower", 0.25), ("veryslow", 0.35),
    ];
    let base_factor = preset_factors.iter()
        .find(|(p, _)| *p == preset)
        .map(|(_, f)| *f)
        .unwrap_or(0.15);

    let resolution_factor = if width >= 3840 { 1.5 } else if width >= 1920 { 1.0 } else if width >= 1280 { 0.7 } else { 0.5 };
    let codec_factor = match codec {
        "libx265" => 1.2,
        "libvpx-vp9" => 1.3,
        _ => 1.0,
    };
    let hardware_factor = if use_hardware { 0.05 } else { 1.0 };
    let cpu_factor = 1000.0 / detect_cpu_performance() as f64;
    let duration_factor = if duration > 3600.0 { 0.9 } else if duration > 1800.0 { 0.95 } else { 1.0 };

    duration * base_factor * resolution_factor * codec_factor * hardware_factor * cpu_factor * duration_factor
}

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

pub fn estimate_size_mb(
    video_bitrate: i64, _audio_bitrate: i64, duration: f64, crf: i32, codec: &str,
    width: usize,
) -> f64 {
    if video_bitrate <= 0 || duration <= 0.0 {
        return 0.0;
    }
    let crf_ratios = [
        (18, 0.90), (19, 0.80), (20, 0.70), (21, 0.60), (22, 0.55),
        (23, 0.50), (24, 0.42), (25, 0.38), (26, 0.34), (27, 0.30),
        (28, 0.26), (29, 0.23), (30, 0.20), (31, 0.18), (32, 0.16),
        (33, 0.15), (34, 0.14), (35, 0.13),
    ];
    let base_ratio = crf_ratios.iter()
        .find(|(c, _)| *c == crf)
        .map(|(_, r)| *r)
        .unwrap_or(0.42);
    let mut ratio = base_ratio;
    if width < 1920 { ratio *= 1.2; }
    else if width < 1280 { ratio *= 1.4; }
    let codec_adj = match codec {
        "libx265" => 0.85,
        "libvpx-vp9" => 0.90,
        _ => 1.0,
    };
    ratio *= codec_adj;
    let source_kbps = video_bitrate as f64 / 1000.0;
    let target_video_kbps = source_kbps * ratio;
    let target_audio_kbps = 192.0;
    let total_kbps = target_video_kbps + target_audio_kbps;
    (total_kbps * duration) / 8.0 / 1024.0
}
