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

class AppState:
    """Хранит состояние UI и данных."""
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

APP_STATE = AppState()

def main(page: ft.Page):
    """Основная функция для построения и запуска Flet-приложения."""
    page.title = "Flet Video Compressor"
    page.window_width = 700
    page.window_height = 720
    page.padding = ft.padding.all(15)
    page.theme_mode = ft.ThemeMode.DARK

    # --- UI Элементы ---
    file_picker = ft.FilePicker(on_result=lambda e: handle_file_picked(e, page))
    page.overlay.append(file_picker)

    def on_drag_accept(e: ft.DragTargetAcceptEvent):
        if hasattr(e, 'files') and e.files:
            filepath = e.files[0].path
            handle_file_selected(filepath, page)
        e.control.border = None
        e.control.update()

    def on_drag_will_accept(e: ft.DragTargetAcceptEvent):
        e.control.border = ft.border.all(3, ft.colors.GREEN_ACCENT_400)
        e.control.update()

    def on_drag_leave(e: ft.DragTargetAcceptEvent):
        e.control.border = None
        e.control.update()

    drag_target_icon = ft.Icon(ft.icons.UPLOAD_FILE_ROUNDED, size=40, color=ft.colors.BLUE_GREY_300)
    drag_target_text = ft.Text("Перетащите видео сюда", color=ft.colors.BLUE_GREY_300, size=14)
    
    drag_target_container = ft.DragTarget(
        group="video_files",
        content=ft.Container(
            content=ft.Row([drag_target_icon, drag_target_text], alignment=ft.MainAxisAlignment.CENTER),
            width=float('inf'), height=100,
            bgcolor=ft.colors.with_opacity(0.05, ft.colors.WHITE12),
            border_radius=8, alignment=ft.alignment.center
        ),
        on_accept=on_drag_accept, on_will_accept=on_drag_will_accept, on_leave=on_drag_leave
    )

    btn_browse = ft.OutlinedButton("Обзор...", icon=ft.icons.FOLDER_OPEN, on_click=lambda _: file_picker.pick_files(
        dialog_title="Выберите видеофайл", allowed_extensions=list(OUTPUT_EXTENSIONS.keys())
    ))
    
    txt_selected_file_info = ft.Text("Файл не выбран", italic=True, size=12, color=ft.colors.BLUE_GREY_200)
    dd_output_ext = ft.Dropdown(
        label="Формат",
        options=[ft.dropdown.Option(key=k, text=f".{k.upper()}") for k in OUTPUT_EXTENSIONS.keys()],
        value=APP_STATE.output_extension_key, on_change=lambda e: handle_extension_change(e, page)
    )
    slider_crf_label = ft.Text(f"CRF: {APP_STATE.crf_value}", weight=ft.FontWeight.BOLD)
    slider_crf = ft.Slider(
        min=1, max=51, value=APP_STATE.crf_value, label="{value}", on_change=lambda e: handle_crf_change(e, page)
    )
    lbl_vfr_status = ft.Text("Починка VFR: Не определено", size=13)
    switch_force_vfr_fix = ft.Switch(label="Принудительная починка", value=APP_STATE.force_vfr_fix, on_change=lambda e: handle_force_fix_change(e, page))
    progress_bar = ft.ProgressBar(value=0, bar_height=8, color=ft.colors.AMBER, bgcolor=ft.colors.with_opacity(0.2, ft.colors.AMBER))
    lbl_status = ft.Text("Готов к работе.", size=13, weight=ft.FontWeight.W_500)
    btn_compress = ft.FilledButton("Сжать", icon=ft.icons.COMPRESS, on_click=lambda e: start_processing_thread(page), height=45, disabled=True)

    def show_snackbar(page_ref: ft.Page, message: str, color=ft.colors.GREEN, duration_ms=4000):
        page_ref.show_snack_bar(ft.SnackBar(ft.Text(message, weight=ft.FontWeight.BOLD), open=True, bgcolor=color, duration=duration_ms))

    def update_ui_after_file_selection(page_ref, filepath):
        APP_STATE.reset_file_specific_state()
        APP_STATE.input_filepath = filepath
        
        if filepath:
            txt_selected_file_info.value = os.path.basename(filepath)
            txt_selected_file_info.italic, txt_selected_file_info.color = False, ft.colors.GREEN_ACCENT_200
            btn_compress.disabled = False
            info, err = get_video_info(filepath)
            if err:
                show_snackbar(page_ref, f"Ошибка анализа: {err}", ft.colors.RED)
                lbl_vfr_status.value, lbl_vfr_status.color = "Ошибка", ft.colors.RED
            elif info:
                APP_STATE.video_duration_seconds = get_video_duration_seconds(info)
                if needs_vfr_fix(info):
                    lbl_vfr_status.value, lbl_vfr_status.color = "Рекомендуется!", ft.colors.ORANGE_ACCENT_400
                    APP_STATE.vfr_fix_recommended = True
                else:
                    lbl_vfr_status.value, lbl_vfr_status.color = "Не требуется", ft.colors.GREEN_ACCENT_400
        else:
            txt_selected_file_info.value, txt_selected_file_info.italic = "Файл не выбран", True
            txt_selected_file_info.color = ft.colors.BLUE_GREY_200
            btn_compress.disabled = True
            lbl_vfr_status.value, lbl_vfr_status.color = "Не определено", None
            progress_bar.value = 0
        page_ref.update(txt_selected_file_info, lbl_vfr_status, btn_compress, progress_bar)

    def handle_file_picked(e: ft.FilePickerResultEvent, page_ref: ft.Page):
        if e.files: update_ui_after_file_selection(page_ref, e.files[0].path)

    def handle_file_selected(filepath: str, page_ref: ft.Page):
        update_ui_after_file_selection(page_ref, filepath)

    def update_crf_slider(ext_key: str, slider: ft.Slider, label: ft.Text, page_ref: ft.Page):
        details = OUTPUT_EXTENSIONS.get(ext_key)
        if not details: return
        slider.min, slider.max, slider.divisions = details["crf_min"], details["crf_max"], details["crf_max"] - details["crf_min"]
        APP_STATE.crf_value = details["crf_default"]
        slider.value = APP_STATE.crf_value
        label.value = f"CRF: {APP_STATE.crf_value}"
        page_ref.update(slider, label)

    def handle_extension_change(e: ft.ControlEvent, page_ref: ft.Page):
        APP_STATE.output_extension_key = e.control.value
        update_crf_slider(APP_STATE.output_extension_key, slider_crf, slider_crf_label, page_ref)

    def handle_crf_change(e: ft.ControlEvent, page_ref: ft.Page):
        APP_STATE.crf_value = int(e.control.value)
        slider_crf_label.value = f"CRF: {APP_STATE.crf_value}"
        slider_crf_label.update()

    def handle_force_fix_change(e: ft.ControlEvent, page_ref: ft.Page):
        APP_STATE.force_vfr_fix = e.control.value

    def set_ui_processing_state(is_processing: bool, page_ref: ft.Page, operation_name=""):
        APP_STATE.is_processing = is_processing
        APP_STATE.current_operation_name = operation_name
        for ctrl in [btn_browse, dd_output_ext, slider_crf, switch_force_vfr_fix, btn_compress, drag_target_container]:
            ctrl.disabled = is_processing
        lbl_status.value = f"{operation_name}..." if is_processing else "Завершено."
        progress_bar.value = None if is_processing else 0
        page_ref.update(btn_browse, dd_output_ext, slider_crf, switch_force_vfr_fix, btn_compress, drag_target_container, lbl_status, progress_bar)

    def update_progress_ui(percent: int, page_ref: ft.Page):
        if not APP_STATE.is_processing: return
        progress_bar.value = percent / 100.0 if percent != -1 else None
        lbl_status.value = f"{APP_STATE.current_operation_name}: {percent}%" if percent != -1 else f"{APP_STATE.current_operation_name}..."
        page_ref.update(progress_bar, lbl_status)

    def _processing_target_func(page_ref: ft.Page):
        input_file = APP_STATE.input_filepath
        output_dir = os.path.dirname(input_file)
        base_name, ext = os.path.splitext(os.path.basename(input_file))
        temp_file = os.path.join(output_dir, f"{base_name}{TEMP_FIXED_VIDEO_SUFFIX}{ext}")
        final_file = os.path.join(output_dir, f"{base_name}{COMPRESSED_VIDEO_SUFFIX}.{APP_STATE.output_extension_key}")
        current_input, success, error_msg = input_file, True, ""

        if APP_STATE.force_vfr_fix or APP_STATE.vfr_fix_recommended:
            page_ref.run_thread_safe(lambda: set_ui_processing_state(True, page_ref, "Починка VFR"))
            success, error_msg = fix_vfr(input_file, temp_file, DEFAULT_FPS_FIX, DEFAULT_FIX_CRF_H264, DEFAULT_FIX_CRF_VP9, APP_STATE.output_extension_key, lambda p: page_ref.run_thread_safe(lambda: update_progress_ui(p, page_ref)), APP_STATE.video_duration_seconds)
            if success: current_input = temp_file

        if success:
            page_ref.run_thread_safe(lambda: set_ui_processing_state(True, page_ref, "Сжатие"))
            duration = APP_STATE.video_duration_seconds
            details = OUTPUT_EXTENSIONS[APP_STATE.output_extension_key]
            success, error_msg = compress_video(
                current_input, final_file, details, APP_STATE.crf_value,
                lambda p: page_ref.run_thread_safe(lambda: update_progress_ui(p, page_ref)),
                duration
            )

        if success:
            page_ref.run_thread_safe(lambda: show_snackbar(page_ref, f"Успешно! Сохранено: {final_file}"))
        else:
            page_ref.run_thread_safe(lambda: show_snackbar(page_ref, error_msg, ft.colors.RED))

        if os.path.exists(temp_file): os.remove(temp_file)
        page_ref.run_thread_safe(lambda: set_ui_processing_state(False, page_ref))
        page_ref.run_thread_safe(lambda: update_ui_after_file_selection(page_ref, None))

    def start_processing_thread(page_ref: ft.Page):
        if APP_STATE.is_processing: return
        if not APP_STATE.input_filepath:
            show_snackbar(page_ref, "Сначала выберите видеофайл!", ft.colors.YELLOW_ACCENT_700)
            return
        
        thread = threading.Thread(target=_processing_target_func, args=(page_ref,), daemon=True)
        thread.start()

    update_crf_slider(APP_STATE.output_extension_key, slider_crf, slider_crf_label, page)
    
    page.add(
        ft.Column([
            ft.Text("1. Выбор видеофайла", weight=ft.FontWeight.BOLD),
            drag_target_container,
            ft.Row([ft.Text("или"), btn_browse], alignment=ft.MainAxisAlignment.CENTER),
            txt_selected_file_info, ft.Divider(height=10),

            ft.Text("2. Настройки сжатия", weight=ft.FontWeight.BOLD),
            ft.Row([dd_output_ext, slider_crf_label], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            slider_crf, ft.Divider(height=10),

            ft.Text("3. Обработка VFR", weight=ft.FontWeight.BOLD),
            ft.Row([lbl_vfr_status, switch_force_vfr_fix], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Divider(height=10),
            
            ft.Text("4. Запуск и Прогресс", weight=ft.FontWeight.BOLD),
            btn_compress, progress_bar, lbl_status
        ], spacing=10)
    )
    page.update()

if __name__ == "__main__":
    if not os.path.exists(FFMPEG_PATH) or not os.path.exists(FFPROBE_PATH):
        print("ОШИБКА: ffmpeg или ffprobe не найдены. Проверьте пути в config.py.")
        print(f"Ожидаемый путь ffmpeg: {FFMPEG_PATH}")
        print(f"Ожидаемый путь ffprobe: {FFPROBE_PATH}")
        input("Нажмите Enter для выхода...")
    else:
        ft.app(target=main)