use std::sync::atomic::{AtomicBool, AtomicI32, Ordering};
use std::sync::Arc;
use log::{info, warn, error};

use super::core::{run_command_simple, RunResult};
use super::encode::{encode_chunk_with_progress, ChunkEncodeOptions};
use super::parallel_plan::{
    build_mux_command, calculate_chunk_count, calculate_overall_progress, RAM_LIMIT_MB,
};
use super::probe::{VideoInfo, VideoType};
use crate::process_control::PidTracker;

struct SegmentSpec {
    start_time: f64,
    duration: f64,
    output_path: String,
}

fn cleanup_temp_files(specs: &[SegmentSpec]) {
    for spec in specs {
        if let Err(e) = std::fs::remove_file(&spec.output_path) {
            warn!("Failed to remove temp file {}: {}", spec.output_path, e);
        }
    }
}

/// РќРµРёР·РјРµРЅСЏРµРјС‹Рµ Р°СЂРіСѓРјРµРЅС‚С‹ РєРѕРґРёСЂРѕРІР°РЅРёСЏ, РѕР±С‰РёРµ РґР»СЏ РІСЃРµС… С‡Р°РЅРєРѕРІ РѕРґРЅРѕРіРѕ Р·Р°РїСѓСЃРєР°.
/// РљР»РѕРЅРёСЂСѓСЋС‚СЃСЏ РІ РєР°Р¶РґС‹Р№ РїРѕС‚РѕРє: СЃРѕР±РёСЂР°С‚СЊ `String` РІРЅСѓС‚СЂРё С†РёРєР»Р° Р·РЅР°С‡РёР»Рѕ Р±С‹
/// РїРµСЂРµСЃРѕР·РґР°РІР°С‚СЊ РёС… N СЂР°Р·, Р° `.clone()` РґРµС€РµРІР»Рµ Рё СЏРІРЅРѕ СЂР°Р·РґРµР»СЏРµС‚ В«РѕР±С‰РµРµВ» Рё В«РїРѕ С‡Р°РЅРєСѓВ».
#[derive(Clone)]
struct ChunkEncodeArgs {
    input: String,
    codec: String,
    crf: i32,
    preset: String,
    use_hardware: bool,
    video_info: VideoInfo,
    video_type: VideoType,
    svtav1_lp: Option<usize>,
    threads: usize,
    x264_extra_params: String,
}

impl ChunkEncodeArgs {
    #[allow(clippy::too_many_arguments)]
    fn new(
        input_path: &str,
        codec: &str,
        crf: i32,
        preset: &str,
        use_hardware: bool,
        video_info: &VideoInfo,
        video_type: &VideoType,
        svtav1_lp: Option<usize>,
        threads: usize,
        x264_extra_params: &str,
    ) -> Self {
        Self {
            input: input_path.to_string(),
            codec: codec.to_string(),
            crf,
            preset: preset.to_string(),
            use_hardware,
            video_info: video_info.clone(),
            video_type: video_type.clone(),
            svtav1_lp,
            threads,
            x264_extra_params: x264_extra_params.to_string(),
        }
    }
}

