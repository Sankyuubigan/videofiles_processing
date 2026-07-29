import { useEffect, useCallback, useRef, useState } from 'react';
import { getCurrentWebview } from '@tauri-apps/api/webview';

interface UseDragDropOptions {
  onDrop: (paths: string[], position: { x: number; y: number }) => void;
  enabled?: boolean;
}

export function useDragDrop({ onDrop, enabled = true }: UseDragDropOptions) {
  const [isDragOver, setIsDragOver] = useState(false);
  const onDropRef = useRef(onDrop);
  onDropRef.current = onDrop;
  const lastPositionRef = useRef({ x: 0, y: 0 });

  useEffect(() => {
    if (!enabled) return;

    let unlisten: (() => void) | null = null;

    const setup = async () => {
      try {
        const webview = getCurrentWebview();
        unlisten = await webview.onDragDropEvent((event) => {
          if (event.payload.type === 'enter' || event.payload.type === 'over') {
            setIsDragOver(true);
            if (event.payload.position) {
              lastPositionRef.current = {
                x: event.payload.position.x,
                y: event.payload.position.y,
              };
            }
          } else if (event.payload.type === 'leave') {
            setIsDragOver(false);
          } else if (event.payload.type === 'drop') {
            setIsDragOver(false);
            const paths = event.payload.paths;
            const pos = event.payload.position || lastPositionRef.current;
            if (paths.length > 0) {
              onDropRef.current(paths, { x: pos.x, y: pos.y });
            }
          }
        });
      } catch (e) {
        console.error('Failed to set up drag-drop listener:', e);
      }
    };

    setup();

    return () => {
      if (unlisten) unlisten();
    };
  }, [enabled]);

  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
  }, []);

  return { isDragOver, onDragOver };
}
