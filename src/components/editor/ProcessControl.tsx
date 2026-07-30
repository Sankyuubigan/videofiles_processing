import { t } from '../../i18n';

interface Props {
  progress: { percent: number; message: string };
  isProcessing: boolean;
  isPaused: boolean;
  hasFiles: boolean;
  onStart: () => void;
  onBatchTest: () => void;
  onBatchCompress: () => void;
  onCancel: () => void;
  onPause: () => void;
  onResume: () => void;
}

export default function ProcessControl({ progress, isProcessing, isPaused, hasFiles, onStart, onBatchTest, onBatchCompress, onCancel, onPause, onResume }: Props) {
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
        <div className="progress-label">{isPaused ? t('process.paused') : progress.message}</div>
      </div>
    </div>
  );
}
