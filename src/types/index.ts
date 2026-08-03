export interface AudioTrack {
  index: number;
  codec: string;
  language: string;
  title: string;
  channels: number;
  sample_rate: string;
  bit_rate: string;
}

export interface VideoInfo {
  path: string;
  duration: number;
  size_mb: number;
  video_bitrate: number;
  audio_bitrate: number;
  width: number;
  height: number;
  fps: number;
  needs_vfr_fix: boolean;
  is_hevc: boolean;
  is_10bit: boolean;
  video_codec: string;
  pixel_format: string;
  has_subtitles: boolean;
  audio_tracks: AudioTrack[];
  gpu_info: string;
  processing_mode: string;
  complexity_score: number;
  complexity_desc: string;
  crf_value: number | null;
  video_type: 'Animation' | 'LiveAction' | 'Rendered';
}

export interface FileEntry {
  path: string;
  info: VideoInfo | null;
  test_result: TestResult | null;
}

export interface TestResult {
  test_diff: string;
  test_est_size: string;
  test_est_time: string;
  test_vmaf: number;
  is_profitable: boolean;
  test_crf: number;
  metric: string;
}

export interface Settings {
  ffmpeg_path: string;
  vmaf_subsample: number;
  chunk_count: number;
  chunk_duration: number;
  locale: string;
  skip_min_diff_enabled: boolean;
  skip_min_diff_percent: number;
  skip_min_crf_enabled: boolean;
  skip_min_crf_value: number;
  vmaf_ignore_noise: boolean;
}

export type Locale = 'en' | 'ru';

export type TabId = 'editor' | 'compare' | 'logs' | 'settings' | 'help';
export type OperationTab = 'compress' | 'trim' | 'normalize';