/// РћР±С‘СЂС‚РєР° РЅР°Рґ С‡Р°РЅРєРѕРІС‹Рј РїСЂРѕРіСЂРµСЃСЃРѕРј: РїРёС€РµС‚ РїСЂРѕС†РµРЅС‚ С‡Р°РЅРєР°, РїРµСЂРµСЃС‡РёС‚С‹РІР°РµС‚ РѕР±С‰РёР№ РїСЂРѕС†РµРЅС‚
/// Рё РѕС‚РґР°С‘С‚ РЅР°СЂСѓР¶Сѓ С‚РѕР»СЊРєРѕ РЎР’РћР” (С‡С‚РѕР±С‹ РЅРµ СЃРїР°РјРёС‚СЊ UI РЅР° РєР°Р¶РґС‹Р№ `out_time_us`).
fn make_chunk_progress_callback(
    chunk_index: usize,
    orig: Option<Arc<dyn Fn(i32, String) + Send + Sync>>,
    chunk_done: Arc<AtomicBool>,
    chunk_pct: Arc<AtomicI32>,
    last_reported: Arc<AtomicI32>,
    all_done: Vec<Arc<AtomicBool>>,
    all_pcts: Vec<Arc<AtomicI32>>,
    total: usize,
) -> Option<Arc<dyn Fn(i32, String) + Send + Sync>> {
    orig.map(move |orig| {
        Arc::new(move |pct: i32, msg: String| {
            chunk_pct.store(pct.clamp(0, 100), Ordering::SeqCst);
            if pct >= 100 && !chunk_done.swap(true, Ordering::SeqCst) {
                log::debug!("Chunk {} marked as completed", chunk_index);
            }
            let done_count = all_done.iter().filter(|d| d.load(Ordering::SeqCst)).count();
            let pcts: Vec<i32> = all_pcts.iter().map(|a| a.load(Ordering::SeqCst)).collect();
            let overall = calculate_overall_progress(&pcts);
            let prev = last_reported.fetch_max(overall, Ordering::SeqCst);
            if overall > prev {
                let _ = orig(overall, format!("Chunk {}/{}: {}", done_count.min(total), total, msg));
            }
        }) as Arc<dyn Fn(i32, String) + Send + Sync>
    })
}

