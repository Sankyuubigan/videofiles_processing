//! Планирование параллельного кодирования: чистые функции без побочных эффектов.
//!
//! Вынесено из `encode_parallel.rs` (там осталась только оркестрация: запуск
//! процессов, склейка, mux). Всё, что можно посчитать заранее и проверить тестами
//! без запуска ffmpeg, живёт здесь.

use log::warn;

/// Бюджет RAM на все чанки, МБ. Ограничивает число процессов для тяжёлых разрешений.
pub const RAM_LIMIT_MB: u64 = 6144;

/// Доля прогресса, отведённая на кодирование чанков (concat + mux занимают остальное).
pub const ENCODE_PROGRESS_SHARE: f64 = 80.0;

/// Сколько чанков кодировать параллельно.
///
/// Порядок ограничений: разрешение -> RAM -> ядра -> пользовательский лимит.
/// `user_cap` = `settings.parallel_workers` (0 или None = авто по числу ядер).
/// Передаётся аргументом, а не читается из настроек внутри: функция остаётся чистой
/// и тестируемой без файла настроек пользователя.
pub fn calculate_chunk_count(
    width: usize,
    height: usize,
    cores: usize,
    ram_limit_mb: u64,
    user_cap: Option<usize>,
) -> usize {
    let cores = cores.max(1);
    let pixels = (width * height) as u64;

    let max_by_resolution = if pixels >= 7680 * 4320 {
        2
    } else if pixels >= 3840 * 2160 {
        3
    } else if pixels >= 2560 * 1440 {
        4
    } else if pixels >= 1920 * 1080 {
        6
    } else {
        8
    };

    let per_process_mb = if pixels >= 3840 * 2160 {
        3000
    } else if pixels >= 1920 * 1080 {
        1500
    } else {
        800
    };
    let max_by_ram = (ram_limit_mb / per_process_mb) as usize;

    // `parallel_workers` из настроек — верхняя граница для пользователя. Раньше
    // настройка читалась в других местах пайплайна, а здесь игнорировалась, т.е.
    // число чанков определялось двумя разными правилами (нарушение SSOT).
    let user_limit = user_cap.filter(|c| *c > 0).unwrap_or(cores);

    let count = max_by_resolution
        .min(max_by_ram)
        .min(cores)
        .min(user_limit)
        .max(1);
    log::info!(
        "calculate_chunk_count: {}x{} cores={} ram_limit={}MB user_limit={} -> resolution_limit={} ram_limit_per={}MB max_by_ram={} -> chunk_count={}",
        width, height, cores, ram_limit_mb, user_limit, max_by_resolution, per_process_mb, max_by_ram, count
    );
    count
}

/// Сводный прогресс кодирования в диапазоне 0..=80 (остальное — concat + mux).
///
/// Считается как среднее по ВСЕМ чанкам, без привязки к порядку завершения: чанки
/// идут параллельно и заканчиваются в случайном порядке, поэтому прежняя формула
/// `i < done` (считавшая «первые N завершённых» полными) завышала прогресс.
pub fn calculate_overall_progress(chunk_pcts: &[i32]) -> i32 {
    let total = chunk_pcts.len();
    if total == 0 {
        return 0;
    }
    let sum: f64 = chunk_pcts
        .iter()
        .map(|p| (*p).clamp(0, 100) as f64)
        .sum();
    // sum в процентах, поэтому делим ещё и на 100: (sum / total / 100) * SHARE.
    let overall = (sum / total as f64 / 100.0) * ENCODE_PROGRESS_SHARE;
    overall.round().clamp(0.0, ENCODE_PROGRESS_SHARE) as i32
}

/// Субтитры, которые нельзя перенести в MP4: растровые дорожки не конвертируются
/// в `mov_text` (ffmpeg не умеет растрировать/распознать их в текст).
///
/// `hdmv_text_subtitle` — ТЕКСТОВЫЙ (HDMV TextST), ошибочно относился к битмапным.
pub fn is_bitmap_subtitle(codec_name: &str) -> bool {
    matches!(
        codec_name,
        "hdmv_pgs_subtitle" | "pgssub" | "dvd_subtitle" | "dvb_subtitle" | "dvb_teletext" | "xsub"
    )
}

