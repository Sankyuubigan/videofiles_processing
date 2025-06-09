# main.py
import flet as ft
import os
import platform # Для определения ОС в Drag-and-Drop
import shutil # Не используется пока, но может пригодиться для работы с файлами
import threading
import time # Для имитации задержек и тестирования UI

from config import (
    OUTPUT_EXTENSIONS, DEFAULT_OUTPUT_EXTENSION_KEY,
    DEFAULT_FPS_FIX, DEFAULT_FIX_CRF_H264, DEFAULT_FIX_CRF_VP9,
    TEMP_FIXED_VIDEO_SUFFIX, COMPRESSED_VIDEO_SUFFIX
)
from ffmpeg_utils import (
    get_video_info, needs_vfr_fix, get_video_duration_seconds,
    fix_vfr, compress_video
)

# --- Состояние приложения ---
class AppState:
    def __init__(self):
        self.input_filepath = None
        self.output_extension_key = DEFAULT_OUTPUT_EXTENSION_KEY
        # CRF берем из дефолтов для выбранного расширения
        self.crf_value = OUTPUT_EXTENSIONS[DEFAULT_OUTPUT_EXTENSION_KEY]["crf_default"]
        self.force_vfr_fix = False
        self.vfr_fix_recommended = False
        self.is_processing = False
        self.video_duration_seconds = None
        self.current_operation_name = "" # Для отображения в статус баре

    def reset_file_specific_state(self):
        self.input_filepath = None
        self.vfr_fix_recommended = False
        self.video_duration_seconds = None
        # self.force_vfr_fix = False # Не сбрасываем принудительную починку, это выбор пользователя

APP_STATE = AppState()

