use crate::ffmpeg::probe::VideoType;

/// AV1 всегда кодируется в 10-bit (даже из 8-bit источников) — убирает бандинг
/// в градиентах и тенях без заметного замедления (рекомендация доки, 2026).
pub const AV1_PIX_FMT: &str = "yuv420p10le";

/// Flat film-grain, когда авто-пресеты по контенту отключены.
const FLAT_FILM_GRAIN: i32 = 8;

/// Параметры SVT-AV1, зависящие от типа контента и зернистости источника.
pub struct Av1Params {
    pub film_grain: i32,
    pub tune: i32,
}

impl Av1Params {
    /// Собирает строку `-svtav1-params` (GOP 10s, VQ, scene change, film-grain).
    /// `film-grain-denoise=1` велит кодеру реально удалить смоделированное зерно
    /// из кадров перед кодированием (это и даёт экономию битрейта); работает
    /// только когда film-grain включён (film-grain>0).
    pub fn svtav1_params(&self) -> String {
        format!(
            "keyint=10s:tune={}:scd=1:film-grain={}:film-grain-denoise=1",
            self.tune, self.film_grain
        )
    }
}

/// Авто-выбор film-grain по типу контента и замеренной зернистости:
/// - Animation / 2D: 4 (плоская заливка хорошо сжимается, лёгкое зерно)
/// - Rendered (геймплей / скринкасты / 3D): 0 (зерна нет)
/// - LiveAction: 8; тяжёлое зерно (grain_ydif >= GRAIN_HEAVY_THRESHOLD) -> 12
pub fn params_for(video_type: &VideoType, grain_ydif: Option<f64>) -> Av1Params {
    let film_grain = match video_type {
        VideoType::Animation => 4,
        VideoType::Rendered => 0,
        VideoType::LiveAction => match grain_ydif {
            Some(ydif) if ydif >= crate::video_processor::grain::GRAIN_HEAVY_THRESHOLD => 12,
            _ => 8,
        },
    };
    Av1Params { film_grain, tune: 0 }
}

/// Максимум параллельных SVT-AV1 инстансов, чтобы не улететь в OOM:
/// каждый 4K-инстанс (preset 6, 10-bit) держит ~1-1.5 ГБ буферов кадра.
/// Значения в духе Av1an workers: чем выше разрешение, тем меньше воркеров.
pub fn av1_parallel_worker_cap(width: usize, height: usize) -> usize {
    let pixels = width as u64 * height as u64;
    if pixels >= 3840 * 2160 {
        2
    } else if pixels >= 2560 * 1440 {
        3
    } else if pixels >= 1920 * 1080 {
        4
    } else {
        6
    }
}

/// Ограничивает число воркеров для libsvtav1 с учётом разрешения (>= 1).
pub fn cap_parallel_workers(base: usize, width: usize, height: usize) -> usize {
    base.min(av1_parallel_worker_cap(width, height)).max(1)
}

/// Число логических процессоров на один SVT-AV1 инстанс, когда их запущено
/// `workers` параллельно: `max(1, cores / workers)` — суммарно не превышаем CPU.
pub fn av1_lp_for_workers(workers: usize) -> usize {
    let cores = std::thread::available_parallelism()
        .map(|n| n.get())
        .unwrap_or(4);
    (cores / workers.max(1)).max(1)
}

/// Чистая сборка значения `-svtav1-params` (без `-pix_fmt` и прочего). Выделена
/// отдельно как SSOT и для юнит-тестов: одинакова для замера auto-CRF и финала.
/// `film-grain-denoise=1` добавляется только когда `grain_denoise && film_grain > 0`
/// (иначе при `film-grain=0` флаг бессмыслен, а при preserve — вреден).
pub fn build_svtav1_params_value(
    lp: Option<usize>,
    film_grain: i32,
    grain_denoise: bool,
) -> String {
    let mut s = format!("keyint=10s:tune=0:scd=1:film-grain={}", film_grain);
    if grain_denoise && film_grain > 0 {
        s.push_str(":film-grain-denoise=1");
    }
    if let Some(lp) = lp {
        if lp > 0 {
            s.push_str(&format!(":lp={}", lp));
        }
    }
    s
}

/// Возвращает ffmpeg-аргументы для libsvtav1: `-svtav1-params` + `-pix_fmt yuv420p10le`.
/// Учитывает настройки: авто-пресеты по контенту, ручной оверрайд `film-grain` и
/// `av1_preserve_film_grain` (сохранять натуральное зерно — выключает синтез и денойз).
/// `lp` (логические процессоры на инстанс) задаётся вызывающим единообразно для
/// замера auto-CRF и финального энкода, чтобы measured VMAF == actual VMAF.
pub fn svtav1_args(video_type: &VideoType, grain_ydif: Option<f64>, lp: Option<usize>) -> Vec<String> {
    let settings = crate::settings::load_settings();
    let preserve = settings.av1_preserve_film_grain;
    let base = if settings.av1_use_content_presets {
        params_for(video_type, grain_ydif)
    } else {
        Av1Params { film_grain: FLAT_FILM_GRAIN, tune: 0 }
    };
    let base_film_grain = if settings.av1_film_grain >= 0 {
        settings.av1_film_grain
    } else {
        base.film_grain
    };
    let film_grain = if preserve { 0 } else { base_film_grain };
    let grain_denoise = !preserve;
    let value = build_svtav1_params_value(lp, film_grain, grain_denoise);
    vec![
        "-svtav1-params".to_string(),
        value,
        "-pix_fmt".to_string(),
        AV1_PIX_FMT.to_string(),
    ]
}

#[cfg(test)]
mod tests {
    use super::build_svtav1_params_value;

    #[test]
    fn lp_some_appends_lp() {
        let v = build_svtav1_params_value(Some(12), 8, true);
        assert!(v.contains("film-grain=8"), "got: {}", v);
        assert!(v.contains("film-grain-denoise=1"), "got: {}", v);
        assert!(v.contains("lp=12"), "got: {}", v);
    }

    #[test]
    fn lp_none_has_no_lp() {
        let v = build_svtav1_params_value(None, 8, true);
        assert!(!v.contains("lp="), "got: {}", v);
        assert!(v.contains("film-grain=8"), "got: {}", v);
    }

    #[test]
    fn preserve_grain_zeroes_synthesis_and_denoise() {
        // preserve => film_grain=0, grain_denoise=false: натуральное зерно сохранено.
        let v = build_svtav1_params_value(None, 0, false);
        assert!(v.contains("film-grain=0"), "got: {}", v);
        assert!(!v.contains("film-grain-denoise"), "got: {}", v);
    }

    #[test]
    fn denoise_flag_only_when_grain_present() {
        // film_grain=0 + grain_denoise=true => флаг не добавляется (бессмыслен).
        let v = build_svtav1_params_value(Some(4), 0, true);
        assert!(v.contains("film-grain=0"), "got: {}", v);
        assert!(!v.contains("film-grain-denoise"), "got: {}", v);
    }

    #[test]
    fn auto_crf_and_final_share_params_shape() {
        // Замер и финал должны получать идентичную строку при одинаковом (lp, grain, denoise).
        let measured = build_svtav1_params_value(Some(8), 8, true);
        let final_out = build_svtav1_params_value(Some(8), 8, true);
        assert_eq!(measured, final_out);
    }
}