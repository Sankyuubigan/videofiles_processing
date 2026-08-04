import { convertFileSrc } from '@tauri-apps/api/core';
import { t } from '../../i18n';
import { PreviewState } from '../../types';

interface Props {
  preview: PreviewState;
  onClose: () => void;
}

function fileBaseName(path: string): string {
  return path.split(/[\\/]/).pop() || path;
}

export default function PreviewModal({ preview, onClose }: Props) {
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <span className="modal-title">{t('preview.title')}</span>
          <span className="modal-file" title={preview.filePath}>{fileBaseName(preview.filePath)}</span>
          <button className="modal-close" onClick={onClose}>{t('preview.close')}</button>
        </div>
        <div className="modal-body">
          {preview.error ? (
            <div className="preview-error">{preview.error}</div>
          ) : preview.gifPath ? (
            <img
              className="preview-gif"
              src={convertFileSrc(preview.gifPath)}
              alt="Video preview"
            />
          ) : (
            <div className="preview-loading">
              <span className="preview-spinner" />
              {t('preview.generating')}
            </div>
          )}
        </div>
        <div className="modal-footer">{t('preview.usage')}</div>
      </div>
    </div>
  );
}