pub enum SubtitlePlan {
    /// Копируем все дорожки как есть (mkv/webm: битмап-субы поддерживаются контейнером).
    CopyAll,
    /// Только текстовые дорожки по индексам (mp4: битмап в mov_text не конвертируется).
    TextOnly(Vec<usize>),
    /// Нечего переносить — дорожки будут отброшены с предупреждением.
    Skip(String),
}

/// Какие дорожки сабов мапить для данного контейнера.
pub fn subtitle_map_args(output_format: &str, codecs: &[String]) -> SubtitlePlan {
    if output_format != "mp4" {
        return SubtitlePlan::CopyAll;
    }
    let text_indices: Vec<usize> = codecs
        .iter()
        .enumerate()
        .filter(|(_, c)| !is_bitmap_subtitle(c))
        .map(|(i, _)| i)
        .collect();
    if text_indices.is_empty() {
        let bitmap: Vec<&str> = codecs
            .iter()
            .filter(|c| is_bitmap_subtitle(c))
            .map(|c| c.as_str())
            .collect();
        SubtitlePlan::Skip(format!("only bitmap subtitles in MP4: {:?}", bitmap))
    } else {
        SubtitlePlan::TextOnly(text_indices)
    }
}

/// Сборка команды финального mux (чистая функция — тестируется без запуска ffmpeg).
///
/// Вход 0 — склеенное видео (метаданных не содержит), вход 1 — исходник. Поэтому
/// глобальные метаданные и главы берутся ИЗ ВХОДА 1: по умолчанию ffmpeg копирует их
/// с первого входа, а он пустой — иначе теги и главы молча терялись бы.
///
/// Аудио кодируется через `audio_args` — тот же SSOT, что и в одиночном пути:
/// побитовое копирование ломает упаковку mp4 (DTS/FLAC/Opus) и не жмёт звук.
#[allow(clippy::too_many_arguments)]
pub fn build_mux_command(
    video_only_path: &str,
    input_path: &str,
    output_path: &str,
    output_format: &str,
    codec: &str,
    crf_value: i32,
    has_subtitles: bool,
    subtitle_codecs: &[String],
) -> Vec<String> {
    let mut cmd = vec![
        "ffmpeg".to_string(),
        "-y".to_string(),
        "-i".to_string(),
        video_only_path.to_string(),
        "-i".to_string(),
        input_path.to_string(),
        "-map".to_string(),
        "0:v".to_string(),
        "-map".to_string(),
        "1:a?".to_string(),
        "-map_metadata".to_string(),
        "1".to_string(),
        "-map_chapters".to_string(),
        "1".to_string(),
    ];

    if has_subtitles {
        match subtitle_map_args(output_format, subtitle_codecs) {
            SubtitlePlan::CopyAll => {
                cmd.extend(["-map".to_string(), "1:s?".to_string()]);
                cmd.extend(["-c:s".to_string(), "copy".to_string()]);
            }
            SubtitlePlan::TextOnly(indices) => {
                for idx in indices {
                    cmd.extend(["-map".to_string(), format!("1:s:{}", idx)]);
                }
                cmd.extend(["-c:s".to_string(), "mov_text".to_string()]);
            }
            SubtitlePlan::Skip(reason) => {
                warn!("Subtitles dropped for {} output: {}", output_format, reason);
            }
        }
    }

    cmd.extend(super::encode::audio_args(codec));
    if codec == "libsvtav1" {
        // SVT-AV1 не пишет EncoderSettings — CRF фиксируется тегом comment,
        // иначе приложение не сможет прочитать CRF из собственного файла.
        cmd.extend(super::encode::svtav1_crf_metadata(crf_value, output_format));
    }
    if output_format == "mp4" {
        cmd.extend(["-movflags".to_string(), "+faststart".to_string()]);
    }
    cmd.push(output_path.to_string());
    cmd
}

/// Стоит ли пробовать следующий способ после неудачи.
///
/// Отмена пользователем — не ошибка кодирования: повторные попытки после отмены
/// лишь тратят время и путают отчёт (в логе уже был кейс «Operation cancelled»,
/// который уходил в фолбэк и запускал кодирование заново).
pub fn should_attempt_fallback(result_message: &str, cancel_flag: &std::sync::atomic::AtomicBool) -> bool {
    if cancel_flag.load(std::sync::atomic::Ordering::Relaxed) {
        log::info!("Skipping fallback: cancel flag is set");
        return false;
    }
    if result_message == "Operation cancelled" {
        log::info!("Skipping fallback: result was cancellation");
        return false;
    }
    true
}

