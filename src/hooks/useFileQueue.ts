import { useState, useCallback } from 'react';
import { tauriInvoke } from './useTauri';
import { FileEntry } from '../types';

export function useFileQueue() {
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [selectedIndex, setSelectedIndex] = useState<number>(-1);

  const addFiles = useCallback(async (paths: string[]) => {
    try {
      console.log('[useFileQueue] Adding files:', paths);
      const added = await tauriInvoke<FileEntry[]>('add_files', { paths });
      console.log('[useFileQueue] Added:', added.length, 'files');
      setFiles(prev => [...prev, ...added]);
    } catch (e) {
      console.error('[useFileQueue] add_files error:', e);
    }
  }, []);

  const removeFile = useCallback(async (path: string) => {
    try {
      console.log('[useFileQueue] Removing file:', path);
      const idx = files.findIndex(f => f.path === path);
      await tauriInvoke('remove_file', { path });
      setFiles(prev => prev.filter(f => f.path !== path));
      setSelectedIndex(sel => {
        if (sel === -1 || idx === -1) return sel;
        if (idx < sel) return sel - 1;
        if (idx === sel) return files.length > 1 ? Math.min(sel, files.length - 2) : -1;
        return sel;
      });
    } catch (e) {
      console.error('[useFileQueue] remove_file error:', e);
    }
  }, [files]);

  const refreshFiles = useCallback(async () => {
    try {
      const list = await tauriInvoke<FileEntry[]>('get_file_list');
      setFiles(list);
    } catch (e) {
      console.error('[useFileQueue] get_file_list error:', e);
    }
  }, []);

  const clearQueue = useCallback(async () => {
    try {
      await tauriInvoke('clear_queue');
      setFiles([]);
      setSelectedIndex(-1);
    } catch (e) {
      console.error('[useFileQueue] clear_queue error:', e);
    }
  }, []);

  return { files, setFiles, selectedIndex, setSelectedIndex, addFiles, removeFile, refreshFiles, clearQueue };
}
