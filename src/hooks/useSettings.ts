import { useState, useCallback, useEffect } from 'react';
import { tauriInvoke } from './useTauri';
import { Settings } from '../types';

const DEFAULT_SETTINGS: Settings = {
  ffmpeg_path: './',
  vmaf_subsample: 24,
  chunk_count: 5,
  chunk_duration: 2,
  locale: 'en',
  skip_min_diff_enabled: true,
  skip_min_diff_percent: 5.0,
  skip_min_crf_enabled: true,
  skip_min_crf_value: 18.0,
  vmaf_ignore_noise: false,
};

export function useSettings() {
  const [settings, setSettings] = useState<Settings>(DEFAULT_SETTINGS);
  const [ffmpegExists, setFfmpegExists] = useState(false);

  const loadSettings = useCallback(async () => {
    try {
      const s = await tauriInvoke<Settings>('load_settings_cmd');
      console.log('[useSettings] Loaded:', s);
      setSettings(s);
    } catch (e) {
      console.error('[useSettings] load_settings error:', e);
    }
  }, []);

  const saveSettings = useCallback(async (newSettings: Settings) => {
    try {
      console.log('[useSettings] Saving:', newSettings);
      await tauriInvoke('save_settings_cmd', { settings: newSettings });
      setSettings(newSettings);
    } catch (e) {
      console.error('[useSettings] save_settings error:', e);
    }
  }, []);

  const checkFfmpeg = useCallback(async () => {
    try {
      const exists = await tauriInvoke<boolean>('check_ffmpeg_cmd');
      console.log('[useSettings] FFmpeg exists:', exists);
      setFfmpegExists(exists);
    } catch (e) {
      console.error('[useSettings] check_ffmpeg error:', e);
    }
  }, []);

  const downloadFfmpeg = useCallback(async () => {
    try {
      console.log('[useSettings] Downloading FFmpeg...');
      await tauriInvoke('download_ffmpeg_cmd');
      await checkFfmpeg();
    } catch (e) {
      console.error('[useSettings] download_ffmpeg error:', e);
    }
  }, [checkFfmpeg]);

  useEffect(() => {
    loadSettings();
    checkFfmpeg();
  }, [loadSettings, checkFfmpeg]);

  return { settings, ffmpegExists, loadSettings, saveSettings, checkFfmpeg, downloadFfmpeg };
}
