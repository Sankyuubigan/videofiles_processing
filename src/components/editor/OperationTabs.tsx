import { useState } from 'react';
import { FileEntry, OperationTab } from '../../types';
import { CODECS, OUTPUT_FORMATS } from '../../constants/codecs';
import { t } from '../../i18n';

interface Props {
  activeTab: OperationTab;
  setActiveTab: (t: OperationTab) => void;
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
  selectedFile: FileEntry | null;
  onTrim: (path: string, seconds: number, fromStart: boolean) => void;
  onNormalize: (path: string) => void;
  onExtractFrame: (path: string, frame: number) => void;
  isProcessing: boolean;
}

export default function OperationTabs(props: Props) {
  const [trimSeconds, setTrimSeconds] = useState(10);
  const [trimFromStart, setTrimFromStart] = useState(false);

  const codecInfo = CODECS[props.selectedCodec];
  const formatInfo = OUTPUT_FORMATS[props.selectedFormat];
  const compatibleCodecs = formatInfo?.compatibleCodecs || [];

  return (
    <div>
      <div className="op-tabs">
        <button className={`op-tab ${props.activeTab === 'compress' ? 'active' : ''}`} onClick={() => props.setActiveTab('compress')}>{t('op.compress')}</button>
        <button className={`op-tab ${props.activeTab === 'trim' ? 'active' : ''}`} onClick={() => props.setActiveTab('trim')}>{t('op.trim')}</button>
        <button className={`op-tab ${props.activeTab === 'normalize' ? 'active' : ''}`} onClick={() => props.setActiveTab('normalize')}>{t('op.normalize')}</button>
      </div>

      {props.activeTab === 'compress' && (
        <div className="op-panel">
          <div className="op-row">
            <label>Format:</label>
            <select value={props.selectedFormat} onChange={(e) => props.onFormatChange(e.target.value)}>
              {Object.entries(OUTPUT_FORMATS).map(([k, v]) => (
                <option key={k} value={k}>.{v.name}</option>
              ))}
            </select>
          </div>
          <div className="op-row">
            <label>Codec:</label>
            <select value={props.selectedCodec} onChange={(e) => props.onCodecChange(e.target.value)}>
              {compatibleCodecs.map(c => (
                <option key={c} value={c}>{CODECS[c]?.name || c}</option>
              ))}
            </select>
          </div>
          <div className="op-row">
            <label>Encoding:</label>
            <label><input type="radio" checked={!props.useHardware} onChange={() => props.setUseHardware(false)} /> Software (CPU)</label>
            <label><input type="radio" checked={props.useHardware} onChange={() => props.setUseHardware(true)} /> Hardware (NVENC)</label>
          </div>
          <div className="op-row">
            <label>Preset:</label>
            <select value={props.selectedPreset} onChange={(e) => props.setSelectedPreset(e.target.value)}>
              {codecInfo?.presets.map(p => <option key={p} value={p}>{p}</option>)}
            </select>
          </div>
          <div className="op-row">
            <label>CRF:</label>
            <div className="crf-slider">
              <span>{codecInfo?.crfMin || 18}</span>
              <input
                type="range"
                min={codecInfo?.crfMin || 18}
                max={codecInfo?.crfMax || 35}
                value={props.crfValue}
                onChange={(e) => props.setCrfValue(parseInt(e.target.value))}
                disabled={props.autoCrf}
              />
              <span>{codecInfo?.crfMax || 35}</span>
              <span className="crf-value">{props.crfValue}</span>
            </div>
          </div>
          <div className="op-row">
            <div className="checkbox-row">
              <input type="checkbox" id="autoCrf" checked={props.autoCrf} onChange={(e) => props.setAutoCrf(e.target.checked)} />
              <label htmlFor="autoCrf">Auto CRF (VMAF target)</label>
            </div>
            {props.autoCrf && (
              <div className="vmaf-input">
                <label>VMAF:</label>
                <input
                  type="number"
                  min={80}
                  max={99}
                  step={0.5}
                  value={props.targetVmaf}
                  onChange={(e) => props.setTargetVmaf(parseFloat(e.target.value))}
                />
                <label style={{ marginLeft: 12 }}>SSIMULACRA2:</label>
                <input
                  type="number"
                  min={60}
                  max={100}
                  step={0.5}
                  value={props.targetSsimulacra2}
                  onChange={(e) => props.setTargetSsimulacra2(parseFloat(e.target.value))}
                />
              </div>
            )}
          </div>
          <div className="op-row">
            <div className="checkbox-row">
              <input type="checkbox" id="vfrFix" checked={props.forceVfrFix} onChange={(e) => props.setForceVfrFix(e.target.checked)} />
              <label htmlFor="vfrFix">Force VFR fix</label>
            </div>
            {props.selectedFile?.info && (
              <span className={`vfr-status ${props.selectedFile.info.needs_vfr_fix ? 'needs-fix' : 'ok'}`}>
                VFR: {props.selectedFile.info.needs_vfr_fix ? 'Needs fix' : 'OK'}
              </span>
            )}
          </div>
        </div>
      )}

      {props.activeTab === 'trim' && (
        <div className="op-panel">
          <div className="op-row">
            <label>Seconds to remove:</label>
            <input
              type="number"
              min={1}
              max={3600}
              value={trimSeconds}
              onChange={(e) => setTrimSeconds(parseInt(e.target.value))}
              style={{ width: 100 }}
            />
            <span>sec</span>
          </div>
          <div className="op-row">
            <label>From:</label>
            <label><input type="radio" checked={!trimFromStart} onChange={() => setTrimFromStart(false)} /> End</label>
            <label><input type="radio" checked={trimFromStart} onChange={() => setTrimFromStart(true)} /> Start</label>
          </div>
          <p style={{ fontSize: 12, color: '#666' }}>Video will be saved with suffix '_trimmed'.</p>
          <button
            className="btn-start"
            disabled={!props.selectedFile || props.isProcessing}
            onClick={() => props.selectedFile && props.onTrim(props.selectedFile.path, trimSeconds, trimFromStart)}
          >
            Trim
          </button>
        </div>
      )}

      {props.activeTab === 'normalize' && (
        <div className="op-panel">
          <p style={{ marginBottom: 8 }}>Two-step audio normalization: 1) dynamic normalization, 2) volume normalization.</p>
          <p style={{ fontSize: 12, color: '#666', marginBottom: 12 }}>Video will be saved with suffix '_volnorm'.</p>
          <button
            className="btn-start"
            disabled={!props.selectedFile || props.isProcessing}
            onClick={() => props.selectedFile && props.onNormalize(props.selectedFile.path)}
          >
            Normalize Audio
          </button>
        </div>
      )}
    </div>
  );
}
