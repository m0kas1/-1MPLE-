import os, asyncio, httpx
from aiogram import Bot, Dispatcher, types, Router, F
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, Message
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from dotenv import load_dotenv
from bot_instance import bot
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🎡 Стенды"), KeyboardButton(text="📋 Мои очереди")],
        [KeyboardButton(text="📍 Проверить позицию"), KeyboardButton(text="❌ Отменить")],
    ],
    resize_keyboard=True,
    input_field_placeholder="Выберите действие..."
)



router = Router()

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000")
BOT_SECRET = os.getenv("BOT_SECRET")
ADMIN_TG_IDS = set(map(int, os.getenv("ADMIN_TG_IDS","").split(","))) if os.getenv("ADMIN_TG_IDS") else set()

def api_url(path: str) -> str:
    return f"{API_BASE.rstrip('/')}/{path.lstrip('/')}"


class Form(StatesGroup):
    name = State()
    choose_event = State()
    confirm_event = State()
    waiting = State()

# async def set_bot_commands(bot: Bot):
#     commands = [
#         types.BotCommand(command="start", description="Начать — ввести имя и выбрать стенд"),
#         types.BotCommand(command="events", description="Показать доступные стенды"),
#         types.BotCommand(command="queue", description="Показать мои очереди"),
#         types.BotCommand(command="pos", description="Проверить позицию: /pos <event_id>"),
#         types.BotCommand(command="next", description="(Оператор) Вызвать следующего"),
#         types.BotCommand(command="cancel", description="Отменить текущее действие"),
#         types.BotCommand(command="help", description="Помощь"),
#     ]
#     await bot.set_my_commands(commands)

@router.message(Command(commands=["pos"]))
async def cmd_pos(message: Message):
    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer("Использование: /pos <event_id>")
        return
    event_id = parts[1]
    tg_id = message.from_user.id
    headers = {}
    if BOT_SECRET:
        headers["X-BOT-SECRET"] = BOT_SECRET

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(api_url(f"api/events/{event_id}/position/"), params={"telegram_id": tg_id}, headers=headers, timeout=10.0)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        await message.answer(f"Ошибка: {e}")
        return

    pos = data.get("position")
    status = data.get("status")
    eta = data.get("eta_minutes")
    if pos is None:
        await message.answer("Вы не в очереди на этот стенд.")
    else:
        await message.answer(f"Ваша позиция: {pos}. ETA: ~{eta} мин. Статус: {status}")


@router.message(F.text == '📋 Мои очереди')
async def cmd_queue(message: Message):
    tg_id = message.from_user.id
    headers = {}
    if BOT_SECRET:
        headers["X-BOT-SECRET"] = BOT_SECRET
    # Получим список всех стендов
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(api_url("api/events/"), headers=headers, timeout=10.0)
            resp.raise_for_status()
            events = resp.json()
    except Exception:
        await message.answer("Не удалось получить список стендов.")
        return

    results = []
    async with httpx.AsyncClient() as client:
        for e in events:
            try:
                resp = await client.get(api_url(f"api/events/{e['id']}/position/"), params={"telegram_id": tg_id}, headers=headers, timeout=5.0)
                resp.raise_for_status()
                data = resp.json()
                if data.get("position"):
                    results.append(f"{e['name']}: позиция {data['position']}, ETA ~{data.get('eta_minutes')}")
            except Exception:
                continue

    if not results:
        await message.answer("Вы не стоите ни в одной очереди.")
    else:
        await message.answer("Твои очереди:\n" + "\n".join(results))

@router.message(F.text == '❌ Отменить')
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Действие отменено.")

@router.message(Command(commands=["help"]))
async def cmd_help(message: Message):
    await message.answer(
        "/start — начать\n"
        "/events — список стендов\n"
        "/queue — мои очереди\n"
        "/pos <event_id> — проверить позицию\n"
        "/cancel — отменить текущее действие\n"
        "/next <event_id> — (оператор) вызвать следующего"
    )