pub fn compress_video_parallel(
    input_path: &str,
    output_path: &str,
    output_format: &str,
    codec: &str,
    crf_value: i32,
    preset_value: &str,
    duration_seconds: f64,
    video_info: &VideoInfo,
    video_type: &VideoType,
    use_hardware: bool,
    parallel_workers: usize,
    cancel_flag: Arc<AtomicBool>,
    progress_cb: Option<Arc<dyn Fn(i32, String) + Send + Sync>>,
    child_pid: Option<PidTracker>,
) -> RunResult {
    let cores = std::thread::available_parallelism()
        .map(|n| n.get())
        .unwrap_or(4);
    let chunk_count = calculate_chunk_count(
        video_info.width,
        video_info.height,
        cores,
        RAM_LIMIT_MB,
        Some(parallel_workers),
    );
    let chunk_duration = duration_seconds / chunk_count as f64;

    // РџРѕС‚РѕРєРё РЅР° РѕРґРёРЅ С‡Р°РЅРє Рё `lp` РґР»СЏ SVT-AV1 СЃС‡РёС‚Р°СЋС‚СЃСЏ РћРў chunk_count, Р° РЅРµ РѕС‚ 1.
    // РРЅР°С‡Рµ РєР°Р¶РґС‹Р№ РёР· N РїСЂРѕС†РµСЃСЃРѕРІ Р·Р°Р±РёСЂР°РµС‚ РІСЃРµ СЏРґСЂР° => СЃСѓРјРјР°СЂРЅРѕ N x oversubscription,
    // С‡С‚Рѕ СЃСЉРµРґР°РµС‚ РІС‹РёРіСЂС‹С€ РѕС‚ РїР°СЂР°Р»Р»РµР»СЊРЅРѕСЃС‚Рё (x264/x265/SVT-AV1 РїРѕ СѓРјРѕР»С‡Р°РЅРёСЋ = РІСЃРµ СЏРґСЂР°).
    let threads_per_chunk = (cores / chunk_count).max(1);
    let chunk_lp = crate::av1::av1_lp_for_workers(chunk_count);

    info!(
        "Parallel compress: {} chunks, {:.1}s each, {} threads/chunk, codec={}, crf={}, resolution={}x{}",
        chunk_count, chunk_duration, threads_per_chunk, codec, crf_value, video_info.width, video_info.height
    );

    if let Some(ref cb) = progress_cb {
        cb(0, format!("Preparing {} chunks...", chunk_count));
    }

    let temp_dir = std::env::temp_dir();
    let pid = std::process::id();
    let mut specs: Vec<SegmentSpec> = Vec::new();

    for i in 0..chunk_count {
        let start = (i as f64) * chunk_duration;
        let dur = if i == chunk_count - 1 {
            duration_seconds - start
        } else {
            chunk_duration
        };
        if dur <= 0.0 {
            continue;
        }
        let out = temp_dir.join(format!("parallel_seg_{}_{}.mkv", pid, i));
        specs.push(SegmentSpec {
            start_time: start,
            duration: dur,
            output_path: out.to_string_lossy().to_string(),
        });
    }

    if specs.is_empty() {
        return RunResult {
            success: false,
            message: "No segments generated for parallel compress".to_string(),
        };
    }

    let total_chunks = specs.len();
    let chunk_done: Vec<Arc<AtomicBool>> = (0..total_chunks).map(|_| Arc::new(AtomicBool::new(false))).collect();
    let chunk_pcts: Vec<Arc<AtomicI32>> = (0..total_chunks).map(|_| Arc::new(AtomicI32::new(0))).collect();
    let last_reported_pct = Arc::new(AtomicI32::new(0));

    let x264_parallel_params = "ref=2:rc-lookahead=15:bframes=2";

    // Р Р°Р·Р±РёРІР°РµРј ffmpeg-Р°СЂРіСѓРјРµРЅС‚С‹ Рё РѕР±С‰РёР№ callback РЅР° С…РµР»РїРµСЂС‹: С‚РµР»Рѕ РїРѕС‚РѕРєР° РЅРµ РґРѕР»Р¶РЅРѕ
    // СЃРѕРґРµСЂР¶Р°С‚СЊ РЅРё РїРѕСЃС‚СЂРѕРµРЅРёСЏ Р°СЂРіСѓРјРµРЅС‚РѕРІ, РЅРё СЂР°СЃС‡С‘С‚Р° РїСЂРѕРіСЂРµСЃСЃР° вЂ” РёРЅР°С‡Рµ РµРіРѕ РЅРµР»СЊР·СЏ
    // РїСЂРѕС‡РёС‚Р°С‚СЊ С†РµР»РёРєРѕРј (РїСЂР°РІРёР»Рѕ В«С„СѓРЅРєС†РёРё < 50-80 СЃС‚СЂРѕРєВ»).
    let base_args = ChunkEncodeArgs::new(
        input_path, codec, crf_value, preset_value, use_hardware,
        video_info, video_type, Some(chunk_lp), threads_per_chunk, &x264_parallel_params,
    );

    let results: Vec<Result<(), String>> = std::thread::scope(|s| {
        let mut handles = Vec::new();
        for i in 0..specs.len() {
            let spec = &specs[i];
            let args = base_args.clone();
            let cb = progress_cb.clone();
            let chunk_dur = spec.duration;
            let chunk_done_i = chunk_done[i].clone();
            let chunk_pcts_i = chunk_pcts[i].clone();
            let last_ref = last_reported_pct.clone();
            let chunk_done_all = chunk_done.clone();
            let chunk_pcts_all = chunk_pcts.clone();
            let total = total_chunks;
            let cancel = cancel_flag.clone();
            let cpid = child_pid.as_ref().map(|t| t.fork());

            handles.push(s.spawn(move || {
                let chunk_cb = make_chunk_progress_callback(
                    i, cb, chunk_done_i, chunk_pcts_i, last_ref, chunk_done_all, chunk_pcts_all, total,
                );

                let result = encode_chunk_with_progress(
                    &args.input,
                    &spec.output_path,
                    spec.start_time,
                    chunk_dur,
                    &args.codec,
                    args.crf,
                    &args.preset,
                    args.use_hardware,
                    &args.video_info,
                    &args.video_type,
                    false,
                    cancel,
                    cpid,
                    args.svtav1_lp,
                    ChunkEncodeOptions {
                        progress_cb: chunk_cb,
                        duration_seconds: Some(chunk_dur),
                        x264_extra_params: Some(args.x264_extra_params.as_str()),
                        threads: Some(args.threads),
                    },
                );
                if result.success {
                    info!("Chunk {}/{} completed successfully", i + 1, total_chunks);
                    Ok(())
                } else {
                    error!("Chunk {} failed: {}", i, result.message);
                    Err(result.message)
                }
            }));
        }

        let mut out_res = Vec::new();
        for h in handles {
            match h.join() {
                Ok(r) => out_res.push(r),
                Err(e) => {
                    let msg = if let Some(s) = e.downcast_ref::<&str>() {
                        s.to_string()
                    } else if let Some(s) = e.downcast_ref::<String>() {
                        s.clone()
                    } else {
                        "segment panicked".to_string()
                    };
                    error!("Chunk thread panicked: {}", msg);
                    out_res.push(Err(msg));
                }
            }
        }
        out_res
    });

    let failures: Vec<String> = results.into_iter().filter_map(|r| r.err()).collect();
    if !failures.is_empty() {
        cleanup_temp_files(&specs);
        return RunResult {
            success: false,
            message: format!("Parallel encode segments failed:\n{}", failures.join("\n")),
        };
    }

    if let Some(ref cb) = progress_cb {
        cb(82, "Concatenating video segments...".to_string());
    }

    let concat_list_path = temp_dir.join(format!("parallel_concat_{}.txt", pid));
    let list_content: String = specs
        .iter()
        .map(|s| format!("file '{}'", s.output_path.replace('\\', "/")))
        .collect::<Vec<_>>()
        .join("\n");
    if let Err(e) = std::fs::write(&concat_list_path, list_content) {
        cleanup_temp_files(&specs);
        return RunResult {
            success: false,
            message: format!("Failed to write concat list: {}", e),
        };
    }

    let temp_video_only = temp_dir.join(format!("parallel_video_only_{}.mkv", pid));
    let concat_cmd = vec![
        "ffmpeg".to_string(),
        "-y".to_string(),
        "-f".to_string(),
        "concat".to_string(),
        "-safe".to_string(),
        "0".to_string(),
        "-i".to_string(),
        concat_list_path.to_string_lossy().to_string(),
        "-c".to_string(),
        "copy".to_string(),
        temp_video_only.to_string_lossy().to_string(),
    ];
    let concat_res = run_command_simple(&concat_cmd, cancel_flag.clone(), child_pid.clone());
    if let Err(e) = std::fs::remove_file(&concat_list_path) {
        warn!("Failed to remove concat list: {}", e);
    }

    if !concat_res.success {
        cleanup_temp_files(&specs);
        let _ = std::fs::remove_file(&temp_video_only);
        return RunResult {
            success: false,
            message: format!("Video concat failed: {}", concat_res.message),
        };
    }

    if let Some(ref cb) = progress_cb {
        cb(90, "Muxing audio and subtitles...".to_string());
    }

    let mux_cmd = build_mux_command(
        &temp_video_only.to_string_lossy(),
        input_path,
        output_path,
        output_format,
        codec,
        crf_value,
        video_info.has_subtitles,
        &video_info.subtitle_codecs,
    );
    let mux_res = run_command_simple(&mux_cmd, cancel_flag.clone(), child_pid.clone());

    cleanup_temp_files(&specs);
    if let Err(e) = std::fs::remove_file(&temp_video_only) {
        warn!("Failed to remove temp video-only file: {}", e);
    }

    if !mux_res.success {
        return RunResult {
            success: false,
            message: format!("Mux failed: {}", mux_res.message),
        };
    }

    if let Some(ref cb) = progress_cb {
        cb(100, "Parallel compress completed".to_string());
    }

    info!("Parallel compress completed: {}", output_path);
    RunResult {
        success: true,
        message: "Parallel compress completed".to_string(),
    }
}