#[cfg(test)]
mod tests {
    use super::*;

    // ========== calculate_chunk_count ==========

    #[test]
    fn chunk_count_respects_resolution_limit() {
        assert!(calculate_chunk_count(7680, 4320, 100, 99999, None) <= 2, "8K max 2");
        assert!(calculate_chunk_count(3840, 2160, 100, 99999, None) <= 3, "4K max 3");
        assert!(calculate_chunk_count(2560, 1440, 100, 99999, None) <= 4, "1440p max 4");
        assert!(calculate_chunk_count(1920, 1080, 100, 99999, None) <= 6, "1080p max 6");
    }

    #[test]
    fn chunk_count_never_exceeds_cores() {
        for cores in [1, 2, 4, 8, 16] {
            let count = calculate_chunk_count(1920, 1080, cores, RAM_LIMIT_MB, None);
            assert!(count <= cores, "chunk_count({}) should not exceed cores({})", count, cores);
        }
    }

    #[test]
    fn chunk_count_never_zero() {
        // 1 ядро + 4 МБ RAM + лимит 1: min() даёт 1, а не 0 (деление на 0 выше).
        for (cores, ram) in [(1usize, 1u64), (1, 0), (1, 1000)] {
            let count = calculate_chunk_count(3840, 2160, cores, ram, Some(1));
            assert!(count >= 1, "chunk_count must be >= 1 (cores={}, ram={}), got {}", cores, ram, count);
        }
    }

    #[test]
    fn chunk_count_respects_user_cap() {
        let count = calculate_chunk_count(1920, 1080, 32, RAM_LIMIT_MB, Some(2));
        assert_eq!(count, 2, "user cap must win over resolution/RAM limits");
    }

    #[test]
    fn chunk_count_zero_cap_means_auto() {
        let auto = calculate_chunk_count(1920, 1080, 8, RAM_LIMIT_MB, None);
        let zero = calculate_chunk_count(1920, 1080, 8, RAM_LIMIT_MB, Some(0));
        assert_eq!(auto, zero, "0 must behave like 'auto', not as 'no chunks'");
    }

    #[test]
    fn chunk_count_lower_ram_never_increases_chunks() {
        let small = calculate_chunk_count(1920, 1080, 24, 2000, None);
        let big = calculate_chunk_count(1920, 1080, 24, 12000, None);
        assert!(small <= big, "smaller RAM must not increase chunks: small={} big={}", small, big);
    }

    #[test]
    fn chunk_count_monotonic_in_ram() {
        // Больше RAM доступно -> больше чанков (не меньше).
        let mut previous = 0usize;
        for ram in [2000u64, 4000, 6000, 12000, 24000] {
            let count = calculate_chunk_count(1920, 1080, 24, ram, None);
            assert!(count >= previous, "count must not shrink as RAM grows: ram={} count={}", ram, count);
            previous = count;
        }
    }

    // ========== calculate_overall_progress ==========

    #[test]
    fn progress_empty_is_zero() {
        assert_eq!(calculate_overall_progress(&[]), 0);
    }

    #[test]
    fn progress_all_zero_is_zero() {
        assert_eq!(calculate_overall_progress(&vec![0i32; 8]), 0);
    }

    #[test]
    fn progress_all_done_is_full_share() {
        let pcts = vec![100i32; 8];
        assert_eq!(calculate_overall_progress(&pcts), 80);
    }

    #[test]
    fn progress_half_done_is_half_share() {
        let pcts = vec![50i32; 4];
        assert_eq!(calculate_overall_progress(&pcts), 40);
    }

    #[test]
    fn progress_independent_of_completion_order() {
        // Регресс: старая формула `i < done` считала «первые N завершённых» полными,
        // поэтому порядок завершения чанков менял итоговый процент.
        let ordered = vec![100, 100, 0, 0];
        let scrambled = vec![0, 0, 100, 100];
        assert_eq!(
            calculate_overall_progress(&ordered),
            calculate_overall_progress(&scrambled),
            "progress must depend only on the multiset of percentages"
        );
    }

    #[test]
    fn progress_is_sum_based_not_prefix_based() {
        // 100% у последнего чанка, а не у первых двух: результат тот же, что и 1/4.
        let pcts = vec![0, 0, 0, 100];
        assert_eq!(calculate_overall_progress(&pcts), 20);
    }