# @router.message(F.text == "🎡 Стенды")
# async def cmd_events(message: Message):
#     headers = {}
#     if BOT_SECRET:
#         headers["X-BOT-SECRET"] = BOT_SECRET
#     try:
#         async with httpx.AsyncClient() as client:
#             resp = await client.get(api_url("api/events/"), headers=headers, timeout=10.0)
#             resp.raise_for_status()
#             events = resp.json()
#     except Exception:
#         await message.answer("Не удалось получить список стендов.")
#         return
#
#     if not events:
#         await message.answer("Сейчас нет доступных стендов.")
#         return
#
#     text = "Доступные стенды:\n" + "\n".join([f"{e['id']}. {e['name']}" for e in events])
#     await message.answer(text)

@router.message(F.text == '')
async def cmd_next(message: types.Message):
    if message.from_user.id not in ADMIN_TG_IDS:
        await message.answer("Нет доступа")
        return
    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer("Использование: /next <event_id>")
        return
    event_id = parts[1]
    headers = {}
    if BOT_SECRET:
        headers["X-BOT-SECRET"] = BOT_SECRET

    async with httpx.AsyncClient() as client:
        resp = await client.post(api_url(f"api/events/{event_id}/next/"), headers=headers, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()

    if data.get("detail") == "queue_empty":
        await message.answer("Очередь пуста.")
        return

    called = data.get("called_user")
    tg = called.get("telegram_id")
    username = called.get("username")
    # уведомляем оператора
    await message.answer(f"Вызван пользователь: {username} ({tg})")
    # уведомление игрока
    await bot.send_message(chat_id=tg, text=f"Твоя очередь на стенд {event_id}! Подойди, пожалуйста.")


@router.message(CommandStart())
async def start(m: types.Message, state: FSMContext):
    await state.clear()
    await m.answer("Привет! Как тебя зовут?", reply_markup=main_menu)
    await state.set_state(Form.name)

@router.message(F.text == "🎡 Стенды")
async def btn_show_events(message: types.Message, state: FSMContext):
    # не просим имя — но на всякий случай ставим в state что-то под именем
    # чтобы дальше при подтверждении можно было передать full_name, username
    # берем полное имя из telegram, если есть — иначе username, иначе пусто
    full_name = message.from_user.full_name or message.from_user.username or ""
    await state.update_data(name=full_name, tg_id=message.from_user.id, username=message.from_user.username)

    headers = {}
    if BOT_SECRET:
        headers["X-BOT-SECRET"] = BOT_SECRET

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(api_url("api/events/"), headers=headers, timeout=10.0)
            resp.raise_for_status()
            events = resp.json()
    except Exception as e:
        await message.answer("Не удалось получить список стендов (сервер).")
        return

    if not events:
        await message.answer("Сейчас нет доступных стендов.")
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=e["name"], callback_data=f"ev:{e['id']}")] for e in events
    ])
    await message.answer("Выберите стенд:", reply_markup=kb)
    await state.set_state(Form.choose_event)

# 1) Получаем имя
@router.message()
async def got_name(message: types.Message, state: FSMContext):
    # пока не в состоянии ввода имени — игнорируем (чтобы кнопки/прочие тексты не ломали)
    if await state.get_state() != Form.name.state:
        return
    name = (message.text or "").strip()
    if not name:
        await message.answer("Напиши имя, пожалуйста.")
        return
    # сохраняем имя и далее — показываем стенды (ту же логику, что и для кнопки)
    await state.update_data(name=name, tg_id=message.from_user.id, username=message.from_user.username)

    headers = {}
    if BOT_SECRET:
        headers["X-BOT-SECRET"] = BOT_SECRET
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(api_url("api/events/"), headers=headers, timeout=10.0)
            resp.raise_for_status()
            events = resp.json()
    except Exception:
        await message.answer("Не удалось получить список стендов (сервер).")
        await state.clear()
        return

    if not events:
        await message.answer("Сейчас нет доступных стендов.")
        await state.clear()
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=e["name"], callback_data=f"ev:{e['id']}")] for e in events
    ])
    await message.answer("Выберите стенд:", reply_markup=kb)
    await state.set_state(Form.choose_event)

