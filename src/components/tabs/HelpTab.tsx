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

      <h2>Auto Mode (Auto CRF)</h2>
      <p>When <strong>Auto CRF (VMAF target)</strong> is enabled, the program automatically selects the best CRF value for each file to reach the target VMAF quality score.</p>
      <p>How it works:</p>
      <ul>
        <li>The program runs test encodes at different CRF values to find the highest CRF that still achieves the target VMAF (e.g. 90).</li>
        <li>A higher CRF means more compression and smaller file size. Auto mode finds the most aggressive setting that keeps quality above your target.</li>
        <li>If the target VMAF is unreachable even at the maximum CRF for the codec, the file is <strong>skipped</strong> with a message like "target VMAF unreachable (best achieved: X.X)".</li>
      </ul>

      <h2>Auto Mode Skip Rules</h2>
      <p>When Auto CRF is enabled, the program can also skip files that don't need compression. These rules are configurable in <strong>Settings &gt; Auto Mode Skip</strong>:</p>
      <ul>
        <li><strong>Min size reduction</strong> — skips a file if the estimated size reduction is less than this percentage (default 5%). If compressing won't save much space, there's no point.</li>
        <li><strong>Skip if original CRF &ge;</strong> — skips a file if its original CRF is already at or above this value (default 18). Such videos are already well compressed and further compression would only waste time and reduce quality.</li>
      </ul>
      <p>Skipped files are reported in the progress bar with a "SKIP" message explaining the reason.</p>
    </div>
  );
}
