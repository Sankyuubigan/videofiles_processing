//! SVT-AV1 pipeline (Модуль 4 доки): единый источник правды для параметров AV1.
//! Импорт — только через эту дверь (`crate::av1::*`), не через `params::`.

mod params;

#[allow(unused_imports)]
pub use params::{params_for, svtav1_args, Av1Params, AV1_PIX_FMT, av1_parallel_worker_cap, av1_lp_for_workers, cap_parallel_workers};