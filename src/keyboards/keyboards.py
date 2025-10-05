# Create your keyboards here.
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Моя кнопка 1"), KeyboardButton(text="Моя кнопка 2")]
    ],
    resize_keyboard=True
)

main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🎡 Стенды"), KeyboardButton(text="📋 Мои очереди")],
    ],
    resize_keyboard=True,
    input_field_placeholder="Выберите действие..."
)