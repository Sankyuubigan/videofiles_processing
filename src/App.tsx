import { useState, useEffect, useCallback } from 'react';
import { listen } from '@tauri-apps/api/event';
import { open } from '@tauri-apps/plugin-dialog';
import { TabId, OperationTab, FileEntry } from './types';
import { CODECS, OUTPUT_FORMATS } from './constants/codecs';
import { useFileQueue } from './hooks/useFileQueue';
import { useSettings } from './hooks/useSettings';
import { useDragDrop } from './hooks/useDragDrop';
import { tauriInvoke } from './hooks/useTauri';
import { t, setLocale, Locale } from './i18n';
import EditorTab from './components/tabs/EditorTab';
import CompareTab from './components/tabs/CompareTab';
import LogsTab from './components/tabs/LogsTab';
import SettingsTab from './components/tabs/SettingsTab';
import HelpTab from './components/tabs/HelpTab';
import './styles.css';

function App() {
  const [activeTab, setActiveTab] = useState<TabId>('editor');
  const [logs, setLogs] = useState<string[]>([]);
  const [progress, setProgress] = useState({ percent: 0, message: 'Ready' });
  const [isProcessing, setIsProcessing] = useState(false);
  const [isPaused, setIsPaused] = useState(false);

  // Editor state
  const [selectedFormat, setSelectedFormat] = useState('mp4');
  const [selectedCodec, setSelectedCodec] = useState('libx264');
  const [useHardware, setUseHardware] = useState(false);
  const [selectedPreset, setSelectedPreset] = useState('slow');
  const [crfValue, setCrfValue] = useState(22);
  const [autoCrf, setAutoCrf] = useState(true);
  const [targetVmaf, setTargetVmaf] = useState(90.0);
  const [targetSsimulacra2, setTargetSsimulacra2] = useState(77.0);
  const [forceVfrFix, setForceVfrFix] = useState(false);
  const [operationTab, setOperationTab] = useState<OperationTab>('compress');

  const { files, setFiles, selectedIndex, setSelectedIndex, addFiles, removeFile, refreshFiles, clearQueue } = useFileQueue();
  const { settings, ffmpegExists, saveSettings, checkFfmpeg, downloadFfmpeg } = useSettings();
  const [outputDir, setOutputDir] = useState<string | null>(null);

  // Sync locale from settings
  useEffect(() => {
    if (settings.locale) {
      setLocale(settings.locale as Locale);
    }
  }, [settings.locale]);

  // Load output dir on mount
  useEffect(() => {
    tauriInvoke<string | null>('get_output_dir').then(dir => {
      setOutputDir(dir || null);
    }).catch(() => {});
  }, []);

  const addLog = useCallback((msg: string) => {
    const now = new Date();
    const ts = `${String(now.getHours()).padStart(2,'0')}:${String(now.getMinutes()).padStart(2,'0')}:${String(now.getSeconds()).padStart(2,'0')}`;
    setLogs(prev => [...prev, `[${ts}] ${msg}`]);
  }, []);

  const handleFileDrop = useCallback((paths: string[], _position: { x: number; y: number }) => {
    addLog(`Dropped ${paths.length} file(s)`);
    addFiles(paths);
  }, [addFiles, addLog]);

  const { isDragOver } = useDragDrop({
    onDrop: handleFileDrop,
    enabled: activeTab === 'editor',
  });

  // Listen for events from backend
  useEffect(() => {
    const unlisteners: (() => void)[] = [];
    const setup = async () => {
      unlisteners.push(await listen<[number, string]>('compress-progress', (e) => {
        setProgress({ percent: e.payload[0], message: e.payload[1] });
      }));
      unlisteners.push(await listen<string>('log-message', (e) => {
        const now = new Date();
        const ts = `${String(now.getHours()).padStart(2,'0')}:${String(now.getMinutes()).padStart(2,'0')}:${String(now.getSeconds()).padStart(2,'0')}`;
        setLogs(prev => [...prev, `[${ts}] ${e.payload}`]);
      }));
      unlisteners.push(await listen('compress-finished', () => {
        setIsProcessing(false);
        setIsPaused(false);
        setProgress({ percent: 100, message: 'Done!' });
      }));
      unlisteners.push(await listen('batch-finished', () => {
        setIsProcessing(false);
        setIsPaused(false);
        setProgress({ percent: 100, message: 'Batch done!' });
        refreshFiles();
      }));
      unlisteners.push(await listen<[number, string]>('test-progress', (e) => {
        setProgress({ percent: e.payload[0], message: e.payload[1] });
      }));
      unlisteners.push(await listen<[number, number, number, string]>('batch-test-progress', (e) => {
        const [idx, total, filePercent, msg] = e.payload;
        const overall = total > 0 ? (idx + filePercent / 100) / total * 100 : filePercent;
        setProgress({ percent: Math.round(overall * 10) / 10, message: msg });
      }));
      unlisteners.push(await listen('batch-test-finished', () => {
        setProgress({ percent: 100, message: 'Batch test done!' });
      }));
      unlisteners.push(await listen<{ path: string; success: boolean }>('file-done', (e) => {
        if (e.payload.success) {
          setFiles(prev => prev.filter(f => f.path !== e.payload.path));
        }
      }));
      unlisteners.push(await listen<FileEntry>('file-entry-updated', (e) => {
        setFiles(prev => prev.map(f => f.path === e.payload.path ? e.payload : f));
      }));
    };
    setup();
    return () => { unlisteners.forEach(u => u()); };
  }, []);

  const handleSelectFiles = useCallback(async () => {
    const selected = await open({
      multiple: true,
      filters: [{ name: 'Video', extensions: ['mp4','avi','mkv','mov','webm'] }],
    });
    if (selected) {
      const paths = Array.isArray(selected) ? selected : [selected];
      addFiles(paths);
    }
  }, [addFiles]);

  const handleSelectOutputDir = useCallback(async () => {
    const dir = await open({ directory: true });
    if (dir) {
      await tauriInvoke('set_output_dir', { path: dir });
      setOutputDir(dir);
    }
  }, []);

  const handleStartCompress = useCallback(async () => {
    if (selectedIndex < 0 || selectedIndex >= files.length) return;
    const file = files[selectedIndex];
    if (!file) return;
    setIsProcessing(true);
    setProgress({ percent: 0, message: 'Starting...' });
    try {
      await tauriInvoke('start_compress', {
        path: file.path,
        outputFormat: selectedFormat,
        codec: selectedCodec,
        crfValue,
        presetValue: selectedPreset,
        forceVfrFix,
        useHardware,
        autoCrf,
        targetVmaf,
        targetSsimulacra2,
      });
    } catch (e: any) {
      addLog(`Error: ${e}`);
      setIsProcessing(false);
    }
  }, [selectedIndex, files, selectedFormat, selectedCodec, crfValue, selectedPreset, forceVfrFix, useHardware, autoCrf, targetVmaf, targetSsimulacra2, addLog]);

  const handleBatchCompress = useCallback(async () => {
    if (files.length === 0) return;
    setIsProcessing(true);
    setProgress({ percent: 0, message: 'Starting batch...' });
    try {
      await tauriInvoke('start_batch_compress', {
        outputFormat: selectedFormat,
        codec: selectedCodec,
        crfValue,
        presetValue: selectedPreset,
        forceVfrFix,
        useHardware,
        autoCrf,
        targetVmaf,
        targetSsimulacra2,
      });
    } catch (e: any) {
      addLog(`Batch error: ${e}`);
      setIsProcessing(false);
    }
  }, [files.length, selectedFormat, selectedCodec, crfValue, selectedPreset, forceVfrFix, useHardware, autoCrf, targetVmaf, targetSsimulacra2, addLog]);

  const handleCancel = useCallback(async () => {
    try {
      await tauriInvoke('cancel_processing');
      setIsProcessing(false);
      setIsPaused(false);
      setProgress({ percent: 0, message: 'Cancelled' });
    } catch (e) {
      console.error('cancel error:', e);
    }
  }, []);

  const handlePause = useCallback(async () => {
    try {
      await tauriInvoke('pause_processing');
      setIsPaused(true);
      setProgress(prev => ({ ...prev, message: 'Paused' }));
    } catch (e) {
      console.error('pause error:', e);
    }
  }, []);

  const handleResume = useCallback(async () => {
    try {
      await tauriInvoke('resume_processing');
      setIsPaused(false);
    } catch (e) {
      console.error('resume error:', e);
    }
  }, []);

  const handleTestFile = useCallback(async (path: string, forceMetric?: string) => {
    if (!path) return;
    const fileIndex = files.findIndex(f => f.path === path);
    if (fileIndex < 0) return;
    setIsProcessing(true);
    try {
      const result = await tauriInvoke<any>('run_chunk_test_cmd', {
        path,
        codec: selectedCodec,
        crfValue,
        presetValue: selectedPreset,
        useHardware,
        autoCrf: forceMetric ? false : autoCrf,
        targetVmaf,
        targetSsimulacra2,
        forceVfrFix,
        forceMetric: forceMetric || null,
      });
      setFiles(prev => prev.map((f) => f.path === path ? { ...f, test_result: result } : f));
      setProgress({ percent: 100, message: 'Done!' });
    } catch (e: any) {
      addLog(`Test error: ${e}`);
      setProgress({ percent: 0, message: 'Error' });
    }
    setIsProcessing(false);
  }, [files, selectedCodec, crfValue, selectedPreset, useHardware, autoCrf, targetVmaf, targetSsimulacra2, forceVfrFix, addLog, setFiles]);

  const handleBatchTest = useCallback(async () => {
    if (files.length === 0) return;
    setIsProcessing(true);
    try {
      await tauriInvoke('run_batch_test', {
        codec: selectedCodec,
        crfValue,
        presetValue: selectedPreset,
        useHardware,
        autoCrf,
        targetVmaf,
        targetSsimulacra2,
        forceVfrFix,
      });
      setProgress({ percent: 100, message: 'Batch test done!' });
    } catch (e: any) {
      addLog(`Batch test error: ${e}`);
      setProgress({ percent: 0, message: 'Error' });
    }
    setIsProcessing(false);
  }, [files.length, selectedCodec, crfValue, selectedPreset, useHardware, autoCrf, targetVmaf, targetSsimulacra2, forceVfrFix, addLog]);

  const handleVideoTypeChange = useCallback(async (path: string, videoType: string) => {
    const file = files.find(f => f.path === path);
    if (!file) return;
    try {
      await tauriInvoke('set_video_type', { path: file.path, videoType });
      setFiles(prev => prev.map((f) =>
        f.path === path && f.info ? { ...f, info: { ...f.info, video_type: videoType as any } } : f
      ));
      addLog(`Video type set to ${videoType} for ${file.path}`);
    } catch (e: any) {
      addLog(`Set video type error: ${e}`);
    }
  }, [files, setFiles, addLog]);

  const handleTrim = useCallback(async (filePath: string, seconds: number, fromStart: boolean) => {
    setIsProcessing(true);
    try {
      await tauriInvoke('trim_video_cmd', { filePath, seconds, fromStart });
    } catch (e: any) {
      addLog(`Trim error: ${e}`);
      setIsProcessing(false);
    }
  }, [addLog]);

  const handleNormalize = useCallback(async (filePath: string) => {
    setIsProcessing(true);
    try {
      await tauriInvoke('normalize_audio_cmd', { filePath });
    } catch (e: any) {
      addLog(`Normalize error: ${e}`);
      setIsProcessing(false);
    }
  }, [addLog]);

  const handleExtractFrame = useCallback(async (filePath: string, frameNumber: number) => {
    try {
      const result = await tauriInvoke<string>('extract_frame_cmd', { filePath, frameNumber });
      addLog(`Frame extracted: ${result}`);
    } catch (e: any) {
      addLog(`Extract frame error: ${e}`);
    }
  }, [addLog]);

  // Update codec when format changes
  const handleFormatChange = useCallback((fmt: string) => {
    setSelectedFormat(fmt);
    const formatInfo = OUTPUT_FORMATS[fmt];
    if (formatInfo && !formatInfo.compatibleCodecs.includes(selectedCodec)) {
      setSelectedCodec(formatInfo.defaultCodec);
      const codecInfo = CODECS[formatInfo.defaultCodec];
      if (codecInfo) {
        setSelectedPreset(codecInfo.presetDefault);
        setCrfValue(codecInfo.crfDefault);
      }
    }
  }, [selectedCodec]);

  // Update CRF range when codec changes
  const handleCodecChange = useCallback((codec: string) => {
    setSelectedCodec(codec);
    const info = CODECS[codec];
    if (info) {
      setSelectedPreset(info.presetDefault);
      if (crfValue < info.crfMin || crfValue > info.crfMax) {
        setCrfValue(info.crfDefault);
      }
    }
  }, [crfValue]);

  // Вместо unmount для вкладок используем display: none / flex, чтобы не терять состояние
  return (
    <div className="app">
      <div className="tabs-bar">
        {(['editor','compare','logs','settings','help'] as TabId[]).map(tab => (
          <button
            key={tab}
            className={`tab-btn ${activeTab === tab ? 'active' : ''}`}
            onClick={() => setActiveTab(tab)}
          >
            {tab === 'editor' && t('tab.editor')}
            {tab === 'compare' && t('tab.compare')}
            {tab === 'logs' && t('tab.logs')}
            {tab === 'settings' && t('tab.settings')}
            {tab === 'help' && t('tab.help')}
          </button>
        ))}
      </div>
      <div className="tab-content">
        <div style={{ display: activeTab === 'editor' ? 'flex' : 'none', flexDirection: 'column', height: '100%' }}>
          <EditorTab
            files={files}
            selectedIndex={selectedIndex}
            setSelectedIndex={setSelectedIndex}
            isDragOver={isDragOver}
            onSelectFiles={handleSelectFiles}
            onSelectOutputDir={handleSelectOutputDir}
            onRemoveFile={removeFile}
            onTestFile={handleTestFile}
            onVideoTypeChange={handleVideoTypeChange}
            operationTab={operationTab}
            setOperationTab={setOperationTab}
            selectedFormat={selectedFormat}
            onFormatChange={handleFormatChange}
            selectedCodec={selectedCodec}
            onCodecChange={handleCodecChange}
            useHardware={useHardware}
            setUseHardware={setUseHardware}
            selectedPreset={selectedPreset}
            setSelectedPreset={setSelectedPreset}
            crfValue={crfValue}
            setCrfValue={setCrfValue}
            autoCrf={autoCrf}
            setAutoCrf={setAutoCrf}
            targetVmaf={targetVmaf}
            setTargetVmaf={setTargetVmaf}
            targetSsimulacra2={targetSsimulacra2}
            setTargetSsimulacra2={setTargetSsimulacra2}
            forceVfrFix={forceVfrFix}
            setForceVfrFix={setForceVfrFix}
            progress={progress}
            isProcessing={isProcessing}
            isPaused={isPaused}
            onStartCompress={handleStartCompress}
            onBatchCompress={handleBatchCompress}
            onBatchTest={handleBatchTest}
            onCancel={handleCancel}
            onPause={handlePause}
            onResume={handleResume}
            onTrim={handleTrim}
            onNormalize={handleNormalize}
            onExtractFrame={handleExtractFrame}
            filesCount={files.length}
            outputDir={outputDir}
            onClearTable={clearQueue}
          />
        </div>
        <div style={{ display: activeTab === 'compare' ? 'flex' : 'none', flexDirection: 'column', height: '100%' }}>
          <CompareTab addLog={addLog} isActive={activeTab === 'compare'} />
        </div>
        <div style={{ display: activeTab === 'logs' ? 'flex' : 'none', flexDirection: 'column', height: '100%' }}>
          <LogsTab logs={logs} />
        </div>
        <div style={{ display: activeTab === 'settings' ? 'flex' : 'none', flexDirection: 'column', height: '100%' }}>
          <SettingsTab
            settings={settings}
            ffmpegExists={ffmpegExists}
            onSave={saveSettings}
            onCheckFfmpeg={checkFfmpeg}
            onDownloadFfmpeg={downloadFfmpeg}
          />
        </div>
        <div style={{ display: activeTab === 'help' ? 'flex' : 'none', flexDirection: 'column', height: '100%' }}>
          <HelpTab />
        </div>
      </div>
    </div>
  );
}

export default App;