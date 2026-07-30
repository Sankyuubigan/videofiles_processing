import { useState, useEffect, useCallback } from 'react';
import { open } from '@tauri-apps/plugin-dialog';
import { Settings } from '../../types';
import { t, setLocale, Locale } from '../../i18n';

interface Props {
  settings: Settings;
  ffmpegExists: boolean;
  onSave: (s: Settings) => void;
  onCheckFfmpeg: () => void;
  onDownloadFfmpeg: () => void;
}

export default function SettingsTab({ settings, ffmpegExists, onSave, onDownloadFfmpeg }: Props) {
  const [localSettings, setLocalSettings] = useState<Settings>({ ...settings });

  useEffect(() => {
    setLocalSettings({ ...settings });
  }, [settings]);

  const autoSave = useCallback((updated: Settings) => {
    setLocalSettings(updated);
    setLocale(updated.locale as Locale);
    onSave(updated);
  }, [onSave]);

  const handleBrowseFfmpeg = async () => {
    const dir = await open({ directory: true });
    if (dir) {
      autoSave({ ...localSettings, ffmpeg_path: dir as string });
    }
  };

  return (
    <div className="settings-container">
      <div className="settings-group">
        <h3>{t('settings.locale')}</h3>
        <div className="settings-row">
          <label>{t('settings.locale')}</label>
          <select
            value={localSettings.locale}
            onChange={(e) => autoSave({ ...localSettings, locale: e.target.value })}
          >
            <option value="en">{t('settings.locale_en')}</option>
            <option value="ru">{t('settings.locale_ru')}</option>
          </select>
        </div>
      </div>

      <div className="settings-group">
        <h3>{t('settings.ffmpeg')}</h3>
        <div className="settings-row">
          <label>{t('settings.ffmpeg_path')}</label>
          <input
            type="text"
            value={localSettings.ffmpeg_path}
            onChange={(e) => autoSave({ ...localSettings, ffmpeg_path: e.target.value })}
            placeholder="./ (program folder)"
          />
          <button className="btn-browse" onClick={handleBrowseFfmpeg}>Browse</button>
          <span className={`status ${ffmpegExists ? 'ok' : 'error'}`}>
            {ffmpegExists ? t('settings.ffmpeg_found') : t('settings.ffmpeg_not_found')}
          </span>
        </div>
        {!ffmpegExists && (
          <div className="settings-row">
            <button className="btn-download" onClick={onDownloadFfmpeg}>{t('settings.download_ffmpeg')}</button>
          </div>
        )}
      </div>

      <div className="settings-group">
        <h3>{t('settings.compression')}</h3>
        <div className="settings-row">
          <label>{t('settings.vmaf_subsample')}</label>
          <select
            value={localSettings.vmaf_subsample}
            onChange={(e) => autoSave({ ...localSettings, vmaf_subsample: parseInt(e.target.value) })}
          >
            <option value={1}>Every frame (very slow)</option>
            <option value={2}>Every 2nd frame</option>
            <option value={5}>Every 5th frame</option>
            <option value={10}>Every 10th frame (default)</option>
            <option value={24}>Every 24th frame (very fast)</option>
          </select>
        </div>
        <div className="settings-row">
          <label>{t('settings.chunk_count')}</label>
          <select
            value={localSettings.chunk_count}
            onChange={(e) => autoSave({ ...localSettings, chunk_count: parseInt(e.target.value) })}
          >
            <option value={1}>1 chunk</option>
            <option value={2}>2 chunks</option>
            <option value={3}>3 chunks</option>
            <option value={4}>4 chunks</option>
            <option value={5}>5 chunks (default)</option>
          </select>
        </div>
        <div className="settings-row">
          <label>{t('settings.chunk_duration')}</label>
          <select
            value={localSettings.chunk_duration}
            onChange={(e) => autoSave({ ...localSettings, chunk_duration: parseInt(e.target.value) })}
          >
            <option value={2}>2 seconds</option>
            <option value={5}>5 seconds</option>
            <option value={10}>10 seconds</option>
            <option value={15}>15 seconds</option>
            <option value={20}>20 seconds</option>
          </select>
        </div>
      </div>

      <div className="settings-group">
        <h3>{t('settings.auto_skip')}</h3>
        <div className="settings-row">
          <div className="checkbox-row">
            <input
              type="checkbox"
              id="skipDiff"
              checked={localSettings.skip_min_diff_enabled}
              onChange={(e) => autoSave({ ...localSettings, skip_min_diff_enabled: e.target.checked })}
            />
            <label htmlFor="skipDiff">{t('settings.skip_min_diff')}</label>
          </div>
          {localSettings.skip_min_diff_enabled && (
            <div className="value-input">
              <input
                type="number"
                min={1}
                max={50}
                step={0.5}
                value={localSettings.skip_min_diff_percent}
                onChange={(e) => autoSave({ ...localSettings, skip_min_diff_percent: parseFloat(e.target.value) || 5.0 })}
              />
              <span>%</span>
            </div>
          )}
        </div>
        <div className="settings-row">
          <div className="checkbox-row">
            <input
              type="checkbox"
              id="skipCrf"
              checked={localSettings.skip_min_crf_enabled}
              onChange={(e) => autoSave({ ...localSettings, skip_min_crf_enabled: e.target.checked })}
            />
            <label htmlFor="skipCrf">{t('settings.skip_min_crf')}</label>
          </div>
          {localSettings.skip_min_crf_enabled && (
            <div className="value-input">
              <input
                type="number"
                min={0}
                max={51}
                step={1}
                value={localSettings.skip_min_crf_value}
                onChange={(e) => autoSave({ ...localSettings, skip_min_crf_value: parseFloat(e.target.value) || 18.0 })}
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
