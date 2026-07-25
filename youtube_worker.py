from PySide6.QtCore import QThread, Signal
import os
import re
import json
import platform
import subprocess
import logging
from settings_manager import get_actual_ffmpeg_path
from yt_dlp_manager import get_yt_dlp_exe_path, get_deno_path

logger = logging.getLogger(__name__)

def _no_window_startupinfo():
    if platform.system() == "Windows":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE
        return si
    return None

_PROGRESS_RE = re.compile(
    r'\[download\]\s+([\d.]+)%\s+of\s+~?([\d.]+)\s*(\w+)\s+at\s+([\d.]+)\s*(\w+)'
)
_DEST_RE = re.compile(r'\[download\]\s+Destination:\s+(.+)')
_MERGE_RE = re.compile(r'\[Merger\]\s+Merging formats into "(.+)"')


class YoutubeDownloadWorker(QThread):
    progress_signal = Signal(str)
    percent_signal = Signal(int)
    finished_signal = Signal()
    error_signal = Signal(str)
    log_signal = Signal(str)

    def __init__(self, url, path, format_type='mp4', resolution=None,
                 auth_mode='none', browser_name=None, cookies_file=None):
        super().__init__()
        self.url = url
        self.path = path
        self.format_type = format_type
        self.resolution = resolution
        self.auth_mode = auth_mode
        self.browser_name = browser_name
        self.cookies_file = cookies_file

    def _build_base_args(self):
        exe = get_yt_dlp_exe_path()
        if not os.path.isfile(exe):
            raise FileNotFoundError(
                f"yt-dlp не найден: {exe}\n"
                "Установите или обновите yt-dlp в настройках."
            )

        args = [exe]

        res_str = f"[height<={self.resolution}]" if self.resolution else ""

        if self.format_type == 'mp4':
            fmt = (
                f'bestvideo[ext=mp4]{res_str}+bestaudio[ext=m4a]'
                f'/best[ext=mp4]{res_str}/best{res_str}/best'
            )
            args += ["--format", fmt, "--merge-output-format", "mp4"]
        elif self.format_type == 'mp3':
            fmt = "bestaudio/best"
            args += ["--format", fmt, "--audio-format", "mp3",
                     "--audio-quality", "192"]
        else:
            fmt = f'bestvideo{res_str}+bestaudio/best{res_str}/best'
            args += ["--format", fmt, "--merge-output-format", "mkv"]

        outtmpl = os.path.join(self.path, '%(title)s.%(ext)s')
        args += ["-o", outtmpl]

        ffmpeg_dir = os.path.dirname(get_actual_ffmpeg_path())
        if os.path.isdir(ffmpeg_dir):
            args += ["--ffmpeg-location", ffmpeg_dir]

        args += [
            "--no-playlist",
            "--socket-timeout", "60",
            "--retries", "10",
            "--quiet",
            "--no-warnings",
        ]

        if self.auth_mode == 'browser' and self.browser_name:
            args += ["--cookies-from-browser", self.browser_name]
            logger.info(f"Cookies из браузера: {self.browser_name}")
            self.log_signal.emit(f"[INFO] Cookies из браузера: {self.browser_name}")
        elif self.auth_mode == 'file' and self.cookies_file:
            args += ["--cookies", self.cookies_file]
            logger.info(f"Cookies из файла: {self.cookies_file}")
            self.log_signal.emit(f"[INFO] Cookies из файла: {self.cookies_file}")
        else:
            self.log_signal.emit("[INFO] Скачивание без авторизации")

        return args

    def _setup_deno(self):
        deno_path = get_deno_path()
        deno_dir = os.path.dirname(deno_path)
        if os.path.isfile(deno_path) and deno_dir not in os.environ.get("PATH", ""):
            os.environ["PATH"] = deno_dir + os.pathsep + os.environ.get("PATH", "")
            self.log_signal.emit("[INFO] Deno добавлен в PATH")

    def run(self):
        try:
            exe = get_yt_dlp_exe_path()
            self.log_signal.emit(f"[DEBUG] yt-dlp: {exe}")
            logger.info(f"[YoutubeWorker] yt-dlp exe: {exe}")

            self._setup_deno()

            args = self._build_base_args()

            self.log_signal.emit("--- Анализ видео ---")
            info_args = args + ["--dump-json", "--no-download", self.url]
            logger.info(f"[YoutubeWorker] Анализ: {' '.join(info_args)}")

            info_proc = subprocess.run(
                info_args,
                capture_output=True, text=True, timeout=120,
                startupinfo=_no_window_startupinfo()
            )

            if info_proc.returncode != 0:
                err = info_proc.stderr.strip() or info_proc.stdout.strip() or "Неизвестная ошибка"
                logger.error(f"[YoutubeWorker] Ошибка анализа: {err}")
                self.error_signal.emit(f"Не удалось получить информацию о видео:\n{err}")
                return

            try:
                info = json.loads(info_proc.stdout)
            except json.JSONDecodeError:
                logger.error("[YoutubeWorker] Не удалось распарсить JSON")
                self.error_signal.emit("Ошибка: yt-dlp вернул некорректные данные")
                return

            title = info.get("title", "Video")
            self.log_signal.emit(f"Название: {title}")
            logger.info(f"[YoutubeWorker] Видео: {title}")

            self.log_signal.emit("\n--- Начало загрузки ---")
            logger.info(f"[YoutubeWorker] Загрузка в: {self.path}")

            dl_args = args + ["--newline", self.url]
            logger.info(f"[YoutubeWorker] Загрузка: yt-dlp {' '.join(dl_args[1:])}")

            self.percent_signal.emit(0)
            self.progress_signal.emit("Скачивание: 0%")

            proc = subprocess.Popen(
                dl_args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                startupinfo=_no_window_startupinfo()
            )

            last_percent = -1
            ffmpeg_phase = False

            for line in proc.stdout:
                line = line.rstrip("\n\r")
                if not line:
                    continue

                m = _PROGRESS_RE.search(line)
                if m:
                    ffmpeg_phase = False
                    pct = int(float(m.group(1)))
                    size = m.group(2)
                    size_unit = m.group(3)
                    speed = m.group(4)
                    speed_unit = m.group(5)

                    if pct != last_percent:
                        last_percent = pct
                        self.percent_signal.emit(pct)

                    self.progress_signal.emit(
                        f"Скачивание: {pct}% ({size} {size_unit} at {speed} {speed_unit})"
                    )
                    continue

                if "[download] 100%" in line and not ffmpeg_phase:
                    self.percent_signal.emit(100)
                    self.progress_signal.emit("Обработка (ffmpeg)...")
                    self.log_signal.emit("Загрузка завершена. Склейка (если нужно)...")
                    ffmpeg_phase = True
                    continue

                if _MERGE_RE.search(line):
                    self.log_signal.emit(line.strip())
                    continue

                if _DEST_RE.search(line):
                    self.log_signal.emit(line.strip())
                    continue

                if line.strip():
                    self.log_signal.emit(line.strip())

            proc.wait()

            if proc.returncode != 0:
                stderr_text = proc.stderr.read().strip() if proc.stderr else ""
                err = stderr_text or "yt-dlp завершился с ошибкой"
                logger.error(f"[YoutubeWorker] Ошибка загрузки (code={proc.returncode}): {err}")
                self.error_signal.emit(err)
                return

            logger.info("[YoutubeWorker] Загрузка завершена успешно")
            self.percent_signal.emit(100)
            self.progress_signal.emit("Готово")
            self.finished_signal.emit()

        except FileNotFoundError as e:
            logger.error(f"[YoutubeWorker] yt-dlp не найден: {e}")
            self.error_signal.emit(str(e))
        except subprocess.TimeoutExpired:
            logger.error("[YoutubeWorker] Таймаут загрузки")
            self.error_signal.emit("Превышен таймаут загрузки (120 сек)")
        except Exception as e:
            logger.error(f"[YoutubeWorker] Ошибка: {e}", exc_info=True)
            self.error_signal.emit(str(e))
