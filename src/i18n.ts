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
    'editor.reset_output_dir': 'Reset',
    'editor.output_dir_default': 'same as source',
    'editor.clear_table': 'Clear table',
    'editor.in_queue': 'In queue: {count} files',
    'editor.drop_hint': 'Drag and drop files here or click "Select file(s)"',

    // Table
    'table.auto_test': 'Auto-test',
    'table.test_vmaf': 'Test VMAF',
    'table.test_ssim': 'Test SSIM',

    // Operation tabs
    'op.compress': 'Compress',
    'op.trim': 'Trim',
    'op.normalize': 'Normalize',
    'op.auto_crf': 'Auto CRF (SSIMULACRA2/VMAF target)',

    // Process control
    'process.start': 'Start Compress',
    'process.batch_test': 'Batch Test',
    'process.batch_compress': 'Batch Compress',
    'process.cancel': 'Cancel',
    'process.pause': 'Pause',
    'process.resume': 'Resume',
    'process.paused': 'Paused',
    'process.file': 'File:',

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
    'compare.volume': 'Volume',

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
    'settings.auto_skip': 'Auto Mode Skip',
    'settings.skip_min_diff': 'Min size reduction:',
    'settings.skip_min_crf': 'Skip if original CRF >=',
    'settings.vmaf_ignore_noise': 'Ignore Noise/Grain in VMAF',
    'settings.parallel_chunks': 'Parallel chunk encoding (faster tests)',
    'settings.about_title': 'About',
    'settings.about_name': 'Name:',
    'settings.about_version': 'Version:',
    'settings.support_title': 'Support the Project',
    'settings.support_desc': 'This project is developed by a single author. If the app is useful to you, you can thank the author and support the project:',
    'settings.support_link': 'Thank the author. Support the project →',

    // Logs
    'logs.no_logs': 'No logs yet...',
    'logs.copy': 'Copy',
    'logs.copied': 'Copied!',
    'logs.clear': 'Clear',

    // Preview
    'preview.gif': 'Thumbnails',
    'preview.title': 'Video thumbnails',
    'preview.generating': 'Generating thumbnails...',
    'preview.close': 'Close',
    'preview.usage': '5 random 3s clips from the middle of the video',

    // Help
    'help.columns': 'File Table Columns',
    'help.vfr_desc': '- Sometimes video has broken frames and needs repair for successful compression.',
    'help.vmaf_desc': '- Algorithm comparing original and estimated compression quality. Score in percent shows how much quality will be lost.',
    'help.crf_desc': '- Shows if the video was already compressed before.',
    'help.red_title': 'Red Color in Table',
    'help.red_est_size': 'If estimated size is highlighted red, the video is likely already compressed.',
    'help.red_crf': 'If CRF is red, the video was definitely compressed before. But if everything else is green, size can still decrease due to better preset or higher CRF value.',
    'help.params_title': 'Compression Parameters',
    'help.codec_label': 'Codec HEVC',
    'help.codec_desc': 'produces smaller files but compresses slower than AVC and uses more hardware resources during playback.',
    'help.preset_label': 'Preset',
    'help.preset_desc': 'affects quality after compression and compression time.',
    'help.coding_label': 'Coding type',
    'help.coding_desc': 'affects not only compression time but also the output file size.',
    'help.auto_title': 'Auto Mode (Auto CRF)',
    'help.auto_desc': 'When Auto CRF is enabled, the program automatically selects the best CRF value for each file to reach the target quality score.',
    'help.auto_how': 'How it works:',
    'help.auto_how_1': 'The program runs test encodes at different CRF values to find the highest CRF that still achieves the target score (SSIMULACRA2 77 for Animation/Rendered, VMAF 90 for LiveAction).',
    'help.auto_how_2': 'A higher CRF means more compression and smaller file size. Auto mode finds the most aggressive setting that keeps quality above your target.',
    'help.auto_how_3': 'If the target score is unreachable even at the maximum CRF for the codec, the file is skipped with a message like "target unreachable (best achieved: X.X)".',
    'help.skip_title': 'Auto Mode Skip Rules',
    'help.skip_desc': 'When Auto CRF is enabled, the program can also skip files that don\'t need compression. These rules are configurable in Settings > Auto Mode Skip:',
    'help.skip_min_size': 'Min size reduction — skips a file if the estimated size reduction is less than this percentage (default 5%). If compressing won\'t save much space, there\'s no point.',
    'help.skip_crf_ge': 'Skip if original CRF >= — skips a file if its original CRF is already at or above this value (default 18). Such videos are already well compressed and further compression would only waste time and reduce quality.',
    'help.skip_reported': 'Skipped files are reported in the progress bar with a "SKIP" message explaining the reason.',
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
    'editor.reset_output_dir': 'Сброс',
    'editor.output_dir_default': 'рядом с исходным',
    'editor.clear_table': 'Очистить таблицу',
    'editor.in_queue': 'В очереди: {count} файлов',
    'editor.drop_hint': 'Перетащите файлы сюда или нажмите "Выбрать файл(ы)"',

    // Table
    'table.auto_test': 'Автотест',
    'table.test_vmaf': 'Тест VMAF',
    'table.test_ssim': 'Тест SSIM',

    // Operation tabs
    'op.compress': 'Сжатие',
    'op.trim': 'Обрезка',
    'op.normalize': 'Нормализация',
    'op.auto_crf': 'Авто CRF (автоподбор по SSIMULACRA2/VMAF)',

    // Process control
    'process.start': 'Начать сжатие',
    'process.batch_test': 'Тест всех',
    'process.batch_compress': 'Сжать все',
    'process.cancel': 'Отмена',
    'process.pause': 'Пауза',
    'process.resume': 'Продолжить',
    'process.paused': 'Приостановлено',
    'process.file': 'Файл:',

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
    'compare.volume': 'Громкость',

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
    'settings.auto_skip': 'Пропуск в авторежиме',
    'settings.skip_min_diff': 'Мин. уменьшение размера:',
    'settings.skip_min_crf': 'Пропускать если CRF оригинала >=',
    'settings.vmaf_ignore_noise': 'Игнорировать шум/зерно в VMAF',
    'settings.parallel_chunks': 'Параллельное кодирование частей (быстрее тесты)',
    'settings.about_title': 'О программе',
    'settings.about_name': 'Название:',
    'settings.about_version': 'Версия:',
    'settings.support_title': 'Поддержка проекта',
    'settings.support_desc': 'Проект развивается одним автором. Если приложение вам полезно — вы можете отблагодарить автора, это поможет проекту:',
    'settings.support_link': 'Отблагодарить автора. Помощь проекту →',

    // Logs
    'logs.no_logs': 'Пока нет логов...',
    'logs.copy': 'Копировать',
    'logs.copied': 'Скопировано!',
    'logs.clear': 'Очистить',

    // Preview
    'preview.gif': 'Миниатюры',
    'preview.title': 'Миниатюры видео',
    'preview.generating': 'Генерация миниатюр...',
    'preview.close': 'Закрыть',
    'preview.usage': '5 случайных нарезок по 3 сек из середины видео',

    // Help
    'help.columns': 'Колонки таблицы',
    'help.vfr_desc': '— иногда видео содержит повреждённые кадры, и ему требуется починка для успешного сжатия.',
    'help.vmaf_desc': '— алгоритм сравнения качества сжатия оригинала и результата. Оценка в процентах показывает, сколько качества будет потеряно.',
    'help.crf_desc': '— показывает, было ли видео уже сжато ранее.',
    'help.red_title': 'Красный цвет в таблице',
    'help.red_est_size': 'Если расчётный размер подсвечен красным, видео, скорее всего, уже сжато.',
    'help.red_crf': 'Если CRF красный — видео точно уже сжимали. Но если всё остальное зелёное, размер всё равно может уменьшиться за счёт лучшего пресета или большего значения CRF.',
    'help.params_title': 'Параметры сжатия',
    'help.codec_label': 'Кодек HEVC',
    'help.codec_desc': 'даёт меньшие файлы, но сжимает медленнее, чем AVC, и требует больше ресурсов при воспроизведении.',
    'help.preset_label': 'Пресет',
    'help.preset_desc': 'влияет на качество после сжатия и на время сжатия.',
    'help.coding_label': 'Тип кодирования',
    'help.coding_desc': 'влияет не только на время сжатия, но и на размер выходного файла.',
    'help.auto_title': 'Авторежим (Авто CRF)',
    'help.auto_desc': 'Когда включён авторежим CRF, программа сама подбирает лучшее значение CRF для каждого файла, чтобы достичь целевой оценки качества.',
    'help.auto_how': 'Как это работает:',
    'help.auto_how_1': 'Программа выполняет тестовые кодирования с разными значениями CRF, чтобы найти максимальный CRF, при котором целевая оценка ещё достигается (SSIMULACRA2 77 для анимации и рендер-контента, VMAF 90 для живого видео).',
    'help.auto_how_2': 'Чем выше CRF, тем сильнее сжатие и меньше размер файла. Авторежим находит самую агрессивную настройку, при которой качество остаётся выше вашей цели.',
    'help.auto_how_3': 'Если целевая оценка недостижима даже при максимальном CRF для кодека, файл пропускается с сообщением вида «цель недостижима (лучшее достигнутое: X.X)».',
    'help.skip_title': 'Правила пропуска в авторежиме',
    'help.skip_desc': 'В авторежиме программа также может пропускать файлы, которые не нуждаются в сжатии. Правила настраиваются в Настройки > Пропуск в авторежиме:',
    'help.skip_min_size': 'Мин. уменьшение размера — файл пропускается, если расчётное уменьшение размера меньше этого процента (по умолчанию 5%). Если сжатие почти не экономит место, оно не имеет смысла.',
    'help.skip_crf_ge': 'Пропускать если CRF оригинала >= — файл пропускается, если его исходный CRF уже равен или больше этого значения (по умолчанию 18). Такие видео уже хорошо сжаты, дальнейшее сжатие только зря потратит время и ухудшит качество.',
    'help.skip_reported': 'Пропущенные файлы отмечаются в прогрессбаре сообщением «SKIP» с указанием причины.',
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