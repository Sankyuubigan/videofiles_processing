export default function HelpTab() {
  return (
    <div className="help-container">
      <h2>File Table Columns</h2>
      <p><strong>VFR</strong> - Sometimes video has broken frames and needs repair for successful compression.</p>
      <p><strong>VMAF</strong> - Algorithm comparing original and estimated compression quality. Score in percent shows how much quality will be lost.</p>
      <p><strong>CRF</strong> - Shows if the video was already compressed before.</p>

      <h2>Red Color in Table</h2>
      <p>If estimated size is highlighted red, the video is likely already compressed.</p>
      <p>If CRF is red, the video was definitely compressed before. But if everything else is green, size can still decrease due to better preset or higher CRF value.</p>

      <h2>Compression Parameters</h2>
      <p><strong>Codec HEVC</strong> produces smaller files but compresses slower than AVC and uses more hardware resources during playback.</p>
      <p><strong>Preset</strong> affects quality after compression and compression time.</p>
      <p><strong>Coding type</strong> affects not only compression time but also the output file size.</p>
    </div>
  );
}
