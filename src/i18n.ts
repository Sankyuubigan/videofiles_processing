export type Locale = 'en' | 'ru';

const translations: Record<Locale, Record<string, string>> = {
  en: {
    // Tabs
    'tab.editor': 'Editor',
    'tab.compare': 'Compare',
    'tab.logs': 'Logs',
    'tab.settings': 'Settings',
    'tab.help': 'Help',

    // Editor
    'editor.select_files': '1. Select video files',
    'editor.select_btn': 'Select file(s)',
    'editor.output_dir': 'Output dir',
    'editor.in_queue': 'In queue: {count} files',
    'editor.drop_hint': 'Drag and drop files here or click "Select file(s)"',

    // Operation tabs
    'op.compress': 'Compress',
    'op.trim': 'Trim',
    'op.normalize': 'Normalize',

    // Process control
    'process.start': 'Start Compress',
    'process.batch_test': 'Batch Test',
    'process.batch_compress': 'Batch Compress',
    'process.cancel': 'Cancel',

    // Compare
    'compare.select_left': 'Select left video',
    'compare.change_left': 'Change left',
    'compare.select_right': 'Select right video',
    'compare.change_right': 'Change right',
    'compare.drop_target': 'Drop target:',
    'compare.drop_hint': 'Drag files to left or right area',
    'compare.left': 'Left',
    'compare.right': 'Right',
    'compare.left_video': 'Left video (drop here)',
    'compare.right_video': 'Right video (drop here)',
    'compare.play': 'Play',
    'compare.pause': 'Pause',

    // Settings
    'settings.ffmpeg': 'FFmpeg',
    'settings.ffmpeg_path': 'Path:',
    'settings.ffmpeg_not_found': 'Not found',
    'settings.ffmpeg_found': 'Found',
    'settings.download_ffmpeg': 'Download FFmpeg',
    'settings.compression': 'Compression Test Settings',
    'settings.vmaf_subsample': 'VMAF subsample:',
    'settings.chunk_count': 'Chunk count:',
    'settings.chunk_duration': 'Chunk duration:',
    'settings.locale': 'Language:',
    'settings.locale_en': 'English',
    'settings.locale_ru': 'Russian',
    'settings.save': 'Save Settings',
    'settings.saving': 'Saving...',

    // Logs
    'logs.no_logs': 'No logs yet...',
  },
  ru: {
    // Tabs
    'tab.editor': 'Редактор',
    'tab.compare': 'Сравнение',
    'tab.logs': 'Логи',
    'tab.settings': 'Настройки',
    'tab.help': 'Помощь',

    // Editor
    'editor.select_files': '1. Выберите видеофайлы',
    'editor.select_btn': 'Выбрать файл(ы)',
    'editor.output_dir': 'Папка вывода',
    'editor.in_queue': 'В очереди: {count} файлов',
    'editor.drop_hint': 'Перетащите файлы сюда или нажмите "Выбрать файл(ы)"',

    // Operation tabs
    'op.compress': 'Сжатие',
    'op.trim': 'Обрезка',
    'op.normalize': 'Нормализация',

    // Process control
    'process.start': 'Начать сжатие',
    'process.batch_test': 'Тест всех',
    'process.batch_compress': 'Сжать все',
    'process.cancel': 'Отмена',

    // Compare
    'compare.select_left': 'Выбрать левое видео',
    'compare.change_left': 'Изменить левое',
    'compare.select_right': 'Выбрать правое видео',
    'compare.change_right': 'Изменить правое',
    'compare.drop_target': 'Цель перетаскивания:',
    'compare.drop_hint': 'Перетащите файлы на левую или правую область',
    'compare.left': 'Левое',
    'compare.right': 'Правое',
    'compare.left_video': 'Левое видео (перетащите сюда)',
    'compare.right_video': 'Правое видео (перетащите сюда)',
    'compare.play': 'Воспроизвести',
    'compare.pause': 'Пауза',

    // Settings
    'settings.ffmpeg': 'FFmpeg',
    'settings.ffmpeg_path': 'Путь:',
    'settings.ffmpeg_not_found': 'Не найден',
    'settings.ffmpeg_found': 'Найден',
    'settings.download_ffmpeg': 'Скачать FFmpeg',
    'settings.compression': 'Настройки теста сжатия',
    'settings.vmaf_subsample': 'VMAF подвыборка:',
    'settings.chunk_count': 'Количество частей:',
    'settings.chunk_duration': 'Длительность части:',
    'settings.locale': 'Язык:',
    'settings.locale_en': 'Английский',
    'settings.locale_ru': 'Русский',
    'settings.save': 'Сохранить настройки',
    'settings.saving': 'Сохранение...',

    // Logs
    'logs.no_logs': 'Пока нет логов...',
  },
};

let currentLocale: Locale = 'en';

export function setLocale(locale: Locale) {
  currentLocale = locale;
}

export function getLocale(): Locale {
  return currentLocale;
}

export function t(key: string, params?: Record<string, string | number>): string {
  const dict = translations[currentLocale] || translations.en;
  let text = dict[key] || translations.en[key] || key;
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      text = text.replace(`{${k}}`, String(v));
    }
  }
  return text;
}