# --- Основная функция приложения Flet ---
def main(page: ft.Page):
    page.title = "Flet Video Compressor"
    page.vertical_alignment = ft.MainAxisAlignment.START
    page.window_width = 700
    page.window_height = 700 # Немного увеличим высоту
    page.spacing = 0 # Уберем глобальный spacing, будем управлять через margin/padding контролов
    page.padding = ft.padding.all(10)


    # --- UI Элементы ---
    # FilePicker должен быть в overlay
    file_picker = ft.FilePicker(on_result=lambda e: handle_file_picked(e, page))
    page.overlay.append(file_picker)

    # --- Drag and Drop Area ---
    def on_drag_accept(e: ft.DragTargetAcceptEvent):
        if e.data == "true" and e.src_address: # Проверяем, что данные пришли
            if hasattr(e.page.web_event_data, "files") and e.page.web_event_data.files:
                 # Веб-версия Flet (иногда и десктоп, если используется webview)
                filepath = e.page.web_event_data.files[0].path
            elif e.src_address.startswith("file://"): # Десктопные сборки
                filepath_uri = e.src_address
                # Обработка URI
                if platform.system() == "Windows":
                    filepath = filepath_uri[8:] # Убираем 'file:///' для Windows
                    if filepath.startswith('/') and len(filepath) > 2 and filepath[2] == ':': # путь типа /C:/...
                        filepath = filepath[1:]
                else: # Linux, macOS
                    filepath = filepath_uri[7:] # Убираем 'file://'
                filepath = os.path.normpath(filepath)
            else: # Не удалось определить путь
                filepath = None
                show_snackbar(page, "Не удалось получить путь к файлу из Drag-and-Drop.", ft.colors.RED)

            if filepath:
                print(f"Dropped file path (processed): {filepath}")
                file_ext = os.path.splitext(filepath)[1].lower().replace('.', '')
                if os.path.isfile(filepath) and file_ext in OUTPUT_EXTENSIONS.keys():
                    handle_file_selected(filepath, page)
                else:
                    show_snackbar(page, f"Неверный тип файла или файл не найден: {filepath}", ft.colors.RED)
        else:
            print(f"Drag accept event, but no valid data: {e.data}, src: {e.src_address}")
        e.control.border = ft.border.all(2, ft.colors.with_opacity(0.3, ft.colors.BLUE_GREY_700)) # Возвращаем обычную границу
        e.control.update()

    def on_drag_will_accept(e: ft.DragTargetAcceptEvent):
        e.control.border = ft.border.all(3, ft.colors.GREEN_ACCENT_400) # Подсветка при наведении
        e.control.update()

    def on_drag_leave(e: ft.DragTargetAcceptEvent):
        e.control.border = ft.border.all(2, ft.colors.with_opacity(0.3, ft.colors.BLUE_GREY_700)) # Обычная граница
        e.control.update()

    drag_target_icon = ft.Icon(ft.icons.UPLOAD_FILE_ROUNDED, size=40, color=ft.colors.BLUE_GREY_300)
    drag_target_text = ft.Text("Перетащите видео сюда или нажмите 'Обзор'", color=ft.colors.BLUE_GREY_300, size=14)
    
    drag_target_container = ft.DragTarget(
        group="video_files_main", # Уникальная группа
        content=ft.Container(
            content=ft.Column(
                [drag_target_icon, drag_target_text],
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=10,
            ),
            width=float('inf'), # Растягиваем на всю доступную ширину
            height=130,
            bgcolor=ft.colors.with_opacity(0.03, ft.colors.WHITE12),
            border_radius=8,
            border=ft.border.all(2, ft.colors.with_opacity(0.3, ft.colors.BLUE_GREY_700)),
            alignment=ft.alignment.center,
            padding=ft.padding.all(10)
        ),
        on_accept=on_drag_accept,
        on_will_accept=on_drag_will_accept,
        on_leave=on_drag_leave
    )

    btn_browse = ft.ElevatedButton(
        "Обзор...",
        icon=ft.icons.FOLDER_OPEN,
        on_click=lambda _: file_picker.pick_files(
            dialog_title="Выберите видеофайл",
            allowed_extensions=list(OUTPUT_EXTENSIONS.keys()),
            allow_multiple=False
        ),
        height=40
    )
    
    txt_selected_file_info = ft.Text("Файл не выбран", italic=True, size=12, color=ft.colors.BLUE_GREY_200)

    # --- Настройки сжатия ---
    dd_output_ext = ft.Dropdown(
        label="Формат вывода",
        options=[ft.dropdown.Option(key=ext_key, text=f".{ext_key.upper()} ({details['codec']})") for ext_key, details in OUTPUT_EXTENSIONS.items()],
        value=APP_STATE.output_extension_key,
        on_change=lambda e: handle_extension_change(e, page),
        height=50,
        # dense=True, # Уменьшает высоту
        content_padding=ft.padding.symmetric(vertical=5)
    )

    slider_crf_label = ft.Text(f"CRF: {APP_STATE.crf_value}", weight=ft.FontWeight.BOLD)
    slider_crf = ft.Slider(
        min=OUTPUT_EXTENSIONS[APP_STATE.output_extension_key]["crf_min"],
        max=OUTPUT_EXTENSIONS[APP_STATE.output_extension_key]["crf_max"],
        divisions=OUTPUT_EXTENSIONS[APP_STATE.output_extension_key]["crf_max"] - OUTPUT_EXTENSIONS[APP_STATE.output_extension_key]["crf_min"],
        value=APP_STATE.crf_value,
        label="{value}", # Метка будет обновляться при перетаскивании
        on_change=lambda e: handle_crf_change(e, page),
    )
    # update_crf_slider_for_extension_key(APP_STATE.output_extension_key, slider_crf, slider_crf_label, page) # Инициализация

    # --- Настройки VFR ---
    lbl_vfr_status = ft.Text("Починка VFR: Не определено", weight=ft.FontWeight.NORMAL, size=13)
    switch_force_vfr_fix = ft.Switch(
        label="Принудительная починка VFR",
        label_position=ft.LabelPosition.LEFT,
        value=APP_STATE.force_vfr_fix,
        on_change=lambda e: handle_force_fix_change(e, page)
    )

    # --- Прогресс и статус ---
    progress_bar = ft.ProgressBar(width=float('inf'), value=0, bar_height=10, color=ft.colors.AMBER, bgcolor=ft.colors.with_opacity(0.2, ft.colors.AMBER))
    lbl_status = ft.Text("Готов к работе.", italic=True, size=13, weight=ft.FontWeight.W_500)
    
    btn_compress = ft.FilledButton( # FilledButton выглядит солиднее для основной кнопки
        "Сжать видео",
        icon=ft.icons.COMPRESS_ROUNDED,
        on_click=lambda e: start_processing_thread(page),
        height=50,
        width=float('inf'), # Растягиваем кнопку
        disabled=True # Изначально неактивна, пока не выбран файл
    )

    # --- Контейнеры для секций ---
    section_file_selection = ft.Container(
        ft.Column([
            ft.Text("1. Выбор видеофайла", weight=ft.FontWeight.BOLD, size=16),
            drag_target_container,
            ft.Row([btn_browse, ft.Text("или", style=ft.TextStyle(color=ft.colors.BLUE_GREY_200, italic=True))], alignment=ft.MainAxisAlignment.CENTER, vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=10),
            txt_selected_file_info,
        ], spacing=8),
        padding=ft.padding.only(bottom=10),
        border=ft.border.only(bottom=ft.BorderSide(1, ft.colors.with_opacity(0.1, ft.colors.WHITE12)))
    )

    section_settings = ft.Container(
        ft.Column([
            ft.Text("2. Настройки сжатия", weight=ft.FontWeight.BOLD, size=16),
            dd_output_ext,
            ft.Text("Качество (CRF): чем меньше значение, тем лучше качество и больше файл.", size=12, color=ft.colors.BLUE_GREY_200),
            ft.Row([slider_crf_label, slider_crf], vertical_alignment=ft.CrossAxisAlignment.CENTER),
        ], spacing=8),
        padding=ft.padding.only(bottom=10, top=10),
        border=ft.border.only(bottom=ft.BorderSide(1, ft.colors.with_opacity(0.1, ft.colors.WHITE12)))
    )
    
    section_vfr_fix = ft.Container(
        ft.Column([
            ft.Text("3. Обработка VFR (проблемная частота кадров)", weight=ft.FontWeight.BOLD, size=16),
            lbl_vfr_status,
            switch_force_vfr_fix,
        ], spacing=8),
        padding=ft.padding.only(bottom=10, top=10),
        border=ft.border.only(bottom=ft.BorderSide(1, ft.colors.with_opacity(0.1, ft.colors.WHITE12)))
    )

    section_action_progress = ft.Container(
         ft.Column([
            ft.Text("4. Запуск и Прогресс", weight=ft.FontWeight.BOLD, size=16),
            btn_compress,
            progress_bar,
            lbl_status,
        ], spacing=10, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
        padding=ft.padding.only(top=10)
    )


    # --- Обработчики и логика UI ---
    def show_snackbar(page_ref: ft.Page, message: str, color=ft.colors.GREEN, duration_ms=3000):
        # Flet сам управляет очередью снекбаров
        page_ref.show_snack_bar(ft.SnackBar(ft.Text(message, weight=ft.FontWeight.BOLD), open=True, bgcolor=color, duration=duration_ms))

    def update_ui_after_file_selection(page_ref: ft.Page, filepath: str = None):
        APP_STATE.input_filepath = filepath
        
        if filepath:
            txt_selected_file_info.value = f"Выбран: {os.path.basename(filepath)}"
            txt_selected_file_info.italic = False
            txt_selected_file_info.color = ft.colors.GREEN_ACCENT_200
            drag_target_text.value = os.path.basename(filepath)
            drag_target_text.color = ft.colors.WHITE
            drag_target_icon.name = ft.icons.MOVIE_ROUNDED
            btn_compress.disabled = False

            info, err = get_video_info(filepath)
            if err:
                show_snackbar(page_ref, f"Ошибка анализа: {err}", ft.colors.RED)
                lbl_vfr_status.value = "Починка VFR: Ошибка"
                lbl_vfr_status.color = ft.colors.RED_ACCENT_700
                APP_STATE.vfr_fix_recommended = False
                APP_STATE.video_duration_seconds = None
            elif info:
                APP_STATE.video_duration_seconds = get_video_duration_seconds(info)
                if needs_vfr_fix(info):
                    lbl_vfr_status.value = "Починка VFR: Рекомендуется!"
                    lbl_vfr_status.color = ft.colors.ORANGE_ACCENT_400
                    APP_STATE.vfr_fix_recommended = True
                else:
                    lbl_vfr_status.value = "Починка VFR: Не требуется"
                    lbl_vfr_status.color = ft.colors.GREEN_ACCENT_400
                    APP_STATE.vfr_fix_recommended = False
        else: # Файл не выбран или сброшен
            txt_selected_file_info.value = "Файл не выбран"
            txt_selected_file_info.italic = True
            txt_selected_file_info.color = ft.colors.BLUE_GREY_200
            drag_target_text.value = "Перетащите видео сюда или нажмите 'Обзор'"
            drag_target_text.color = ft.colors.BLUE_GREY_300
            drag_target_icon.name = ft.icons.UPLOAD_FILE_ROUNDED
            lbl_vfr_status.value = "Починка VFR: Не определено"
            lbl_vfr_status.color = None
            btn_compress.disabled = True
            APP_STATE.vfr_fix_recommended = False
            APP_STATE.video_duration_seconds = None
            progress_bar.value = 0 # Сброс прогресса

        # Обновляем все затронутые контролы
        txt_selected_file_info.update()
        drag_target_text.update()
        drag_target_icon.update()
        lbl_vfr_status.update()
        btn_compress.update()
        progress_bar.update()
        # page_ref.update() # Не всегда нужен полный page.update()

    def handle_file_picked(e: ft.FilePickerResultEvent, page_ref: ft.Page):
        if e.files and len(e.files) > 0:
            update_ui_after_file_selection(page_ref, e.files[0].path)
        else:
            update_ui_after_file_selection(page_ref, None)

    def handle_file_selected(filepath: str, page_ref: ft.Page): # Вызывается из Drag-n-Drop
        update_ui_after_file_selection(page_ref, filepath)

    def update_crf_slider_for_extension_key(ext_key: str, slider: ft.Slider, label: ft.Text, page_ref: ft.Page):
        ext_details = OUTPUT_EXTENSIONS.get(ext_key)
        if not ext_details: return

        slider.min = ext_details["crf_min"]
        slider.max = ext_details["crf_max"]
        slider.divisions = ext_details["crf_max"] - ext_details["crf_min"]
        
        # Устанавливаем значение CRF, если текущее выходит за новые рамки или для инициализации
        if APP_STATE.crf_value < slider.min or APP_STATE.crf_value > slider.max or \
           (hasattr(slider, '_initial_update') and slider._initial_update): # Флаг для первой инициализации
            APP_STATE.crf_value = ext_details["crf_default"]
            if hasattr(slider, '_initial_update'): del slider._initial_update

        slider.value = APP_STATE.crf_value
        label.value = f"CRF: {APP_STATE.crf_value}"
        
        if page_ref.controls_initialized:
            slider.update()
            label.update()

    def handle_extension_change(e: ft.ControlEvent, page_ref: ft.Page):
        APP_STATE.output_extension_key = e.control.value
        update_crf_slider_for_extension_key(APP_STATE.output_extension_key, slider_crf, slider_crf_label, page_ref)

    def handle_crf_change(e: ft.ControlEvent, page_ref: ft.Page):
        APP_STATE.crf_value = int(e.control.value)
        slider_crf_label.value = f"CRF: {APP_STATE.crf_value}"
        if page_ref.controls_initialized:
            slider_crf_label.update()

    def handle_force_fix_change(e: ft.ControlEvent, page_ref: ft.Page):
        APP_STATE.force_vfr_fix = e.control.value

    def set_ui_processing_state(is_processing: bool, page_ref: ft.Page, operation_name=""):
        APP_STATE.is_processing = is_processing
        APP_STATE.current_operation_name = operation_name

        # Блокируем/разблокируем контролы
        controls_to_disable = [btn_browse, dd_output_ext, slider_crf, switch_force_vfr_fix, btn_compress]
        for ctrl in controls_to_disable:
            ctrl.disabled = is_processing
            if page_ref.controls_initialized: ctrl.update()
        
        drag_target_container.disabled = is_processing # Блокируем DragTarget

        if is_processing:
            progress_bar.value = None # Неопределенный прогресс (крутилка)
            lbl_status.value = f"{operation_name}..." if operation_name else "Обработка..."
        else:
            progress_bar.value = 0 # Сброс до 0%
            lbl_status.value = "Завершено." if APP_STATE.current_operation_name else "Готов к работе."
        
        if page_ref.controls_initialized:
            drag_target_container.update()
            progress_bar.update()
            lbl_status.update()
            page_ref.update()


    def update_progress_ui(percent: int, page_ref: ft.Page):
        """Обновляет ProgressBar и статус из основного потока Flet."""
        if not APP_STATE.is_processing: return # Если обработка уже завершена/отменена

        if percent == -1:
            progress_bar.value = None # Неопределенный
            lbl_status.value = f"{APP_STATE.current_operation_name}: обрабатывается..."
        elif percent == 100:
            progress_bar.value = 1.0
            # Статус обновится после завершения операции
        else:
            progress_bar.value = percent / 100.0
            lbl_status.value = f"{APP_STATE.current_operation_name}: {percent}%"
        
        if page_ref.controls_initialized:
            progress_bar.update()
            lbl_status.update()

    def _processing_target_func(page_ref: ft.Page):
        """Целевая функция для потока обработки."""
        if not APP_STATE.input_filepath:
            # Этого не должно произойти, если кнопка заблокирована
            show_snackbar(page_ref, "Ошибка: Файл не выбран для обработки.", ft.colors.RED)
            page_ref.run_thread_safe(lambda: set_ui_processing_state(False, page_ref))
            return

        input_file = APP_STATE.input_filepath
        output_dir = os.path.dirname(input_file)
        base_name, original_ext = os.path.splitext(os.path.basename(input_file))
        
        # Имена файлов
        temp_fixed_filename = f"{base_name}{TEMP_FIXED_VIDEO_SUFFIX}{original_ext}" # Временный файл сохраняем в исходном расширении
        temp_fixed_filepath = os.path.join(output_dir, temp_fixed_filename)
        
        final_output_filename = f"{base_name}{COMPRESSED_VIDEO_SUFFIX}.{APP_STATE.output_extension_key}"
        final_output_filepath = os.path.join(output_dir, final_output_filename)

        current_input_for_compression = input_file
        operation_successful = True
        error_message = ""

        # --- Этап 1: Починка VFR ---
        if APP_STATE.force_vfr_fix or APP_STATE.vfr_fix_recommended:
            page_ref.run_thread_safe(lambda: set_ui_processing_state(True, page_ref, "Починка VFR"))
            
            success, msg = fix_vfr(
                input_file, temp_fixed_filepath, DEFAULT_FPS_FIX,
                DEFAULT_FIX_CRF_H264, DEFAULT_FIX_CRF_VP9, APP_STATE.output_extension_key, # Передаем ключ конечного расширения
                lambda p: page_ref.run_thread_safe(lambda: update_progress_ui(p, page_ref)),
                APP_STATE.video_duration_seconds
            )
            if not success:
                operation_successful = False
                error_message = f"Ошибка починки VFR: {msg}"
            else:
                current_input_for_compression = temp_fixed_filepath
                page_ref.run_thread_safe(lambda: lbl_status.set_value("Починка VFR завершена.")) # Используем set_value для обновления из потока
        else:
             page_ref.run_thread_safe(lambda: lbl_status.set_value("Этап починки VFR пропущен."))


        # --- Этап 2: Основное сжатие ---
        if operation_successful:
            page_ref.run_thread_safe(lambda: set_ui_processing_state(True, page_ref, "Сжатие видео"))
            
            duration_for_compress_step = APP_STATE.video_duration_seconds
            if current_input_for_compression != input_file: # Если был этап починки
                fixed_info, _ = get_video_info(current_input_for_compression)
                if fixed_info:
                    new_duration = get_video_duration_seconds(fixed_info)
                    if new_duration: duration_for_compress_step = new_duration
            
            output_details = OUTPUT_EXTENSIONS[APP_STATE.output_extension_key]
            success, msg = compress_video(
                current_input_for_compression, final_output_filepath,
                output_details, APP_STATE.crf_value,
                lambda p: page_ref.run_thread_safe(lambda: update_progress_ui(p, page_ref)),
                duration_for_compress_step
            )
            if not success:
                operation_successful = False
                error_message = f"Ошибка сжатия: {msg}"
        
        # --- Завершение и обратная связь ---
        if operation_successful:
            page_ref.run_thread_safe(lambda: show_snackbar(page_ref, f"Успешно! Сохранено: {final_output_filepath}", ft.colors.GREEN, 5000))
            page_ref.run_thread_safe(lambda: lbl_status.set_value("Обработка завершена!"))
        else:
            page_ref.run_thread_safe(lambda: show_snackbar(page_ref, error_message, ft.colors.RED, 5000))
            page_ref.run_thread_safe(lambda: lbl_status.set_value("Ошибка во время обработки."))

        # Очистка временного файла
        if current_input_for_compression == temp_fixed_filepath and os.path.exists(temp_fixed_filepath):
            try:
                os.remove(temp_fixed_filepath)
                print(f"Временный файл {temp_fixed_filepath} удален.")
            except OSError as e_remove:
                print(f"Не удалось удалить временный файл: {e_remove}")
        
        page_ref.run_thread_safe(lambda: set_ui_processing_state(False, page_ref))
        page_ref.run_thread_safe(lambda: update_ui_after_file_selection(page_ref, None)) # Сброс файла


    def start_processing_thread(page_ref: ft.Page):
        if APP_STATE.is_processing or not APP_STATE.input_filepath:
            if not APP_STATE.input_filepath:
                 show_snackbar(page_ref, "Сначала выберите видеофайл!", ft.colors.YELLOW_ACCENT_700)
            return
        
        # Запускаем тяжелую операцию в отдельном потоке
        # daemon=True чтобы поток завершился при закрытии основного приложения
        thread = threading.Thread(target=_processing_target_func, args=(page_ref,), daemon=True)
        thread.start()

    # Инициализация состояния слайдера при первом запуске
    slider_crf._initial_update = True 
    update_crf_slider_for_extension_key(APP_STATE.output_extension_key, slider_crf, slider_crf_label, page)
    
    # --- Сборка основного макета страницы ---
    page.add(
        ft.Column(
            [
                ft.Text("Видео Компрессор (Flet + FFmpeg)", size=22, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER),
                section_file_selection,
                section_settings,
                section_vfr_fix,
                section_action_progress,
            ],
            spacing=15, # Пространство между основными секциями
            # scroll=ft.ScrollMode.ADAPTIVE # Если контент не помещается
        )
    )
    page.update() # Первоначальное отображение


# --- Запуск Flet приложения ---
if __name__ == "__main__":
    # Проверяем наличие ffmpeg и ffprobe при старте
    if not os.path.exists(OUTPUT_EXTENSIONS[DEFAULT_OUTPUT_EXTENSION_KEY]["ffmpeg_path"]) or \
       not os.path.exists(OUTPUT_EXTENSIONS[DEFAULT_OUTPUT_EXTENSION_KEY]["ffprobe_path"]):
        print("ОШИБКА: ffmpeg.exe или ffprobe.exe не найдены в корне проекта!")
        print(f"Ожидаемые пути: {OUTPUT_EXTENSIONS[DEFAULT_OUTPUT_EXTENSION_KEY]['ffmpeg_path']}, {OUTPUT_EXTENSIONS[DEFAULT_OUTPUT_EXTENSION_KEY]['ffprobe_path']}")
        # В реальном приложении здесь можно показать диалоговое окно
        # input("Нажмите Enter для выхода...") # Для консоли
        # exit(1) # Выход, если критические зависимости отсутствуют

    ft.app(target=main)
    # Для сборки в десктопное приложение:
    # flet pack main.py --name FletVideoCompressor --icon path/to/icon.png
    # (потребуется установить flet pack и его зависимости, например, PyInstaller)