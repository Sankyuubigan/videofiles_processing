# main.py
import flet as ft
import os
import threading

from config import (
    OUTPUT_EXTENSIONS, DEFAULT_OUTPUT_EXTENSION_KEY,
    DEFAULT_FPS_FIX, DEFAULT_FIX_CRF_H264, DEFAULT_FIX_CRF_VP9,
    TEMP_FIXED_VIDEO_SUFFIX, COMPRESSED_VIDEO_SUFFIX,
    FFMPEG_PATH, FFPROBE_PATH
)
from ffmpeg_utils import (
    get_video_info, needs_vfr_fix, get_video_duration_seconds,
    fix_vfr, compress_video
)
from ui import build_ui

class AppState:
    """Хранит состояние данных приложения."""
    def __init__(self):
        self.input_filepath = None
        self.output_extension_key = DEFAULT_OUTPUT_EXTENSION_KEY
        self.crf_value = OUTPUT_EXTENSIONS[DEFAULT_OUTPUT_EXTENSION_KEY]["crf_default"]
        self.force_vfr_fix = False
        self.vfr_fix_recommended = False
        self.is_processing = False
        self.video_duration_seconds = None
        self.current_operation_name = ""

    def reset_file_specific_state(self):
        self.input_filepath = None
        self.vfr_fix_recommended = False
        self.video_duration_seconds = None

    def get_initial_ui_state(self):
        """Возвращает словарь с начальными значениями для UI."""
        return {
            "output_extension_key": self.output_extension_key,
            "crf_value": self.crf_value,
            "force_vfr_fix": self.force_vfr_fix,
        }