    #[test]
    fn progress_clamps_out_of_range_values() {
        assert_eq!(calculate_overall_progress(&[150, 150, 150, 150]), 80);
        assert_eq!(calculate_overall_progress(&[-50, -50, -50, -50]), 0);
    }

    #[test]
    fn progress_monotonic_as_chunks_advance() {
        for step in 0..=100 {
            let pcts: Vec<i32> = (0..4).map(|_| step).collect();
            let before = calculate_overall_progress(&vec![0i32; 4]);
            let after = calculate_overall_progress(&pcts);
            assert!(after >= before, "progress must not decrease: step={} {} -> {}", step, before, after);
        }
    }

    #[test]
    fn progress_never_exceeds_encode_share() {
        let pcts: Vec<i32> = (0..12).map(|i| (i * 10).min(100)).collect();
        assert!(calculate_overall_progress(&pcts) <= 80);
    }

    // ========== is_bitmap_subtitle ==========

    #[test]
    fn bitmap_subtitles_detected() {
        for codec in [
            "hdmv_pgs_subtitle",
            "pgssub",
            "dvd_subtitle",
            "dvb_subtitle",
            "dvb_teletext",
            "xsub",
        ] {
            assert!(is_bitmap_subtitle(codec), "{} must be treated as bitmap", codec);
        }
    }

    #[test]
    fn text_subtitles_not_bitmap() {
        for codec in [
            "subrip",
            "ass",
            "ssa",
            "mov_text",
            "webvtt",
            "hdmv_text_subtitle",
            "text",
            "srt",
        ] {
            assert!(!is_bitmap_subtitle(codec), "{} is text, not bitmap", codec);
        }
    }

    // ========== subtitle_map_args ==========

    #[test]
    fn mkv_copies_all_subtitles() {
        let codecs = vec!["hdmv_pgs_subtitle".to_string(), "subrip".to_string()];
        assert!(matches!(subtitle_map_args("mkv", &codecs), SubtitlePlan::CopyAll));
    }

    #[test]
    fn mp4_maps_only_text_tracks_by_index() {
        let codecs = vec![
            "hdmv_pgs_subtitle".to_string(),
            "subrip".to_string(),
            "ass".to_string(),
        ];
        match subtitle_map_args("mp4", &codecs) {
            SubtitlePlan::TextOnly(idx) => assert_eq!(idx, vec![1, 2], "bitmap track 0 must be excluded"),
            _ => panic!("expected TextOnly"),
        }
    }

    #[test]
    fn mp4_skips_when_only_bitmap() {
        let codecs = vec!["hdmv_pgs_subtitle".to_string(), "dvd_subtitle".to_string()];
        assert!(matches!(subtitle_map_args("mp4", &codecs), SubtitlePlan::Skip(_)));
    }

    #[test]
    fn mp4_maps_text_when_hdmi_text_present() {
        // hdmv_text_subtitle — текстовый: раньше он ошибочно попадал в «bitmap»,
        // и текстовая дорожка терялась вместе с PGS.
        let codecs = vec!["hdmv_pgs_subtitle".to_string(), "hdmv_text_subtitle".to_string()];
        match subtitle_map_args("mp4", &codecs) {
            SubtitlePlan::TextOnly(idx) => assert_eq!(idx, vec![1]),
            _ => panic!("expected TextOnly for hdmv_text_subtitle"),
        }
    }

    // ========== build_mux_command ==========

