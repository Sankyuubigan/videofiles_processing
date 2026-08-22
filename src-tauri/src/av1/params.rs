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

/// Возвращает ffmpeg-аргументы для libsvtav1: `-svtav1-params` + `-pix_fmt yuv420p10le`.
/// Учитывает настройки: авто-пресеты по контенту и ручной оверрайд film-grain.
/// `lp` (логические процессоры на инстанс) задаётся при параллельном чанковом
/// кодировании, чтобы N инстансов не перегружали CPU/RAM; `None` = авто (все ядра).
pub fn svtav1_args(video_type: &VideoType, grain_ydif: Option<f64>, lp: Option<usize>) -> Vec<String> {
    let settings = crate::settings::load_settings();
    let params = if settings.av1_use_content_presets {
        params_for(video_type, grain_ydif)
    } else {
        Av1Params { film_grain: FLAT_FILM_GRAIN, tune: 0 }
    };
    let film_grain = if settings.av1_film_grain >= 0 {
        settings.av1_film_grain
    } else {
        params.film_grain
    };
    let mut svtav1 = format!(
        "keyint=10s:tune={}:scd=1:film-grain={}:film-grain-denoise=1",
        params.tune, film_grain
    );
    if let Some(lp) = lp {
        if lp > 0 {
            svtav1.push_str(&format!(":lp={}", lp));
        }
    }
    vec![
        "-svtav1-params".to_string(),
        svtav1,
        "-pix_fmt".to_string(),
        AV1_PIX_FMT.to_string(),
    ]
}