# 2) Показать инфо и кнопки Подтвердить/Отмена
@router.callback_query(lambda c: c.data and c.data.startswith("ev:"))
async def ev_info(query: CallbackQuery, state: FSMContext):
    await query.answer()
    event_id = int(query.data.split(":",1)[1])
    headers = {}
    if BOT_SECRET:
        headers["X-BOT-SECRET"] = BOT_SECRET
    # Запросить детали события или использовать уже полученные данные
    async with httpx.AsyncClient() as client:
        resp = await client.get(api_url(f"api/events/"), headers=headers)
        resp.raise_for_status()
        events = resp.json()
    ev = next((e for e in events if e["id"]==event_id), None)
    if not ev:
        await query.message.answer("Ошибка: стенд не найден.")
        await state.clear()
        return

    # текст карточки
    eta_text = f"Оценка времени ожидания: {ev.get('avg_service_minutes', 3)} минут на человека"
    text = f"Стенд: {ev['name']}\n{ev.get('description','')}\n\n{eta_text}\n\nНажми Подтвердить, чтобы встать в очередь."
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Подтвердить", callback_data=f"confirm:{event_id}"),
         InlineKeyboardButton(text="Отмена", callback_data="cancel_action")]
    ])
    await query.message.answer(text, reply_markup=kb)
    await state.update_data(selected_event=event_id)
    await state.set_state(Form.confirm_event)

@router.callback_query(lambda c: c.data == "cancel_action")
async def cancel_action_cb(query: CallbackQuery, state: FSMContext):
    await query.answer("Отменено")
    await state.clear()

# 3) Подтверждение — отправляем в API
@router.callback_query(lambda c: c.data and c.data.startswith("confirm:"))
async def confirm_join_cb(query: CallbackQuery, state: FSMContext):
    await query.answer()
    data = await state.get_data()
    name = data.get("name")
    tg_id = data.get("tg_id")
    username = data.get("username")
    event_id = int(query.data.split(":",1)[1])

    payload = {"telegram_id": tg_id, "username": username, "full_name": name}
    headers = {"Content-Type":"application/json"}
    if BOT_SECRET:
        headers["X-BOT-SECRET"] = BOT_SECRET

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(api_url(f"api/events/{event_id}/join/"), json=payload, headers=headers, timeout=10.0)
            resp.raise_for_status()
            result = resp.json()
        except httpx.HTTPStatusError as e:
            await query.message.answer(f"Ошибка сервера: {e.response.status_code}")
            await state.clear()
            return
        except Exception as e:
            await query.message.answer(f"Не удалось записаться: {e}")
            await state.clear()
            return

    pos = result.get("position")
    eta = result.get("eta_minutes")
    await query.message.answer(f"Ты встал в очередь. Твоя позиция: {pos}. Оценка ожидания: ~{eta} мин.",
                               reply_markup=InlineKeyboardMarkup(
                                   inline_keyboard=[
                                       [InlineKeyboardButton(text="Отменить очередь",
                                                             callback_data=f"leave:{event_id}")]
                                   ]
                               ))
    await state.clear()

# 4) Отмена через кнопку
@router.callback_query(lambda c: c.data and c.data.startswith("leave:"))
async def leave_cb(query: CallbackQuery, state: FSMContext):
    await query.answer()
    event_id = int(query.data.split(":",1)[1])
    tg_id = query.from_user.id
    headers = {}
    if BOT_SECRET:
        headers["X-BOT-SECRET"] = BOT_SECRET
    async with httpx.AsyncClient() as client:
        resp = await client.post(api_url(f"api/events/{event_id}/leave/"), json={"telegram_id": tg_id}, headers=headers, timeout=10.0)
    await query.message.answer("Ты вышел из очереди." if resp.json().get("removed") else "Ты не был в очереди.")
