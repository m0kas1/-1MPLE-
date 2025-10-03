# Create your keyboards here.
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Моя кнопка 1"), KeyboardButton(text="Моя кнопка 2")]
    ],
    resize_keyboard=True
)