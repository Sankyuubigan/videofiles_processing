import { FileEntry } from '../../types';
import { formatFileSize, formatDuration } from '../../constants/codecs';
import { t } from '../../i18n';

interface Props {
  files: FileEntry[];
  selectedIndex: number;
  onSelect: (i: number) => void;
  onRemove: (i: number) => void;
  onTest: (i: number, forceMetric?: string) => void;
  onNnTest: (i: number, metric: string) => void;
  onAllMetrics: (i: number) => void;
  onVideoTypeChange: (i: number, videoType: string) => void;
}

function getVmafClass(vmaf: number | null): string {
  if (vmaf === null || vmaf < 0) return 'cell-gray';
  if (vmaf >= 93) return 'cell-green';
  if (vmaf >= 80) return 'cell-orange';
  return 'cell-red';
}

function getCrfDisplay(info: FileEntry): { text: string; class: string } {
  const crf = info.info?.crf_value;
  if (crf === null || crf === undefined) return { text: 'none', class: 'cell-green' };
  return { text: String(Math.round(crf)), class: 'cell-orange' };
}

function getVfrDisplay(info: FileEntry): { text: string; class: string } {
  if (info.info?.needs_vfr_fix) return { text: 'Needs fix', class: 'cell-red' };
  return { text: 'OK', class: 'cell-green' };
}

function getEstSizeDisplay(info: FileEntry): { text: string; class: string } {
  if (!info.test_result) return { text: '--', class: '' };
  const profitable = info.test_result.is_profitable;
  return { text: `${info.test_result.test_est_size} (${info.test_result.test_diff})`, class: profitable ? 'cell-green' : 'cell-red' };
}

function getVmafDisplay(info: FileEntry): { text: string; class: string } {
  if (!info.test_result) return { text: '--', class: '' };
  const vmaf = info.test_result.test_vmaf;
  if (vmaf === -2.0) return { text: 'No metric', class: 'cell-gray' };
  const crf = info.test_result.test_crf;
  const metric = info.test_result.metric;
  const shortMetric = metric === 'SSIMULACRA2' ? 'SSIM2' : metric;
  return { text: `${crf} / ${shortMetric} ${vmaf.toFixed(1)}`, class: getVmafClass(vmaf) };
}

function getNnDisplay(info: FileEntry): { text: string; class: string } {
  if (!info.nn_test_result) return { text: '--', class: '' };
  const r = info.nn_test_result;
  const cls = r.passed ? 'cell-green' : 'cell-red';
  return { text: `${r.metric} ${r.score.toFixed(4)} (${r.inference_ms}ms)`, class: cls };
}

function getEstTimeDisplay(info: FileEntry): string {
  if (!info.test_result) return '--';
  return info.test_result.test_est_time;
}

function getVideoTypeDisplay(info: FileEntry): { text: string; class: string } {
  const vt = info.info?.video_type;
  if (!vt) return { text: '--', class: '' };
  switch (vt) {
    case 'Animation': return { text: 'Animation', class: 'cell-yellow' };
    case 'LiveAction': return { text: 'LiveAction', class: 'cell-green' };
    default: return { text: vt, class: '' };
  }
}

export default function FileTable({ files, selectedIndex, onSelect, onRemove, onTest, onNnTest, onAllMetrics, onVideoTypeChange }: Props) {
  if (files.length === 0) {
    return (
      <div style={{ padding: 40, textAlign: 'center', color: '#888' }}>
        Drag and drop files here or click "Select file(s)"
      </div>
    );
  }

  return (
    <table className="file-table">
      <thead>
        <tr>
          <th>File Name</th>
          <th>Size</th>
          <th>Duration</th>
          <th>Type</th>
          <th>CRF</th>
          <th>VFR Status</th>
          <th>Est. Size (Diff)</th>
          <th>CRF / Metric</th>
          <th>Est. Time</th>
          <th>Neural Net</th>
          <th>Actions</th>
        </tr>
      </thead>
      <tbody>
        {files.map((file, i) => {
          const crfDisp = getCrfDisplay(file);
          const vfrDisp = getVfrDisplay(file);
          const estSizeDisp = getEstSizeDisplay(file);
          const vmafDisp = getVmafDisplay(file);
          const nnDisp = getNnDisplay(file);
          const estTime = getEstTimeDisplay(file);
          const typeDisp = getVideoTypeDisplay(file);
          const name = file.path.split(/[\\/]/).pop() || file.path;

          return (
            <tr
              key={i}
              className={i === selectedIndex ? 'selected' : ''}
              onClick={() => onSelect(i)}
            >
              <td title={file.path}>{name}</td>
              <td>{file.info ? formatFileSize(file.info.size_mb) : '--'}</td>
              <td>{file.info ? formatDuration(file.info.duration) : '--'}</td>
              <td className={typeDisp.class}>
                {file.info ? (
                  <select
                    className="video-type-select"
                    value={file.info.video_type}
                    onClick={(e) => e.stopPropagation()}
                    onChange={(e) => { e.stopPropagation(); onVideoTypeChange(i, e.target.value); }}
                  >
                    <option value="Animation">Animation</option>
                    <option value="LiveAction">LiveAction</option>
                  </select>
                ) : (
                  typeDisp.text
                )}
              </td>
              <td className={crfDisp.class}>{crfDisp.text}</td>
              <td className={vfrDisp.class}>{vfrDisp.text}</td>
              <td className={estSizeDisp.class}>{estSizeDisp.text}</td>
              <td className={vmafDisp.class}>{vmafDisp.text}</td>
              <td>{estTime}</td>
              <td className={nnDisp.class}>{nnDisp.text}</td>
              <td>
                <div className="action-btn-group">
                  <button className="action-btn test" onClick={(e) => { e.stopPropagation(); onTest(i); }}>{t('table.auto_test')}</button>
                  <button className="action-btn test" onClick={(e) => { e.stopPropagation(); onTest(i, 'VMAF'); }}>{t('table.test_vmaf')}</button>
                  <button className="action-btn test" onClick={(e) => { e.stopPropagation(); onTest(i, 'SSIMULACRA2'); }}>{t('table.test_ssim')}</button>
                  <button className="action-btn test nn" onClick={(e) => { e.stopPropagation(); onNnTest(i, 'LPIPS'); }}>{t('table.test_lpips')}</button>
                  <button className="action-btn test nn" onClick={(e) => { e.stopPropagation(); onNnTest(i, 'DISTS'); }}>{t('table.test_dists')}</button>
                  <button className="action-btn test all" onClick={(e) => { e.stopPropagation(); onAllMetrics(i); }}>{t('table.test_all')}</button>
                  <button className="action-btn delete" onClick={(e) => { e.stopPropagation(); onRemove(i); }}>x</button>
                </div>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}