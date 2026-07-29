import { t } from '../../i18n';

interface Props {
  progress: { percent: number; message: string };
  isProcessing: boolean;
  hasFiles: boolean;
  onStart: () => void;
  onBatchTest: () => void;
  onBatchCompress: () => void;
  onCancel: () => void;
}

export default function ProcessControl({ progress, isProcessing, hasFiles, onStart, onBatchTest, onBatchCompress, onCancel }: Props) {
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
      {isProcessing && (
        <button className="btn-cancel" onClick={onCancel}>{t('process.cancel')}</button>
      )}
      <div className="progress-bar-wrapper">
        <div className="progress-bar">
          <div className="progress-bar-fill" style={{ width: `${progress.percent}%` }} />
        </div>
        <div className="progress-label">{progress.message}</div>
      </div>
    </div>
  );
}
