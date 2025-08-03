# ui.py
import flet as ft
from config import OUTPUT_EXTENSIONS

class UIControls:
    """Класс для хранения ссылок на все элементы UI, которые нужно обновлять."""
    def __init__(self):
        self.drop_zone = None        # переименовали
        self.txt_selected_file_info = None
        self.dd_output_ext = None
        self.slider_crf_label = None
        self.slider_crf = None
        self.lbl_vfr_status = None
        self.switch_force_vfr_fix = None
        self.progress_bar = None
        self.lbl_status = None
        self.btn_compress = None
        self.btn_browse = None

def build_ui(page: ft.Page, handlers: dict, initial_state: dict):
    """Строит пользовательский интерфейс и возвращает класс со ссылками на элементы."""
    
    controls = UIControls()

    # --- FilePicker ---
    file_picker = ft.FilePicker(on_result=handlers["on_file_picked"])
    page.overlay.append(file_picker)

    # --- «Зона» загрузки, теперь просто кликабельный контейнер ---
    controls.drop_zone = ft.Container(
        content=ft.Row(
            [
                ft.Icon("upload_file", size=40, color="bluegrey300"),
                ft.Text("Нажмите или перетащите видео сюда", color="bluegrey300", size=14)
            ],
            alignment=ft.MainAxisAlignment.CENTER
        ),
        width=float('inf'),
        height=100,
        bgcolor="white12",
        border_radius=8,
        alignment=ft.alignment.center,
        ink=True,  # визуальный эффект нажатия
        on_click=lambda _: file_picker.pick_files(
            dialog_title="Выберите видеофайл",
            allowed_extensions=list(OUTPUT_EXTENSIONS.keys())
        )
    )

    controls.btn_browse = ft.OutlinedButton(
        "Обзор...",
        icon="folder_open",
        on_click=lambda _: file_picker.pick_files(
            dialog_title="Выберите видеофайл",
            allowed_extensions=list(OUTPUT_EXTENSIONS.keys())
        )
    )
    
    controls.txt_selected_file_info = ft.Text("Файл не выбран", italic=True, size=12, color="bluegrey200")
    
    controls.dd_output_ext = ft.Dropdown(
        label="Формат",
        options=[ft.dropdown.Option(key=k, text=f".{k.upper()}") for k in OUTPUT_EXTENSIONS.keys()],
        value=initial_state["output_extension_key"],
        on_change=handlers["on_extension_change"]
    )
    
    controls.slider_crf_label = ft.Text(f"CRF: {initial_state['crf_value']}", weight=ft.FontWeight.BOLD)
    
    crf_details = OUTPUT_EXTENSIONS[initial_state["output_extension_key"]]
    controls.slider_crf = ft.Slider(
        min=crf_details["crf_min"],
        max=crf_details["crf_max"],
        divisions=crf_details["crf_max"] - crf_details["crf_min"],
        value=initial_state["crf_value"],
        label="{value}",
        on_change=handlers["on_crf_change"]
    )
    
    controls.lbl_vfr_status = ft.Text("Починка VFR: Не определено", size=13)
    
    controls.switch_force_vfr_fix = ft.Switch(
        label="Принудительная починка",
        value=initial_state["force_vfr_fix"],
        on_change=handlers["on_force_fix_change"]
    )
    
    controls.progress_bar = ft.ProgressBar(value=0, bar_height=8, color="amber", bgcolor="amber200")
    
    controls.lbl_status = ft.Text("Готов к работе.", size=13, weight=ft.FontWeight.W_500)
    
    controls.btn_compress = ft.FilledButton(
        "Сжать",
        icon="compress",
        on_click=handlers["on_compress_click"],
        height=45,
        disabled=True
    )

    # --- Компоновка ---
    page.add(
        ft.Column([
            ft.Text("1. Выбор видеофайла", weight=ft.FontWeight.BOLD),
            controls.drop_zone,
            ft.Row([ft.Text("или"), controls.btn_browse], alignment=ft.MainAxisAlignment.CENTER),
            controls.txt_selected_file_info, ft.Divider(height=10),

            ft.Text("2. Настройки сжатия", weight=ft.FontWeight.BOLD),
            ft.Row([controls.dd_output_ext, controls.slider_crf_label], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            controls.slider_crf, ft.Divider(height=10),

            ft.Text("3. Обработка VFR", weight=ft.FontWeight.BOLD),
            ft.Row([controls.lbl_vfr_status, controls.switch_force_vfr_fix], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Divider(height=10),

            ft.Text("4. Запуск и Прогресс", weight=ft.FontWeight.BOLD),
            controls.btn_compress,
            controls.progress_bar,
            controls.lbl_status
        ], spacing=10)
    )
    
    return controls