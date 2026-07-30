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
  onTestFile: (i: number) => void;
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
}

export default function EditorTab(props: Props) {
  return (
    <div className="editor-layout">
      <div className="file-section">
        <div className="file-header">
          <label>{t('editor.select_files')}</label>
          <button className="action-btn" onClick={props.onSelectFiles}>{t('editor.select_btn')}</button>
          <button className="action-btn" onClick={props.onSelectOutputDir}>{t('editor.output_dir')}</button>
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