class AppController:
    """Управляет состоянием приложения и взаимодействием с UI."""
    def __init__(self, page: ft.Page):
        self.page = page
        self.state = AppState()
        self.controls = None  # Будет заполнено функцией build_ui

    def initialize(self):
        """Основной метод для инициализации приложения."""
        self.page.title = "Flet Video Compressor"
        self.page.window_width = 700
        self.page.window_height = 720
        self.page.padding = ft.padding.all(15)
        self.page.theme_mode = ft.ThemeMode.DARK

        handlers = {
            "on_file_picked": self.handle_file_picked,
            "on_drag_accept": self.handle_drag_accept,
            "on_drag_will_accept": self.handle_drag_will_accept,
            "on_drag_leave": self.handle_drag_leave,
            "on_extension_change": self.handle_extension_change,
            "on_crf_change": self.handle_crf_change,
            "on_force_fix_change": self.handle_force_fix_change,
            "on_compress_click": self.start_processing_thread,
        }

        self.controls = build_ui(self.page, handlers, self.state.get_initial_ui_state())
        self.page.update()

    # --- Методы обновления UI ---
    
    def show_snackbar(self, message: str, color=ft.Colors.GREEN, duration_ms=4000):
        self.page.show_snack_bar(ft.SnackBar(ft.Text(message, weight=ft.FontWeight.BOLD), open=True, bgcolor=color, duration=duration_ms))

    def update_ui_after_file_selection(self, filepath):
        self.state.reset_file_specific_state()
        self.state.input_filepath = filepath
        
        if filepath:
            self.controls.txt_selected_file_info.value = os.path.basename(filepath)
            self.controls.txt_selected_file_info.italic, self.controls.txt_selected_file_info.color = False, ft.Colors.GREEN_ACCENT_200
            self.controls.btn_compress.disabled = False
            info, err = get_video_info(filepath)
            if err:
                self.show_snackbar(f"Ошибка анализа: {err}", ft.Colors.RED)
                self.controls.lbl_vfr_status.value, self.controls.lbl_vfr_status.color = "Ошибка", ft.Colors.RED
            elif info:
                self.state.video_duration_seconds = get_video_duration_seconds(info)
                if needs_vfr_fix(info):
                    self.controls.lbl_vfr_status.value, self.controls.lbl_vfr_status.color = "Рекомендуется!", ft.Colors.ORANGE_ACCENT_400
                    self.state.vfr_fix_recommended = True
                else:
                    self.controls.lbl_vfr_status.value, self.controls.lbl_vfr_status.color = "Не требуется", ft.Colors.GREEN_ACCENT_400
        else:
            self.controls.txt_selected_file_info.value, self.controls.txt_selected_file_info.italic = "Файл не выбран", True
            self.controls.txt_selected_file_info.color = ft.Colors.BLUE_GREY_200
            self.controls.btn_compress.disabled = True
            self.controls.lbl_vfr_status.value, self.controls.lbl_vfr_status.color = "Не определено", None
            self.controls.progress_bar.value = 0
        
        self.page.update(self.controls.txt_selected_file_info, self.controls.lbl_vfr_status, self.controls.btn_compress, self.controls.progress_bar)

    def update_crf_slider(self, ext_key: str):
        details = OUTPUT_EXTENSIONS.get(ext_key)
        if not details: return
        slider = self.controls.slider_crf
        label = self.controls.slider_crf_label
        
        slider.min, slider.max, slider.divisions = details["crf_min"], details["crf_max"], details["crf_max"] - details["crf_min"]
        self.state.crf_value = details["crf_default"]
        slider.value = self.state.crf_value
        label.value = f"CRF: {self.state.crf_value}"
        self.page.update(slider, label)

    def set_ui_processing_state(self, is_processing: bool, operation_name=""):
        self.state.is_processing = is_processing
        self.state.current_operation_name = operation_name
        
        controls_to_toggle = [
            self.controls.btn_browse, self.controls.dd_output_ext, self.controls.slider_crf, 
            self.controls.switch_force_vfr_fix, self.controls.btn_compress, self.controls.drag_target_container
        ]
        for ctrl in controls_to_toggle:
            ctrl.disabled = is_processing
            
        self.controls.lbl_status.value = f"{operation_name}..." if is_processing else "Завершено."
        self.controls.progress_bar.value = None if is_processing else 0
        
        self.page.update(*controls_to_toggle, self.controls.lbl_status, self.controls.progress_bar)

    def update_progress_ui(self, percent: int):
        if not self.state.is_processing: return
        self.controls.progress_bar.value = percent / 100.0 if percent != -1 else None
        self.controls.lbl_status.value = f"{self.state.current_operation_name}: {percent}%" if percent != -1 else f"{self.state.current_operation_name}..."
        self.page.update(self.controls.progress_bar, self.controls.lbl_status)

    # --- Обработчики событий ---

    def handle_file_picked(self, e: ft.FilePickerResultEvent):
        if e.files:
            self.update_ui_after_file_selection(e.files.path)

    def handle_drag_accept(self, e):
        filepath = e.src
        if filepath:
            self.update_ui_after_file_selection(filepath)
        e.control.border = None
        e.control.update()

    def handle_drag_will_accept(self, e):
        e.control.border = ft.border.all(3, ft.Colors.GREEN_ACCENT_400) if e.data == "true" else ft.border.all(3, ft.Colors.RED)
        e.control.update()

    def handle_drag_leave(self, e):
        e.control.border = None
        e.control.update()

    def handle_extension_change(self, e: ft.ControlEvent):
        self.state.output_extension_key = e.control.value
        self.update_crf_slider(self.state.output_extension_key)

    def handle_crf_change(self, e: ft.ControlEvent):
        self.state.crf_value = int(e.control.value)
        self.controls.slider_crf_label.value = f"CRF: {self.state.crf_value}"
        self.controls.slider_crf_label.update()

    def handle_force_fix_change(self, e: ft.ControlEvent):
        self.state.force_vfr_fix = e.control.value

    # --- Логика обработки ---

    def _processing_target_func(self):
        input_file = self.state.input_filepath
        output_dir = os.path.dirname(input_file)
        base_name, ext = os.path.splitext(os.path.basename(input_file))
        temp_file = os.path.join(output_dir, f"{base_name}{TEMP_FIXED_VIDEO_SUFFIX}{ext}")
        final_file = os.path.join(output_dir, f"{base_name}{COMPRESSED_VIDEO_SUFFIX}.{self.state.output_extension_key}")
        current_input, success, error_msg = input_file, True, ""

        if self.state.force_vfr_fix or self.state.vfr_fix_recommended:
            self.page.run_thread_safe(lambda: self.set_ui_processing_state(True, "Починка VFR"))
            success, error_msg = fix_vfr(
                input_file, temp_file, DEFAULT_FPS_FIX, DEFAULT_FIX_CRF_H264, DEFAULT_FIX_CRF_VP9, 
                self.state.output_extension_key, 
                lambda p: self.page.run_thread_safe(lambda: self.update_progress_ui(p)), 
                self.state.video_duration_seconds
            )
            if success: current_input = temp_file

        if success:
            self.page.run_thread_safe(lambda: self.set_ui_processing_state(True, "Сжатие"))
            details = OUTPUT_EXTENSIONS[self.state.output_extension_key]
            success, error_msg = compress_video(
                current_input, final_file, details, self.state.crf_value,
                lambda p: self.page.run_thread_safe(lambda: self.update_progress_ui(p)),
                self.state.video_duration_seconds
            )

        if success:
            self.page.run_thread_safe(lambda: self.show_snackbar(f"Успешно! Сохранено: {final_file}"))
        else:
            self.page.run_thread_safe(lambda: self.show_snackbar(error_msg, ft.Colors.RED))

        if os.path.exists(temp_file): os.remove(temp_file)
        self.page.run_thread_safe(lambda: self.set_ui_processing_state(False))
        self.page.run_thread_safe(lambda: self.update_ui_after_file_selection(None))

    def start_processing_thread(self, e=None):
        if self.state.is_processing: return
        if not self.state.input_filepath:
            self.show_snackbar("Сначала выберите видеофайл!", ft.Colors.YELLOW_ACCENT_700)
            return
        
        thread = threading.Thread(target=self._processing_target_func, daemon=True)
        thread.start()

def main(page: ft.Page):
    """Точка входа для Flet приложения."""
    controller = AppController(page)
    controller.initialize()

if __name__ == "__main__":
    if not os.path.exists(FFMPEG_PATH) or not os.path.exists(FFPROBE_PATH):
        print("ОШИБКА: ffmpeg или ffprobe не найдены. Проверьте пути в config.py.")
        print(f"Ожидаемый путь ffmpeg: {FFMPEG_PATH}")
        print(f"Ожидаемый путь ffprobe: {FFPROBE_PATH}")
        input("Нажмите Enter для выхода...")
    else:
        ft.app(target=main)