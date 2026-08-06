import { useCallback, useEffect, useRef, useState } from 'react';
import { listen, type UnlistenFn } from '@tauri-apps/api/event';
import { convertFileSrc } from '@tauri-apps/api/core';
import Hls from 'hls.js';
import { tauriInvoke } from './useTauri';

export type CompareMode = 'direct' | 'hls';

interface PreviewInfo {
  mode: 'Direct' | 'Remux' | 'Hls';
  path: string;
  hls: boolean;
  converting: boolean;
  job_id: string;
}

interface Options {
  videoRef: React.RefObject<HTMLVideoElement | null>;
  addLog: (msg: string) => void;
  onError: (msg: string) => void;
  onReady: () => void;
}

export function useCompareSide({ videoRef, addLog, onError, onReady }: Options) {
  const [src, setSrc] = useState<string | null>(null);
  const [mode, setMode] = useState<CompareMode>('direct');
  const [converting, setConverting] = useState<number | null>(null);
  const [original, setOriginal] = useState(false);
  const hlsRef = useRef<Hls | null>(null);
  const jobRef = useRef<string | null>(null);
  const srcRef = useRef<string | null>(null);
  const loadSeqRef = useRef(0);
  const optsRef = useRef({ addLog, onError, onReady });
  optsRef.current = { addLog, onError, onReady };

  const destroyHls = useCallback(() => {
    if (hlsRef.current) {
      hlsRef.current.destroy();
      hlsRef.current = null;
    }
  }, []);

  const cancelJob = useCallback((jobId: string | null) => {
    if (jobId) {
      tauriInvoke('cancel_preview_cmd', { jobId }).catch((e) => {
        console.error('[Compare] Cancel preview error:', e);
      });
    }
  }, []);

  const attachHls = useCallback(
    (hlsUrl: string, video: HTMLVideoElement, startFromBeginning: boolean) => {
      destroyHls();
      const wasPlaying = !video.paused;
      const resumeTime = video.currentTime;
      const hls = new Hls({
        liveDurationInfinity: true,
        startPosition: startFromBeginning ? 0 : -1,
        maxBufferLength: 60,
        maxMaxBufferLength: 600,
      });
      hlsRef.current = hls;
      hls.loadSource(hlsUrl);
      hls.attachMedia(video);
      hls.on(Hls.Events.MANIFEST_PARSED, () => {
        if (!startFromBeginning && resumeTime > 0) {
          video.currentTime = Math.min(resumeTime, hls.duration || 0);
        }
        if (wasPlaying) {
          video.play().catch(() => {});
        }
      });
      hls.on(Hls.Events.ERROR, (_evt, data) => {
        if (data.fatal) {
          console.error('[Compare] HLS fatal error:', data);
          const { addLog, onError } = optsRef.current;
          onError(`HLS playback error: ${data.details}`);
          addLog(`Compare HLS error: ${data.details}`);
        }
      });
    },
    [destroyHls]
  );

  useEffect(() => {
    let unlisteners: UnlistenFn[] = [];
    (async () => {
      unlisteners = [
        await listen<[string, number]>('preview-progress', (ev) => {
          const [jobId, percent] = ev.payload;
          if (jobId === jobRef.current) setConverting(percent);
        }),
        await listen<string>('preview-ready', (ev) => {
          if (ev.payload === jobRef.current) {
            setConverting(null);
            const url = srcRef.current;
            if (url) {
              setSrc(url);
              setMode('hls');
            }
            optsRef.current.onReady();
          }
        }),
        await listen<[string, string]>('preview-error', (ev) => {
          const [jobId, msg] = ev.payload;
          if (jobId === jobRef.current) {
            setConverting(null);
            optsRef.current.onError(msg);
            optsRef.current.addLog(`Compare preview error: ${msg}`);
          }
        }),
      ];
    })();
    return () => {
      unlisteners.forEach((u) => u());
    };
  }, [videoRef, attachHls]);

  useEffect(() => {
    const video = videoRef.current;
    if (mode === 'hls' && src && video) {
      attachHls(src, video, true);
      return () => destroyHls();
    }
    return undefined;
  }, [mode, src, videoRef, attachHls, destroyHls]);

  const load = useCallback(
    async (path: string, force = false) => {
      const seq = ++loadSeqRef.current;
      destroyHls();
      cancelJob(jobRef.current);
      jobRef.current = null;
      setConverting(null);

      try {
        const res = await tauriInvoke<PreviewInfo>('prepare_preview_cmd', { path, forceTranscode: force });
        if (seq !== loadSeqRef.current) return;

        setOriginal(res.mode === 'Direct');
        if (res.mode === 'Hls') {
          const base = await tauriInvoke<string>('get_stream_url');
          jobRef.current = res.job_id || null;
          const url = `${base}/preview?path=${encodeURIComponent(res.path)}`;
          srcRef.current = url;
          if (res.converting) {
            // m3u8 ещё не существует — ждём preview-ready, чтобы не грузить несуществующий плейлист
            setConverting(0);
            setSrc(null);
            setMode('direct');
          } else {
            setSrc(url);
            setMode('hls');
          }
        } else {
          // Direct/Remux: играем через asset protocol (convertFileSrc) — проверенный путь
          const url = convertFileSrc(res.path);
          srcRef.current = url;
          setSrc(url);
          setMode('direct');
        }
        optsRef.current.addLog(`Compare: ${res.mode} ${res.hls ? 'HLS' : 'file'} ready for ${path.split(/[\\/]/).pop()}`);
      } catch (e) {
        if (seq !== loadSeqRef.current) return;
        const msg = String(e);
        console.error('[Compare] Prepare preview failed:', e);
        setSrc(null);
        setMode('direct');
        optsRef.current.addLog(`Compare preview prepare error: ${msg}`);
        optsRef.current.onError(msg);
      }
    },
    [destroyHls, cancelJob]
  );

  return { src, mode, converting, original, load };
}
