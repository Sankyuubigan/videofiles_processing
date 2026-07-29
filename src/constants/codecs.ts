export interface CodecInfo {
  name: string;
  crfMin: number;
  crfMax: number;
  crfDefault: number;
  presets: string[];
  presetDefault: string;
}

export interface FormatInfo {
  name: string;
  compatibleCodecs: string[];
  audioCodec: string;
  defaultCodec: string;
}

export const CODECS: Record<string, CodecInfo> = {
  libx264: {
    name: 'H.264 (AVC)',
    crfMin: 18, crfMax: 35, crfDefault: 22,
    presets: ['veryslow','slower','slow','medium','fast','faster','veryfast','superfast','ultrafast'],
    presetDefault: 'slow',
  },
  libx265: {
    name: 'H.265 (HEVC)',
    crfMin: 20, crfMax: 40, crfDefault: 21,
    presets: ['veryslow','slower','slow','medium','fast','faster','veryfast','superfast','ultrafast'],
    presetDefault: 'slow',
  },
  'libvpx-vp9': {
    name: 'VP9',
    crfMin: 15, crfMax: 50, crfDefault: 28,
    presets: ['veryslow','slower','slow','medium','fast','faster','veryfast','superfast','ultrafast'],
    presetDefault: 'slow',
  },
};

export const OUTPUT_FORMATS: Record<string, FormatInfo> = {
  mp4: { name: 'MP4', compatibleCodecs: ['libx264','libx265'], audioCodec: 'aac', defaultCodec: 'libx264' },
  mkv: { name: 'MKV', compatibleCodecs: ['libx264','libx265'], audioCodec: 'aac', defaultCodec: 'libx264' },
  hevc: { name: 'HEVC', compatibleCodecs: ['libx265'], audioCodec: 'aac', defaultCodec: 'libx265' },
  webm: { name: 'WebM', compatibleCodecs: ['libvpx-vp9'], audioCodec: 'libopus', defaultCodec: 'libvpx-vp9' },
};

export function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.floor(seconds)}s`;
  if (seconds < 3600) {
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m}m ${s}s`;
  }
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  return `${h}h ${m}m ${s}s`;
}

export function formatFileSize(mb: number): string {
  if (mb < 1) return `${(mb * 1024).toFixed(0)} KB`;
  if (mb < 1024) return `${mb.toFixed(1)} MB`;
  return `${(mb / 1024).toFixed(2)} GB`;
}
