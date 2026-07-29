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

  const removeFile = useCallback(async (index: number) => {
    try {
      console.log('[useFileQueue] Removing file at index:', index);
      await tauriInvoke('remove_file', { index });
      setFiles(prev => prev.filter((_, i) => i !== index));
      if (selectedIndex >= files.length - 1) {
        setSelectedIndex(Math.min(selectedIndex, files.length - 2));
      }
    } catch (e) {
      console.error('[useFileQueue] remove_file error:', e);
    }
  }, [selectedIndex, files.length]);

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