    /// Значение, следующее за флагом `flag` (либо None, если флага нет).
    fn arg_after<'a>(cmd: &'a [String], flag: &str) -> Option<&'a str> {
        cmd.windows(2)
            .find(|w| w[0] == flag)
            .map(|w| w[1].as_str())
    }

    fn mux(format: &str, codec: &str, crf: i32, has_subs: bool, codecs: &[&str]) -> Vec<String> {
        let codecs: Vec<String> = codecs.iter().map(|s| s.to_string()).collect();
        build_mux_command("video.mkv", "source.mkv", "out.mp4", format, codec, crf, has_subs, &codecs)
    }

    #[test]
    fn mux_takes_metadata_and_chapters_from_source_input() {
        // Регресс: вход 0 — склеенное видео без метаданных. Без -map_metadata 1
        // ffmpeg копирует метаданные с пустого входа 0, и теги/главы терялись.
        let cmd = mux("mkv", "libx264", 22, false, &[]);
        assert_eq!(arg_after(&cmd, "-map_metadata"), Some("1"), "metadata must come from the source");
        assert_eq!(arg_after(&cmd, "-map_chapters"), Some("1"), "chapters must come from the source");
    }

    #[test]
    fn mux_video_from_concat_audio_from_source() {
        let cmd = mux("mkv", "libx264", 22, false, &[]);
        assert_eq!(arg_after(&cmd, "-map"), Some("0:v"), "video comes from concatenated input");
        assert!(cmd.windows(2).any(|w| w[0] == "-map" && w[1] == "1:a?"), "audio must come from source");
    }

    #[test]
    fn mux_reencodes_audio_same_as_single_pass() {
        // Регресс: `-c copy` для аудио ломает mp4-упаковку (DTS/FLAC/Opus) и не жмёт звук.
        let h264 = mux("mp4", "libx264", 22, false, &[]);
        assert_eq!(arg_after(&h264, "-c:a"), Some("aac"));

        let av1 = mux("mp4", "libsvtav1", 30, false, &[]);
        assert_eq!(arg_after(&av1, "-c:a"), Some("libopus"), "AV1 must use opus like the single-pass path");
    }

    #[test]
    fn mux_av1_writes_crf_metadata() {
        // Регресс: без comment=crf= приложение не читает CRF из собственного AV1-файла.
        let cmd = mux("mp4", "libsvtav1", 30, false, &[]);
        assert!(
            cmd.iter().any(|a| a == "comment=crf=30"),
            "AV1 output must carry comment=crf=, got: {:?}",
            cmd
        );
        let h264 = mux("mp4", "libx264", 22, false, &[]);
        assert!(!h264.iter().any(|a| a.starts_with("comment=crf=")), "x264 writes CRF itself");
    }

    #[test]
    fn mux_mp4_keeps_text_subs_alongside_bitmap() {
        let cmd = mux("mp4", "libx264", 22, true, &["hdmv_pgs_subtitle", "subrip"]);
        assert_eq!(arg_after(&cmd, "-c:s"), Some("mov_text"));
        assert!(
            cmd.windows(2).any(|w| w[0] == "-map" && w[1] == "1:s:1"),
            "text track must be mapped, got: {:?}",
            cmd
        );
        assert!(
            !cmd.windows(2).any(|w| w[0] == "-map" && w[1] == "1:s:0"),
            "bitmap track must not be mapped into mp4"
        );
    }

    #[test]
    fn mux_mkv_copies_bitmap_subs() {
        let cmd = mux("mkv", "libx264", 22, true, &["hdmv_pgs_subtitle", "subrip"]);
        assert_eq!(arg_after(&cmd, "-c:s"), Some("copy"));
        assert!(cmd.windows(2).any(|w| w[0] == "-map" && w[1] == "1:s?"));
    }

    #[test]
    fn mux_mp4_adds_faststart_and_output_is_last() {
        let cmd = mux("mp4", "libx264", 22, false, &[]);
        assert!(cmd.windows(2).any(|w| w[0] == "-movflags" && w[1] == "+faststart"));
        assert_eq!(cmd.last().map(|s| s.as_str()), Some("out.mp4"));
    }

    #[test]
    fn mux_without_subtitles_maps_none() {
        let cmd = mux("mp4", "libx264", 22, false, &[]);
        assert!(!cmd.iter().any(|a| a.starts_with("1:s")), "no subtitle maps expected");
    }

    // ========== should_attempt_fallback ==========
    #[test]
    fn fallback_skipped_on_cancel_flag() {
        let flag = std::sync::atomic::AtomicBool::new(true);
        assert!(!should_attempt_fallback("FFmpeg error (code 1)", &flag));
    }

    #[test]
    fn fallback_skipped_on_cancellation_message() {
        let flag = std::sync::atomic::AtomicBool::new(false);
        assert!(!should_attempt_fallback("Operation cancelled", &flag));
    }

    #[test]
    fn fallback_allowed_on_real_error() {
        let flag = std::sync::atomic::AtomicBool::new(false);
        assert!(should_attempt_fallback("FFmpeg error (code 1)", &flag));
        assert!(should_attempt_fallback("Video concat failed", &flag));
        assert!(should_attempt_fallback("Parallel encode segments failed", &flag));
    }
}
