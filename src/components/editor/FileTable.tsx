import { FileEntry } from '../../types';
import { formatFileSize, formatDuration } from '../../constants/codecs';

interface Props {
  files: FileEntry[];
  selectedIndex: number;
  onSelect: (i: number) => void;
  onRemove: (i: number) => void;
  onTest: (i: number) => void;
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
  if (vmaf === -2.0) return { text: 'No libvmaf', class: 'cell-gray' };
  return { text: vmaf.toFixed(1), class: getVmafClass(vmaf) };
}

function getEstTimeDisplay(info: FileEntry): string {
  if (!info.test_result) return '--';
  return info.test_result.test_est_time;
}

export default function FileTable({ files, selectedIndex, onSelect, onRemove, onTest }: Props) {
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
          <th>CRF</th>
          <th>VFR Status</th>
          <th>Est. Size (Diff)</th>
          <th>VMAF</th>
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
              <td className={crfDisp.class}>{crfDisp.text}</td>
              <td className={vfrDisp.class}>{vfrDisp.text}</td>
              <td className={estSizeDisp.class}>{estSizeDisp.text}</td>
              <td className={vmafDisp.class}>{vmafDisp.text}</td>
              <td>{estTime}</td>
              <td>
                <button className="action-btn test" onClick={(e) => { e.stopPropagation(); onTest(i); }}>Test</button>
                <button className="action-btn delete" onClick={(e) => { e.stopPropagation(); onRemove(i); }}>x</button>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
