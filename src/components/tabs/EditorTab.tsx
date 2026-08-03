import { FileEntry, OperationTab } from '../../types';
import { t } from '../../i18n';
import FileTable from '../editor/FileTable';
import OperationTabs from '../editor/OperationTabs';
import ProcessControl from '../editor/ProcessControl';

interface Props {
  files: FileEntry[];
  selectedIndex: number;
  setSelectedIndex: (i: number) => void;
  isDragOver: boolean;
  onSelectFiles: () => void;
  onSelectOutputDir: () => void;
  onRemoveFile: (i: number) => void;
  onTestFile: (i: number, forceMetric?: string) => void;
  onNnTestFile: (i: number, metric: string) => void;
  onAllMetricsFile: (i: number) => void;
  onVideoTypeChange: (i: number, videoType: string) => void;
  operationTab: OperationTab;
  setOperationTab: (t: OperationTab) => void;
  selectedFormat: string;
  onFormatChange: (f: string) => void;
  selectedCodec: string;
  onCodecChange: (c: string) => void;
  useHardware: boolean;
  setUseHardware: (v: boolean) => void;
  selectedPreset: string;
  setSelectedPreset: (p: string) => void;
  crfValue: number;
  setCrfValue: (v: number) => void;
  autoCrf: boolean;
  setAutoCrf: (v: boolean) => void;
  targetVmaf: number;
  setTargetVmaf: (v: number) => void;
  targetSsimulacra2: number;
  setTargetSsimulacra2: (v: number) => void;
  forceVfrFix: boolean;
  setForceVfrFix: (v: boolean) => void;
  progress: { percent: number; message: string };
  isProcessing: boolean;
  isPaused: boolean;
  onStartCompress: () => void;
  onBatchCompress: () => void;
  onBatchTest: () => void;
  onCancel: () => void;
  onPause: () => void;
  onResume: () => void;
  onTrim: (path: string, seconds: number, fromStart: boolean) => void;
  onNormalize: (path: string) => void;
  onExtractFrame: (path: string, frame: number) => void;
  filesCount: number;
  outputDir: string | null;
  onClearTable: () => void;
}

export default function EditorTab(props: Props) {
  return (
    <div className="editor-layout">
      <div className="file-section">
        <div className="file-header">
          <label>{t('editor.select_files')}</label>
          <button className="action-btn" onClick={props.onSelectFiles}>{t('editor.select_btn')}</button>
          <button className="action-btn" onClick={props.onSelectOutputDir}>{t('editor.output_dir')}</button>
          {props.outputDir && (
            <span className="output-dir-label" title={props.outputDir}>
              {props.outputDir.length > 40 ? '...' + props.outputDir.slice(-37) : props.outputDir}
            </span>
          )}
          {!props.outputDir && (
            <span className="output-dir-label dim">{t('editor.output_dir_default')}</span>
          )}
          <button className="action-btn delete" onClick={props.onClearTable} disabled={props.filesCount === 0 || props.isProcessing}>
            {t('editor.clear_table')}
          </button>
          <span className="queue-info">{t('editor.in_queue', { count: props.filesCount })}</span>
        </div>
        <div
          className={`file-table-wrapper ${props.isDragOver ? 'drag-over' : ''}`}
        >
          <FileTable
            files={props.files}
            selectedIndex={props.selectedIndex}
            onSelect={props.setSelectedIndex}
            onRemove={props.onRemoveFile}
            onTest={props.onTestFile}
            onNnTest={props.onNnTestFile}
            onAllMetrics={props.onAllMetricsFile}
            onVideoTypeChange={props.onVideoTypeChange}
          />
        </div>
      </div>
      <OperationTabs
        activeTab={props.operationTab}
        setActiveTab={props.setOperationTab}
        selectedFormat={props.selectedFormat}
        onFormatChange={props.onFormatChange}
        selectedCodec={props.selectedCodec}
        onCodecChange={props.onCodecChange}
        useHardware={props.useHardware}
        setUseHardware={props.setUseHardware}
        selectedPreset={props.selectedPreset}
        setSelectedPreset={props.setSelectedPreset}
        crfValue={props.crfValue}
        setCrfValue={props.setCrfValue}
        autoCrf={props.autoCrf}
        setAutoCrf={props.setAutoCrf}
        targetVmaf={props.targetVmaf}
        setTargetVmaf={props.setTargetVmaf}
        targetSsimulacra2={props.targetSsimulacra2}
        setTargetSsimulacra2={props.setTargetSsimulacra2}
        forceVfrFix={props.forceVfrFix}
        setForceVfrFix={props.setForceVfrFix}
        selectedFile={props.files[props.selectedIndex] || null}
        onTrim={props.onTrim}
        onNormalize={props.onNormalize}
        onExtractFrame={props.onExtractFrame}
        isProcessing={props.isProcessing}
      />
      <ProcessControl
        progress={props.progress}
        isProcessing={props.isProcessing}
        isPaused={props.isPaused}
        hasFiles={props.filesCount > 0}
        onStart={props.onStartCompress}
        onBatchTest={props.onBatchTest}
        onBatchCompress={props.onBatchCompress}
        onCancel={props.onCancel}
        onPause={props.onPause}
        onResume={props.onResume}
      />
    </div>
  );
}