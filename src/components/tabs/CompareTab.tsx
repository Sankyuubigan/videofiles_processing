import { useState, useRef, useCallback } from 'react';
import { open } from '@tauri-apps/plugin-dialog';
import { convertFileSrc } from '@tauri-apps/api/core';
import { useVideoSync } from '../../hooks/useVideoSync';
import { useDragDrop } from '../../hooks/useDragDrop';
import { tauriInvoke } from '../../hooks/useTauri';
import { VideoInfo } from '../../types';
import { formatFileSize } from '../../constants/codecs';
import { t } from '../../i18n';

const BROWSER_SUPPORTED_CODECS = ['h264', 'vp8', 'vp9', 'av1'];

interface Props {
  addLog: (msg: string) => void;
}

export default function CompareTab({ addLog }: Props) {
  const [fileA, setFileA] = useState<string | null>(null);
  const [fileB, setFileB] = useState<string | null>(null);
  const [infoA, setInfoA] = useState<VideoInfo | null>(null);
  const [infoB, setInfoB] = useState<VideoInfo | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [errorA, setErrorA] = useState<string | null>(null);
  const [errorB, setErrorB] = useState<string | null>(null);
  const [hoveredSide, setHoveredSide] = useState<'a' | 'b' | null>(null);
  const leaderRef = useRef<HTMLVideoElement>(null);
  const followerRef = useRef<HTMLVideoElement>(null);
  const boxARef = useRef<HTMLDivElement>(null);
  const boxBRef = useRef<HTMLDivElement>(null);

  useVideoSync(leaderRef, followerRef);

  const getVideoSrc = useCallback((path: string): string => {
    if (!path) return '';
    return convertFileSrc(path);
  }, []);

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

    setFile(path);
    setError(null);

    const info = await probeFile(path);
    if (info) {
      setInfo(info);
      const codec = info.video_codec.toLowerCase();
      if (!BROWSER_SUPPORTED_CODECS.includes(codec)) {
        const msg = `Codec "${info.video_codec}" may not play in the browser. Convert to H.264 (MP4) for best compatibility.`;
        console.warn('[CompareTab]', msg);
        addLog(`Compare warning: ${path.split(/[\\/]/).pop()} - ${msg}`);
        setError(msg);
      }
    } else {
      setInfo(null);
    }
  }, [probeFile, addLog]);

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

  const { isDragOver } = useDragDrop({ onDrop: handleDrop });

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
    if (el) {
      console.log(`[CompareTab] Video ${side} loaded, duration:`, el.duration);
      if (side === 'a') setDuration(el.duration);
    }
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
    if (side === 'a') setErrorA(msg);
    else setErrorB(msg);
  };

  const togglePlay = () => {
    const leader = leaderRef.current;
    const follower = followerRef.current;
    if (!leader) return;
    
    if (isPlaying) {
      leader.pause();
      if (follower) follower.pause();
    } else {
      leader.play().catch((e) => {
        console.error('[CompareTab] Play error:', e);
      });
      if (follower) follower.play().catch(() => {});
    }
    setIsPlaying(!isPlaying);
  };

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
              src={getVideoSrc(fileA)}
              onLoadedMetadata={() => handleLoadedMetadata('a')}
              onTimeUpdate={handleTimeUpdate}
              onPlay={() => setIsPlaying(true)}
              onPause={() => setIsPlaying(false)}
              onEnded={() => setIsPlaying(false)}
              onError={(e) => handleError('a', e)}
              style={{ objectFit: 'none', background: '#000', width: '100%', height: '100%' }}
            />
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
              src={getVideoSrc(fileB)}
              onLoadedMetadata={() => handleLoadedMetadata('b')}
              onError={(e) => handleError('b', e)}
              muted
              style={{ objectFit: 'none', background: '#000', width: '100%', height: '100%' }}
            />
          )}
          {errorB && <div className="video-error">{errorB}</div>}
        </div>
      </div>
      <div className="compare-timeline">
        <button onClick={togglePlay}>{isPlaying ? t('compare.pause') : t('compare.play')}</button>
        <input
          type="range"
          min={0}
          max={duration || 0}
          step={0.01}
          value={currentTime}
          onChange={handleSeek}
        />
        <span className="time-label">{formatTime(currentTime)} / {formatTime(duration)}</span>
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