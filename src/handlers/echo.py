# handlers/registration.py
from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
import httpx
import os
from ..states import Form  # оставляем как у тебя, предполагается StatesGroup
from typing import List

router: Router = Router()

# Список продуктов — редактируйте под свои нужды
PRODUCTS: List[str] = [
"Базовый пакет",
"Премиум пакет",
"Тестовый продукт",
]


API_URL = os.getenv("API_URL") # например: https://example.com/api/purchases/
API_TOKEN = os.getenv("API_TOKEN") # опционально: токен для заголовка Authorization
API_BASE = os.getenv("API_BASE")
# Укажи именно тот формат, который ожидает бэкенд: "Token ..." или "Bearer ..."
BOT_TOKEN = os.getenv("BOT_TOKEN")


# # 1) Обычный /start — теперь принимаем CommandStart как второй аргумент
# @router.message(CommandStart())
# async def cmd_start(message: Message, command: CommandStart, state: FSMContext):
#     payload = command.args  # вот тут берем payload корректно (aiogram v3)
#     if payload and payload.startswith("stand_"):
#         stand_id = payload.split("_", 1)[1]
#         await message.answer("Подключаю тебя к очереди... Подожди секунду.")
#         await handle_join_queue(message, stand_id, state)
#         return
#
#     # без payload — обычная регистрация имени
#     await state.update_data(stand_id=None)
#     await state.set_state(RegStatet.waiting_for_name)
#     await message.answer("Привет! Как тебя зовут? Напиши, пожалуйста, своё имя, чтобы мы зарегистрировали тебя.")
#
#
# # 2) Обрабатываем ввод имени и отправляем запрос к Django (регистрация)
# @router.message(RegStatet.waiting_for_name)
# async def receive_name(message: Message, state: FSMContext):
#     name = message.text.strip()
#     tg_id = message.from_user.id
#
#     url = f"{API_BASE}/users/register/"  # ожидаем POST {tg_id, name}
#     headers = {"Authorization": API_TOKEN, "Content-Type": "application/json"}
#     payload = {"tg_id": tg_id, "name": name}
#
#     async with httpx.AsyncClient(timeout=10) as client:
#         try:
#             resp = await client.post(url, json=payload, headers=headers)
#         except Exception:
#             await message.answer("Ошибка связи с сервером — попробуй позже.")
#             await state.clear()
#             return
#
#     # безопасно читаем ответ
#     try:
#         resp_json = resp.json()
#     except Exception:
#         resp_json = {"detail": resp.text}
#
#     if resp.status_code in (200, 201):
#         await message.answer("Готово — зареган.")
#         # если пользователь пришёл с QR (в state сохранили stand_id) — автоматически продолжаем очередь
#         data = await state.get_data()
#         stand_id = data.get("stand_id")
#         if stand_id:
#             await message.answer("Продолжаю — встаю в очередь у стенда " + str(stand_id))
#             await handle_join_queue(message, stand_id, state)
#         else:
#             await message.answer("Теперь подойди к стенду, отсканируй QR и бот автоматически встанет в очередь.")
#     else:
#         await message.answer(f"Не удалось зарегистрироваться: {resp_json}")
#
#     await state.clear()
#
#
# # Вспомогательная функция: попытка встать в очередь (используется при payload из QR)
# async def handle_join_queue(message: Message, stand_id: str, state: FSMContext):
#     tg_id = message.from_user.id
#     url = f"{API_BASE}/tickets/create/"
#     headers = {"Authorization": API_TOKEN, "Content-Type": "application/json"}
#     payload = {"tg_id": tg_id, "stand_id": int(stand_id)}
#
#     async with httpx.AsyncClient(timeout=10) as client:
#         try:
#             resp = await client.post(url, json=payload, headers=headers)
#         except Exception:
#             await message.answer("Ошибка связи с сервером — попробуй позже.")
#             return
#
#     try:
#         data = resp.json()
#     except Exception:
#         data = {"detail": resp.text}
#
#     if resp.status_code in (200, 201):
#         number = data.get("number")
#         eta = data.get("eta_minutes", "?")
#         await message.answer(f"Ты в очереди (стенд {stand_id}). Талон №{number}. ETA ≈ {eta} мин.")
#     else:
#         # если бэкенд отвечает, что пользователя нет в базе — просим имя
#         # допустим, бэкенд возвращает {"detail":"user_not_found"} или 400
#         detail = data.get("detail", "")
#         if resp.status_code in (400, 422) and ("user" in str(detail).lower() or "not" in str(detail).lower()):
#             await state.update_data(stand_id=stand_id)
#             await state.set_state(RegStatet.waiting_for_name)
#             await message.answer("Похоже, тебя ещё нет в системе. Сначала скажи, как тебя зовут:")
#             return
#
#         await message.answer(f"Не удалось встать в очередь: {data}")
#
#
# # Не забудь в основном модуле (main.py) подключить router:
# # dp.include_router(router)

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Привет! Я бот, который запишет твоё имя и выбранный продукт. Как тебя зовут?"
    )
    await state.set_state(Form.name)

@router.message(Form.name)
async def process_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if not name:
        await message.answer("Имя пустое — введи, пожалуйста, настоящее имя.")
        return

    await state.update_data(name=name)

    # Генерируем клавиатуру с продуктами (по одному в ряд)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=prod, callback_data=f"product:{idx}")]
        for idx, prod in enumerate(PRODUCTS)
    ])

    await message.answer("Выбери продукт:", reply_markup=keyboard)
    await state.set_state(Form.product)

@router.callback_query(F.data.startswith("product:"))
async def process_product(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    try:
        idx = int(callback.data.split(":", 1)[1])
    except Exception:
        await callback.message.answer("Неправильный выбор продукта.")
        await state.clear()
        return

    if idx < 0 or idx >= len(PRODUCTS):
        await callback.message.answer("Такого продукта нет.")
        await state.clear()
        return

    product_name = PRODUCTS[idx]
    data = await state.get_data()
    name = data.get("name") or ""

    payload = {"name": name, "product": product_name}

    if not API_URL:
        await callback.message.answer(
            "Ошибка: API_URL не настроен на сервере. Обратитесь к администратору."
        )
        await state.clear()
        return

    headers = {}
    if API_TOKEN:
        # Если у вас сервер ждёт заголовок Authorization, передайте его.
        # Например: API_TOKEN = "Bearer abc..." или "Token abc..."
        headers["Authorization"] = API_TOKEN

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(API_URL, json=payload, headers=headers)
        except httpx.RequestError as exc:
            await callback.message.answer(f"Не удалось связаться с API: {exc}")
            await state.clear()
            return

    if 200 <= resp.status_code < 300:
        # Успех
        await callback.message.answer(
            f"Отлично, {name}! Я отправил твой выбор: {product_name}.\nОтвет сервера: {resp.status_code}"
        )
    else:
        # Ошибка — покажем код и тело (аккуратно, может быть длинное)
        text = resp.text
        if len(text) > 600:
            text = text[:600] + "... (усечено)"
        await callback.message.answer(
            f"Сервер вернул ошибку {resp.status_code}: {text}"
        )

    await state.clear()

@router.message()
async def maybe_cancel(message: Message, state: FSMContext):
    txt = (message.text or "").strip().lower()
    if txt in ("/cancel", "cancel", "отмена"):
        await state.clear()
        await message.answer("Отменил. Если нужно — нажми /start и начнём снова.")
        return
