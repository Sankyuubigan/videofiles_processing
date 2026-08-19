pub mod setup;
pub mod script;
pub mod runner;
pub mod denoise;

use std::path::{Path, PathBuf};

pub const VS_SUBDIR: &str = "vapoursynth";
pub const PORTABLE_DIR: &str = "vapoursynth-portable";
pub const INSTALLER_PS1: &str = "install-portable-vapoursynth.ps1";

pub fn exe_dir() -> PathBuf {
    match std::env::current_exe() {
        Ok(p) => p.parent().map(|p| p.to_path_buf()),
        Err(e) => {
            log::warn!("current_exe() failed in vapoursynth paths: {}", e);
            None
        }
    }
    .unwrap_or_else(|| std::env::current_dir().unwrap_or_default())
}

pub fn vs_root_dir() -> PathBuf {
    exe_dir().join(VS_SUBDIR)
}

pub fn portable_dir() -> PathBuf {
    vs_root_dir().join(PORTABLE_DIR)
}

pub fn scripts_dir() -> PathBuf {
    vs_root_dir().join("scripts")
}

pub fn installer_ps1_path() -> PathBuf {
    vs_root_dir().join(INSTALLER_PS1)
}

pub fn is_installed() -> bool {
    vspipe_bat_path().exists()
}

pub fn vspipe_bat_path() -> PathBuf {
    portable_dir().join("vspipe.bat")
}

pub fn python_exe_path() -> PathBuf {
    portable_dir().join("python.exe")
}

pub fn portable_scripts_dir() -> PathBuf {
    portable_dir().join("Scripts")
}

pub fn vsrepo_exe_path() -> PathBuf {
    portable_scripts_dir().join("vsrepo.exe")
}

pub fn vsrepo_dir() -> PathBuf {
    portable_dir().join("Lib").join("site-packages").join("vsrepo")
}

pub fn vsrepo_7z_path() -> PathBuf {
    vsrepo_dir().join("7z.exe")
}

pub fn ensure_dir(dir: &Path) -> Result<(), String> {
    std::fs::create_dir_all(dir)
        .map_err(|e| format!("Failed to create directory {:?}: {}", dir, e))
}
