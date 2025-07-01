from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def main_menu_keyboard():
    kb = [
        [KeyboardButton(text="🛠 Записатися")],
        [KeyboardButton(text="📅 Мої записи"), KeyboardButton(text="❌ Скасувати запис")],
        [KeyboardButton(text="🔄 Перенести запис")],
        [KeyboardButton(text="ℹ️ Зв’язатися з нами")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)
