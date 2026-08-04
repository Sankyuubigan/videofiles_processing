import { t } from '../../i18n';

interface Props {
  progress: { percent: number; message: string };
  isProcessing: boolean;
  isPaused: boolean;
  hasFiles: boolean;
  currentFile: string | null;
  onStart: () => void;
  onBatchTest: () => void;
  onBatchCompress: () => void;
  onCancel: () => void;
  onPause: () => void;
  onResume: () => void;
}

function fileBaseName(path: string): string {
  return path.split(/[\\/]/).pop() || path;
}

export default function ProcessControl({ progress, isProcessing, isPaused, hasFiles, currentFile, onStart, onBatchTest, onBatchCompress, onCancel, onPause, onResume }: Props) {
  return (
    <div className="process-control">
      <button className="btn-start" disabled={!hasFiles || isProcessing} onClick={onStart}>
        {t('process.start')}
      </button>
      <button className="btn-test-all" disabled={!hasFiles || isProcessing} onClick={onBatchTest}>
        {t('process.batch_test')}
      </button>
      <button className="btn-test-all" disabled={!hasFiles || isProcessing} onClick={onBatchCompress} style={{ marginLeft: 4 }}>
        {t('process.batch_compress')}
      </button>
      {isProcessing && !isPaused && (
        <button className="btn-pause" onClick={onPause}>{t('process.pause')}</button>
      )}
      {isProcessing && isPaused && (
        <button className="btn-resume" onClick={onResume}>{t('process.resume')}</button>
      )}
      {isProcessing && (
        <button className="btn-cancel" onClick={onCancel}>{t('process.cancel')}</button>
      )}
      <div className="progress-bar-wrapper">
        <div className="progress-bar">
          <div className={`progress-bar-fill ${isPaused ? 'paused' : ''}`} style={{ width: `${progress.percent}%` }} />
        </div>
        {currentFile && (
          <div className="progress-file" title={currentFile}>
            {t('process.file')} {fileBaseName(currentFile)}
          </div>
        )}
        <div className="progress-label">{isPaused ? t('process.paused') : progress.message}</div>
      </div>
    </div>
  );
}
