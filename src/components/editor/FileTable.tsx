import { FileEntry } from '../../types';
import { formatFileSize, formatDuration } from '../../constants/codecs';

interface Props {
  files: FileEntry[];
  selectedIndex: number;
  onSelect: (i: number) => void;
  onRemove: (path: string) => void;
  onVideoTypeChange: (path: string, videoType: string) => void;
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
  if (!info.test_result || info.test_result.error) return { text: '--', class: '' };
  const profitable = info.test_result.is_profitable;
  return { text: `${info.test_result.test_est_size} (${info.test_result.test_diff})`, class: profitable ? 'cell-green' : 'cell-red' };
}

function shorten(text: string, max: number): string {
  return text.length > max ? text.slice(0, max - 3) + '...' : text;
}

function getVmafDisplay(info: FileEntry): { text: string; class: string; title?: string } {
  if (info.test_result?.error) return { text: shorten(info.test_result.error, 40), class: 'cell-red', title: info.test_result.error };
  if (!info.test_result) return { text: '--', class: '' };
  const vmaf = info.test_result.test_vmaf;
  if (vmaf === -2.0) return { text: 'No metric', class: 'cell-gray' };
  const crf = info.test_result.test_crf;
  const metric = info.test_result.metric;
  const shortMetric = metric === 'SSIMULACRA2' ? 'SSIM2' : metric;
  return { text: `${crf} / ${shortMetric} ${vmaf.toFixed(1)}`, class: getVmafClass(vmaf) };
}

function getEstTimeDisplay(info: FileEntry): string {
  if (!info.test_result || info.test_result.error) return '--';
  return info.test_result.test_est_time;
}

function getVideoTypeDisplay(info: FileEntry): { text: string; class: string } {
  if (info.analysis_state === 'failed') return { text: 'Error', class: 'cell-red' };
  const vt = info.info?.video_type;
  if (!vt) return { text: '--', class: '' };
  switch (vt) {
    case 'Animation': return { text: 'Animation', class: 'cell-yellow' };
    case 'LiveAction': return { text: 'LiveAction', class: 'cell-green' };
    case 'Rendered': return { text: 'Rendered', class: 'cell-blue' };
    default: return { text: vt, class: '' };
  }
}

function isAnalyzing(info: FileEntry): boolean {
  return info.analysis_state === 'pending' || info.analysis_state === 'probing' || info.analysis_state === 'detecting';
}

export default function FileTable({ files, selectedIndex, onSelect, onRemove, onVideoTypeChange }: Props) {
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
          <th>Actions</th>
        </tr>
      </thead>
      <tbody>
        {files.map((file, i) => {
          const crfDisp = getCrfDisplay(file);
          const vfrDisp = getVfrDisplay(file);
          const estSizeDisp = getEstSizeDisplay(file);
          const vmafDisp = getVmafDisplay(file);
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
              <td className={typeDisp.class} title={file.error || undefined}>
                {isAnalyzing(file) ? (
                  <span className="type-spinner" title="Detecting content type..." />
                ) : file.info ? (
                  <select
                    className="video-type-select"
                    value={file.info.video_type}
                    onClick={(e) => e.stopPropagation()}
                    onChange={(e) => { e.stopPropagation(); onVideoTypeChange(file.path, e.target.value); }}
                  >
                    <option value="Animation">Animation</option>
                    <option value="LiveAction">LiveAction</option>
                    <option value="Rendered">Rendered</option>
                  </select>
                ) : (
                  typeDisp.text
                )}
              </td>
              <td className={crfDisp.class}>{crfDisp.text}</td>
              <td className={vfrDisp.class}>{vfrDisp.text}</td>
              <td className={estSizeDisp.class}>{estSizeDisp.text}</td>
              <td className={vmafDisp.class} title={vmafDisp.title}>{vmafDisp.text}</td>
              <td>{estTime}</td>
              <td>
                <div className="action-btn-group">
                  <button className="action-btn delete" onClick={(e) => { e.stopPropagation(); onRemove(file.path); }}>x</button>
                </div>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}