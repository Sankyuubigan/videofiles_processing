/// Converts an FPS value to a (fpsnum, fpsden) pair for AssumeFPS.
pub fn fps_to_rational(fps: f64) -> (u64, u64) {
    if fps <= 0.0 {
        return (25, 1);
    }
    const COMMON: [(u64, u64, f64); 5] = [
        (24000, 1001, 23.976),
        (30000, 1001, 29.97),
        (60000, 1001, 59.94),
        (25, 1, 25.0),
        (30, 1, 30.0),
    ];
    for (num, den, rate) in COMMON {
        if (fps - rate).abs() < 0.05 {
            return (num, den);
        }
    }
    let rounded = fps.round();
    if (fps - rounded).abs() < 0.05 && rounded > 0.0 {
        return (rounded as u64, 1);
    }
    (fps.round() as u64, 1)
}

fn py_path(path: &std::path::Path) -> String {
    path.to_string_lossy().replace('\\', "/")
}

/// Maps measured grain (sigma, derived from median YDIF) to KNLMeansCL strength
/// `h` for animation. Keeps `h` in the light 0.4-0.6 band recommended for anime
/// (docs/task new settings.md): enough to clean studio BD grain, weak enough to
/// preserve lineart.
fn knlmeans_h(sigma: f64) -> f64 {
    (sigma * 0.1).clamp(0.4, 0.6)
}

use crate::vapoursynth::denoise::DenoiseFilter;

/// Source filter used to read the input frames.
/// `ffms2` is fine for the single-pipe path; `lsmas` (LWLibavSource) is used
/// for the segmented path because it does not write a sidecar index file, so
/// multiple instances can read the same source concurrently without contention.
#[derive(Debug, Clone, Copy)]
pub enum DenoiseSource {
    Ffms2,
    Lsmash,
}

impl DenoiseSource {
    /// Returns the full VapourSynth source-call for this input.
    /// ffms2 exposes `Source`; the L-SMASH Works plugin exposes `LWLibavSource`
    /// under the `lsmas` namespace (NOT `lsmash`).
    fn source_call(self, input_esc: &str) -> String {
        match self {
            DenoiseSource::Ffms2 => format!("core.ffms2.Source(r'{input_esc}')"),
            DenoiseSource::Lsmash => format!("core.lsmas.LWLibavSource(r'{input_esc}')"),
        }
    }
}

/// Generates a VapourSynth script that denoises the input at 8-bit depth.
/// Running BM3D at 16-bit made `sigma` ~1000x too small to do anything; at
/// 8-bit `sigma = YDIF` is meaningful. Output stays 8-bit and no `contrasharp`
/// is applied (which previously re-sharpened the grain back in).
///
/// The spatial denoiser is chosen per content type (see `DenoiseFilter`):
/// - BM3D (LiveAction / Rendered): `bm3dcuda` on GPU when the vsrepo plugin is
///   present (10-50x faster than CPU), CPU fallback via the `bm3d` plugin.
/// - KNLMeansCL (Animation): preserves lineart, BM3D can damage thin lines.
///   Falls back to the BM3D path if the `knlm` plugin is missing.
///
/// * `trim`  - optional `(first, last)` frame range for segmented processing.
/// * `temporal` - also apply a light `SMDegrain(tr=1)` temporal pass afterwards.
/// * `filter` - spatial denoiser selected by content type.
pub fn generate_denoise_vpy(
    input: &str,
    fps: f64,
    sigma: f64,
    source: DenoiseSource,
    trim: Option<(u64, u64)>,
    temporal: bool,
    filter: DenoiseFilter,
    vs_threads: usize,
) -> String {
    let (fps_num, fps_den) = fps_to_rational(fps);
    let scripts = py_path(&crate::vapoursynth::portable_scripts_dir());
    let fallback_scripts = py_path(&crate::vapoursynth::scripts_dir());
    let input_esc = input.replace('\\', "/");
    let source_call = source.source_call(&input_esc);

    let trim_block = match trim {
        Some((first, last)) => format!(
            "\nsrc = src.std.Trim(first={first}, last=min({last}, src.num_frames - 1))"
        ),
        None => String::new(),
    };

    let temporal_block = if temporal {
        // SMDegrain defaults to UHDhalf=True on UHD inputs, which requires the
        // native `mvuscale` plugin. If it is missing the whole vspipe dies with
        // `smdegrain_bis: UHDhalf=True requires the 'mvuscale' plugin`. Try to
        // load it (the wheel auto-registers it), otherwise fall back to a
        // full-res search via UHDhalf=False so denoise never hard-fails on 4K.
        "\nfrom smdegrain_bis import SMDegrain\n\
         try:\n\
         \x20   from smdegrain_bis import _ensure_mvuscale\n\
         \x20   _ensure_mvuscale(core)\n\
         except Exception:\n\
         \x20   pass\n\
         if hasattr(core, 'mvuscale'):\n\
         \x20   den = SMDegrain(den, tr=1, plane=4)\n\
         else:\n\
         \x20   den = SMDegrain(den, tr=1, plane=4, UHDhalf=False)\n"
            .to_string()
    } else {
        String::new()
    };

    let spatial_block = match filter {
        DenoiseFilter::Bm3d => {
            "if hasattr(core, 'bm3dcuda'):\n\
             \x20   den = core.resize.Bilinear(src, format=vs.YUV444PS)\n\
             \x20   den = core.bm3dcuda.BM3D(den, sigma=[SIGMA, SIGMA, SIGMA], radius=0)\n\
             \x20   den = core.resize.Bilinear(den, format=vs.YUV444P8)\n\
             else:\n\
             \x20   den = core.bm3d.Basic(src, sigma=[SIGMA, SIGMA, SIGMA], profile='np')\n"
                .to_string()
        }
        DenoiseFilter::Knlmeans => format!(
            "KNL = {knl:.2}\nif hasattr(core, 'knlm'):\n    den = core.knlm.KNLMeansCL(src, d=1, a=2, s=4, h=KNL)\nelse:\n    if hasattr(core, 'bm3dcuda'):\n        den = core.resize.Bilinear(src, format=vs.YUV444PS)\n        den = core.bm3dcuda.BM3D(den, sigma=[SIGMA, SIGMA, SIGMA], radius=0)\n        den = core.resize.Bilinear(den, format=vs.YUV444P8)\n    else:\n        den = core.bm3d.Basic(src, sigma=[SIGMA, SIGMA, SIGMA], profile='np')\n",
            knl = knlmeans_h(sigma),
        ),
    };

    format!(
        "import sys\n\
         import vapoursynth as vs\n\
         core = vs.core\n\
         core.num_threads = {vs_threads}\n\
         for d in [r'{scripts}', r'{fallback_scripts}']:\n\
         \x20   if d not in sys.path:\n\
         \x20       sys.path.insert(0, d)\n\
         \n\
         src = {source_call}\n\
         src = src.std.AssumeFPS(fpsnum={fps_num}, fpsden={fps_den}){trim_block}\n\
          if src.format.sample_type == vs.FLOAT:\n\
          \x20   src = core.resize.Point(src, format=vs.YUV420P8)\n\
          else:\n\
          \x20   src = core.fmtc.bitdepth(src, bits=8)\n\
          src = core.resize.Bilinear(src, format=vs.YUV444P8)\n\
          \n\
          SIGMA = {sigma:.2}\n\
          {spatial_block}\
          den = core.fmtc.bitdepth(den, bits=8)\n\
          den = core.resize.Bilinear(den, format=vs.YUV420P8){temporal_block}\
          out = core.fmtc.bitdepth(den, bits=8)\n\
          out.set_output()\n"
    )
}
