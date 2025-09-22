import flet as ft

def main(page: ft.Page):
    print("Доступные атрибуты page:")
    attrs = [attr for attr in dir(page) if 'drop' in attr.lower()]
    print(attrs)
    
    # Попробуем установить обработчик on_drop_files
    try:
        page.on_drop_files = lambda e: print(f"Файлы перетащены: {e.files}")
        print("on_drop_files установлен успешно")
    except AttributeError as ex:
        print(f"on_drop_files не поддерживается: {ex}")

ft.app(target=main)