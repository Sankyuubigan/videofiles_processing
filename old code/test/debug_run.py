import traceback
import sys

try:
    import main
    # Если main.py не имеет условия if __name__ == "__main__", 
    # то нужно импортировать модуль, а не запускать как скрипт
except Exception as e:
    print("Произошла ошибка:")
    print(f"Тип ошибки: {type(e).__name__}")
    print(f"Сообщение об ошибке: {str(e)}")
    print("\nТрассировка стека:")
    traceback.print_exc()
    sys.exit(1)