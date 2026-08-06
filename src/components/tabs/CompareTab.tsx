import { useState, useRef, useCallback, useEffect } from 'react';
import { open } from '@tauri-apps/plugin-dialog';
import { useVideoSync } from '../../hooks/useVideoSync';
import { useDragDrop } from '../../hooks/useDragDrop';
import { useCompareSide } from '../../hooks/useCompareSide';
import { tauriInvoke } from '../../hooks/useTauri';
import { VideoInfo } from '../../types';
import { formatFileSize } from '../../constants/codecs';
import { t } from '../../i18n';

interface Props {
  addLog: (msg: string) => void;
  isActive: boolean;
}

export default function CompareTab({ addLog, isActive }: Props) {
  const [fileA, setFileA] = useState<string | null>(null);
  const [fileB, setFileB] = useState<string | null>(null);
  const [infoA, setInfoA] = useState<VideoInfo | null>(null);
  const [infoB, setInfoB] = useState<VideoInfo | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [volume, setVolume] = useState(1);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [errorA, setErrorA] = useState<string | null>(null);
  const [errorB, setErrorB] = useState<string | null>(null);
  const [hoveredSide, setHoveredSide] = useState<'a' | 'b' | null>(null);
  const leaderRef = useRef<HTMLVideoElement>(null);
  const followerRef = useRef<HTMLVideoElement>(null);
  const boxARef = useRef<HTMLDivElement>(null);
  const boxBRef = useRef<HTMLDivElement>(null);
  const forcedARef = useRef(false);
  const forcedBRef = useRef(false);

  const sideA = useCompareSide({
    videoRef: leaderRef,
    addLog,
    onError: setErrorA,
    onReady: () => {
      addLog('Compare: left preview converted, full seeking available');
      setErrorA(null);
    },
  });
  const sideB = useCompareSide({
    videoRef: followerRef,
    addLog,
    onError: setErrorB,
    onReady: () => {
      addLog('Compare: right preview converted, full seeking available');
      setErrorB(null);
    },
  });

  useVideoSync(leaderRef, followerRef);

  useEffect(() => {
    if (leaderRef.current) leaderRef.current.volume = volume;
    if (followerRef.current) followerRef.current.volume = volume;
  }, [volume]);

  const probeFile = useCallback(async (filePath: string): Promise<VideoInfo | null> => {
    try {
      return await tauriInvoke<VideoInfo>('get_video_details', { filePath });
    } catch (e) {
      console.error('[CompareTab] Probe failed:', e);
      addLog(`Compare probe error: ${e}`);
      return null;
    }
  }, [addLog]);

  const loadFile = useCallback(async (path: string, side: 'a' | 'b') => {
    const setFile = side === 'a' ? setFileA : setFileB;
    const setInfo = side === 'a' ? setInfoA : setInfoB;
    const setError = side === 'a' ? setErrorA : setErrorB;
    const loadSide = side === 'a' ? sideA : sideB;

    setFile(path);
    setError(null);
    if (side === 'a') forcedARef.current = false;
    else forcedBRef.current = false;

    const info = await probeFile(path);
    if (info) setInfo(info);
    else setInfo(null);

    // Кодек заведомо не поддерживается WebView2 (HEVC и т.п.) — сразу транскодируем,
    // иначе видео вечно висит чёрным экраном без события ошибки
    const codec = (info?.video_codec ?? '').toLowerCase();
    const browserOk = ['h264', 'vp8', 'vp9', 'av1'].includes(codec);
    if (info && !browserOk) {
      addLog(`Compare ${side === 'a' ? 'left' : 'right'}: codec "${info.video_codec}" not supported by WebView2, transcoding...`);
      await loadSide.load(path, true);
    } else {
      await loadSide.load(path);
    }
  }, [probeFile, sideA, sideB, addLog]);

  const handleDrop = useCallback((paths: string[], position: { x: number; y: number }) => {
    if (paths.length === 0) return;
    const path = paths[0];
    console.log('[CompareTab] File dropped:', path);

    const boxA = boxARef.current;
    const boxB = boxBRef.current;
    let targetSide: 'a' | 'b' = 'a';

    if (boxA && boxB) {
      const rectA = boxA.getBoundingClientRect();
      const rectB = boxB.getBoundingClientRect();
      const centerX = (rectA.right + rectB.left) / 2;
      targetSide = position.x < centerX ? 'a' : 'b';
    }

    console.log('[CompareTab] Dropping to side:', targetSide);
    addLog(`Compare: dropped file to ${targetSide === 'a' ? 'left' : 'right'} - ${path.split(/[\\/]/).pop()}`);
    loadFile(path, targetSide);
  }, [addLog, loadFile]);

  const { isDragOver } = useDragDrop({ onDrop: handleDrop, enabled: isActive });

  const selectFile = useCallback(async (side: 'a' | 'b') => {
    const file = await open({
      filters: [{ name: 'Video', extensions: ['mp4','mkv','avi','mov','webm'] }],
    });
    if (file) {
      const path = file as string;
      console.log('[CompareTab] File selected:', path);
      addLog(`Compare: selected ${side === 'a' ? 'left' : 'right'} - ${path.split(/[\\/]/).pop()}`);
      loadFile(path, side);
    }
  }, [addLog, loadFile]);

  const handleLoadedMetadata = (side: 'a' | 'b') => {
    const el = side === 'a' ? leaderRef.current : followerRef.current;
    if (!el) return;
    const d = el.duration;
    console.log(`[CompareTab] Video ${side} loaded, duration:`, d);
    if (!isFinite(d)) return;
    addLog(`Compare: ${side === 'a' ? 'left' : 'right'} video loaded (${Math.round(d)}s)`);
    if (side === 'a') setDuration(d);
    else setDuration(prev => (prev > 0 ? prev : d));
  };

  const handleError = (side: 'a' | 'b', e: React.SyntheticEvent<HTMLVideoElement>) => {
    const video = e.currentTarget;
    const err = video.error;
    let msg = 'Unknown error';
    if (err) {
      switch (err.code) {
        case MediaError.MEDIA_ERR_ABORTED:
          msg = 'Playback aborted';
          break;
        case MediaError.MEDIA_ERR_NETWORK:
          msg = 'Network error loading video';
          break;
        case MediaError.MEDIA_ERR_DECODE:
          msg = 'Video decode error';
          break;
        case MediaError.MEDIA_ERR_SRC_NOT_SUPPORTED:
          msg = 'Format not supported or access denied. Try converting to MP4 (H.264)';
          break;
        default:
          msg = `Code: ${err.code}, Message: ${err.message}`;
      }
    }
    const sideLabel = side === 'a' ? 'left' : 'right';
    const fileName = (side === 'a' ? fileA : fileB)?.split(/[\\/]/).pop() || 'unknown';
    console.error(`[CompareTab] Video ${side} error:`, msg);
    addLog(`Compare ${sideLabel} video error (${fileName}): ${msg}`);

    const sideState = side === 'a' ? sideA : sideB;
    const forcedRef = side === 'a' ? forcedARef : forcedBRef;
    const filePath = side === 'a' ? fileA : fileB;

    // Исходник не воспроизводится (нет HEVC-кодека) — автофолбэк на транскод
    if (
      sideState.original &&
      !forcedRef.current &&
      filePath &&
      (err?.code === MediaError.MEDIA_ERR_SRC_NOT_SUPPORTED || err?.code === MediaError.MEDIA_ERR_DECODE)
    ) {
      forcedRef.current = true;
      addLog(`Compare ${sideLabel}: fallback to transcoding (${fileName})`);
      sideState.load(filePath, true);
      return;
    }

    if (side === 'a') setErrorA(msg);
    else setErrorB(msg);
  };

  const togglePlay = useCallback(async () => {
    const leader = leaderRef.current;
    if (!leader) return;

    if (leader.paused) {
      try {
        await leader.play();
      } catch (e) {
        console.error('[CompareTab] Play error:', e);
        addLog(`Compare play error: ${e}`);
      }
    } else {
      leader.pause();
    }
  }, [addLog]);

  const seekBy = useCallback((deltaSec: number) => {
    const leader = leaderRef.current;
    if (!leader || !isFinite(leader.duration) || leader.duration <= 0) return;
    const target = Math.min(Math.max(leader.currentTime + deltaSec, 0), leader.duration);
    leader.currentTime = target;
    const follower = followerRef.current;
    if (follower) follower.currentTime = target;
    setCurrentTime(target);
  }, []);

  const togglePlayRef = useRef(togglePlay);
  togglePlayRef.current = togglePlay;
  const seekByRef = useRef(seekBy);
  seekByRef.current = seekBy;

  useEffect(() => {
    if (!isActive) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable)) {
        return;
      }

      if (e.code === 'Space') {
        e.preventDefault();
        togglePlayRef.current();
      } else if (e.code === 'ArrowRight') {
        e.preventDefault();
        seekByRef.current(5);
      } else if (e.code === 'ArrowLeft') {
        e.preventDefault();
        seekByRef.current(-5);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isActive]);

  const handleSeek = (e: React.ChangeEvent<HTMLInputElement>) => {
    const time = parseFloat(e.target.value);
    setCurrentTime(time);
    if (leaderRef.current) leaderRef.current.currentTime = time;
    if (followerRef.current) followerRef.current.currentTime = time;
  };

  const handleTimeUpdate = () => {
    if (leaderRef.current) setCurrentTime(leaderRef.current.currentTime);
  };

  const isDropTargetA = isDragOver && (hoveredSide === 'a' || (!hoveredSide && isDragOver));
  const isDropTargetB = isDragOver && (hoveredSide === 'b' || (!hoveredSide && isDragOver));

  return (
    <div className="compare-container">
      <div className="compare-selector">
        <button onClick={() => selectFile('a')}>{fileA ? t('compare.change_left') : t('compare.select_left')}</button>
        <button onClick={() => selectFile('b')}>{fileB ? t('compare.change_right') : t('compare.select_right')}</button>
        <span className="drop-target-info">
          {t('compare.drop_hint')}
        </span>
      </div>
      <div className={`compare-videos ${isDragOver ? 'drag-over' : ''}`}>
        <div
          ref={boxARef}
          className={`compare-video-box ${isDropTargetA ? 'drop-target' : ''}`}
          onMouseEnter={() => setHoveredSide('a')}
          onMouseLeave={() => setHoveredSide(null)}
        >
          <div className="compare-video-label">
            {fileA 
              ? `${fileA.split(/[\\/]/).pop()} ${infoA ? `(${infoA.width}x${infoA.height}, ${formatFileSize(infoA.size_mb)})` : ''}` 
              : t('compare.left_video')}
          </div>
          {fileA && (
            <video
              ref={leaderRef}
              src={sideA.mode === 'direct' && sideA.src ? sideA.src : undefined}
              preload="auto"
              onLoadedMetadata={() => handleLoadedMetadata('a')}
              onTimeUpdate={handleTimeUpdate}
              onPlay={() => setIsPlaying(true)}
              onPause={() => setIsPlaying(false)}
              onEnded={() => setIsPlaying(false)}
              onError={(e) => handleError('a', e)}
              style={{ objectFit: 'none', background: '#000', width: '100%', height: '100%' }}
            />
          )}
          {sideA.converting !== null && (
            <div className="video-converting">
              {sideA.converting > 0 ? t('compare.converting', { percent: sideA.converting }) : t('compare.preparing')}
            </div>
          )}
          {errorA && <div className="video-error">{errorA}</div>}
        </div>
        <div
          ref={boxBRef}
          className={`compare-video-box ${isDropTargetB ? 'drop-target' : ''}`}
          onMouseEnter={() => setHoveredSide('b')}
          onMouseLeave={() => setHoveredSide(null)}
        >
          <div className="compare-video-label">
            {fileB 
              ? `${fileB.split(/[\\/]/).pop()} ${infoB ? `(${infoB.width}x${infoB.height}, ${formatFileSize(infoB.size_mb)})` : ''}` 
              : t('compare.right_video')}
          </div>
          {fileB && (
            <video
              ref={followerRef}
              src={sideB.mode === 'direct' && sideB.src ? sideB.src : undefined}
              preload="auto"
              onLoadedMetadata={() => handleLoadedMetadata('b')}
              onError={(e) => handleError('b', e)}
              muted
              style={{ objectFit: 'none', background: '#000', width: '100%', height: '100%' }}
            />
          )}
          {sideB.converting !== null && (
            <div className="video-converting">
              {sideB.converting > 0 ? t('compare.converting', { percent: sideB.converting }) : t('compare.preparing')}
            </div>
          )}
          {errorB && <div className="video-error">{errorB}</div>}
        </div>
      </div>
      <div className="compare-timeline">
        <button onClick={togglePlay}>{isPlaying ? t('compare.pause') : t('compare.play')}</button>
        <input
          className="time-slider"
          type="range"
          min={0}
          max={duration || 0}
          step={0.01}
          value={currentTime}
          onChange={handleSeek}
        />
        <span className="time-label">{formatTime(currentTime)} / {formatTime(duration)}</span>
        <span className="volume-label">{t('compare.volume')}:</span>
        <input
          className="volume-slider"
          type="range"
          min={0}
          max={1}
          step={0.01}
          value={volume}
          onChange={(e) => setVolume(parseFloat(e.target.value))}
        />
        <span className="volume-value">{Math.round(volume * 100)}%</span>
      </div>
    </div>
  );
}

function formatTime(s: number): string {
  if (!s || !isFinite(s)) return '0:00';
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${String(sec).padStart(2, '0')}`;
}
