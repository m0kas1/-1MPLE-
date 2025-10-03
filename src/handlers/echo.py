# handlers/registration.py
from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
import httpx
import os
from ..states import RegStatet  # оставляем как у тебя, предполагается StatesGroup

router: Router = Router()

API_BASE = "https://your-api.example.com/api"
# Укажи именно тот формат, который ожидает бэкенд: "Token ..." или "Bearer ..."
API_TOKEN = "Token your_api_token_here"
BOT_TOKEN = os.getenv("BOT_TOKEN")


# 1) Обычный /start — теперь принимаем CommandStart как второй аргумент
@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandStart, state: FSMContext):
    payload = command.args  # вот тут берем payload корректно (aiogram v3)
    if payload and payload.startswith("stand_"):
        stand_id = payload.split("_", 1)[1]
        await message.answer("Подключаю тебя к очереди... Подожди секунду.")
        await handle_join_queue(message, stand_id, state)
        return

    # без payload — обычная регистрация имени
    await state.update_data(stand_id=None)
    await state.set_state(RegStatet.waiting_for_name)
    await message.answer("Привет! Как тебя зовут? Напиши, пожалуйста, своё имя, чтобы мы зарегистрировали тебя.")


# 2) Обрабатываем ввод имени и отправляем запрос к Django (регистрация)
@router.message(RegStatet.waiting_for_name)
async def receive_name(message: Message, state: FSMContext):
    name = message.text.strip()
    tg_id = message.from_user.id

    url = f"{API_BASE}/users/register/"  # ожидаем POST {tg_id, name}
    headers = {"Authorization": API_TOKEN, "Content-Type": "application/json"}
    payload = {"tg_id": tg_id, "name": name}

    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.post(url, json=payload, headers=headers)
        except Exception:
            await message.answer("Ошибка связи с сервером — попробуй позже.")
            await state.clear()
            return

    # безопасно читаем ответ
    try:
        resp_json = resp.json()
    except Exception:
        resp_json = {"detail": resp.text}

    if resp.status_code in (200, 201):
        await message.answer("Готово — зареган.")
        # если пользователь пришёл с QR (в state сохранили stand_id) — автоматически продолжаем очередь
        data = await state.get_data()
        stand_id = data.get("stand_id")
        if stand_id:
            await message.answer("Продолжаю — встаю в очередь у стенда " + str(stand_id))
            await handle_join_queue(message, stand_id, state)
        else:
            await message.answer("Теперь подойди к стенду, отсканируй QR и бот автоматически встанет в очередь.")
    else:
        await message.answer(f"Не удалось зарегистрироваться: {resp_json}")

    await state.clear()


# Вспомогательная функция: попытка встать в очередь (используется при payload из QR)
async def handle_join_queue(message: Message, stand_id: str, state: FSMContext):
    tg_id = message.from_user.id
    url = f"{API_BASE}/tickets/create/"
    headers = {"Authorization": API_TOKEN, "Content-Type": "application/json"}
    payload = {"tg_id": tg_id, "stand_id": int(stand_id)}

    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.post(url, json=payload, headers=headers)
        except Exception:
            await message.answer("Ошибка связи с сервером — попробуй позже.")
            return

    try:
        data = resp.json()
    except Exception:
        data = {"detail": resp.text}

    if resp.status_code in (200, 201):
        number = data.get("number")
        eta = data.get("eta_minutes", "?")
        await message.answer(f"Ты в очереди (стенд {stand_id}). Талон №{number}. ETA ≈ {eta} мин.")
    else:
        # если бэкенд отвечает, что пользователя нет в базе — просим имя
        # допустим, бэкенд возвращает {"detail":"user_not_found"} или 400
        detail = data.get("detail", "")
        if resp.status_code in (400, 422) and ("user" in str(detail).lower() or "not" in str(detail).lower()):
            await state.update_data(stand_id=stand_id)
            await state.set_state(RegStatet.waiting_for_name)
            await message.answer("Похоже, тебя ещё нет в системе. Сначала скажи, как тебя зовут:")
            return

        await message.answer(f"Не удалось встать в очередь: {data}")


# Не забудь в основном модуле (main.py) подключить router:
# dp.include_router(router)
