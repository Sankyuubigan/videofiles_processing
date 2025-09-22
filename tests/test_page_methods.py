import flet as ft

def main(page: ft.Page):
    print("Доступные методы page:")
    methods = [method for method in dir(page) if 'thread' in method.lower() or 'update' in method.lower()]
    print(methods)
    
ft.app(target=main)