import os, asyncio, httpx
from aiogram import Bot, Dispatcher, types, Router, F
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, Message, ReplyKeyboardRemove
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from dotenv import load_dotenv
from bot_instance import bot
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from ..keyboards import main_menu
from ..states import Form

router = Router()

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000")
BOT_SECRET = os.getenv("BOT_SECRET")
ADMIN_TG_IDS = set(map(int, os.getenv("ADMIN_TG_IDS","").split(","))) if os.getenv("ADMIN_TG_IDS") else set()

def api_url(path: str) -> str:
    return f"{API_BASE.rstrip('/')}/{path.lstrip('/')}"

async def fetch_user_entries(tg_id: int):
    headers = {}
    if BOT_SECRET:
        headers["X-BOT-SECRET"] = BOT_SECRET
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(api_url(f"api/users/{tg_id}/entries/"), headers=headers)
            resp.raise_for_status()
            try:
                return resp.json()
            except Exception:
                return None
    except Exception:
        return None

async def fetch_position_for_event(event_id: int, tg_id: int):
    headers = {}
    if BOT_SECRET:
        headers["X-BOT-SECRET"] = BOT_SECRET
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(api_url(f"api/events/{event_id}/position/"),
                                    params={"telegram_id": tg_id}, headers=headers)
            status = resp.status_code
            text = resp.text
            try:
                data = resp.json()
            except Exception:
                data = None
            return {"status": status, "raw": text, "data": data}
    except Exception as e:
        return {"status": None, "raw": str(e), "data": None}


def build_entries_text(entries: list, positions: dict) -> str:
    lines = []
    for ent in entries:
        eid = ent.get("id")
        ev = ent.get("event") or {}
        ev_name = ev.get("name", f"event:{ev.get('id')}")
        status = ent.get("status", "unknown")
        pos_info = positions.get(eid, {})
        pos = pos_info.get("position")
        eta = pos_info.get("eta")
        samples = pos_info.get("n_samples", 0)
        if pos is not None:
            eta_str = f"~{eta} мин" if eta is not None else "≈ неизвестно"
            lines.append(f"🆔 {eid} — {ev_name} — позиция {pos} — {eta_str} (n={samples})")
        else:
            lines.append(f"🆔 {eid} — {ev_name} — статус: {status} — ETA: неизвестно")
    header = f"<b>У вас <i>{len(entries)}</i> активных заявок:</b>\n\n"
    return header + "\n".join(lines)


def build_entries_kb(entries: list) -> InlineKeyboardMarkup:
    """
    Для каждой заявки: [❌ Отменить #id]
    Внизу: [❌ Отменить все (N)] и [🔁 Обновить всё]
    """
    rows = []
    for ent in entries:
        eid = ent.get("id")
        rows.append([InlineKeyboardButton(text=f"❌ Отменить #{eid}", callback_data=f"cancel_entry:{eid}")])
    # Добавим строку с "Отменить все" и "Обновить всё"
    rows.append([
        InlineKeyboardButton(text=f"❌ Отменить все ({len(entries)})", callback_data="cancel_all"),
        InlineKeyboardButton(text="🔁 Обновить всё", callback_data="refresh_all")
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ----------------------
# HANDLER: показать мои очереди (нажатие кнопки)
# ----------------------
@router.message(F.text == '📋 Мои очереди')
async def cmd_queue(message: Message):
    tg_id = message.from_user.id

    entries = await fetch_user_entries(tg_id)
    if entries is None:
        await message.answer("Не удалось получить заявки. Попробуйте позже.")
        return

    if not entries:
        await message.answer("У вас нет активных заявок.")
        return

    # Получаем позиции/ETA по событиям (один запрос на каждый event_id)
    positions = {}
    event_ids = {}
    for e in entries:
        ev = e.get("event") or {}
        ev_id = ev.get("id")
        if ev_id is None:
            continue
        event_ids.setdefault(ev_id, []).append(e['id'])

    for ev_id in event_ids.keys():
        resp = await fetch_position_for_event(ev_id, tg_id)
        data = resp.get("data")
        if data and isinstance(data, dict) and data.get("position") is not None:
            try:
                pos_val = int(data.get("position"))
            except Exception:
                pos_val = data.get("position")
            eta = data.get("eta_mean_minutes") or data.get("eta_minutes")
            n_samples = data.get("n_samples", 0)
            for eid in event_ids[ev_id]:
                positions[eid] = {"position": pos_val, "eta": eta, "n_samples": n_samples}
        else:
            for eid in event_ids[ev_id]:
                positions[eid] = {"position": None, "eta": None, "n_samples": 0}

    text = build_entries_text(entries, positions)
    kb = build_entries_kb(entries)

    await message.answer(text, reply_markup=kb)


# ----------------------
# CALLBACK: обновить всё (редактирует сообщение)
# ----------------------
@router.callback_query(lambda c: c.data == "refresh_all")
async def callback_refresh_all(query: CallbackQuery):
    await query.answer()
    try:
        await query.message.delete()
    except Exception:
        pass
    tg_id = query.from_user.id

    entries = await fetch_user_entries(tg_id)
    if entries is None:
        await query.message.answer("Не удалось получить заявки.")
        return

    positions = {}
    event_ids = {}
    for e in entries:
        ev = e.get("event") or {}
        ev_id = ev.get("id")
        if ev_id is None:
            continue
        event_ids.setdefault(ev_id, []).append(e['id'])

    for ev_id in event_ids.keys():
        resp = await fetch_position_for_event(ev_id, tg_id)
        data = resp.get("data")
        if data and isinstance(data, dict) and data.get("position") is not None:
            try:
                pos_val = int(data.get("position"))
            except Exception:
                pos_val = data.get("position")
            eta = data.get("eta_mean_minutes") or data.get("eta_minutes")
            n_samples = data.get("n_samples", 0)
            for eid in event_ids[ev_id]:
                positions[eid] = {"position": pos_val, "eta": eta, "n_samples": n_samples}
        else:
            for eid in event_ids[ev_id]:
                positions[eid] = {"position": None, "eta": None, "n_samples": 0}

    new_text = build_entries_text(entries, positions)
    new_kb = build_entries_kb(entries)
    try:
        await query.message.edit_text(new_text, reply_markup=new_kb)
        await query.answer("Список обновлён.")
    except Exception:
        await query.message.answer(new_text, reply_markup=new_kb)
        await query.answer("Обновлено (новое сообщение).")


# ----------------------
# CALLBACK: отмена конкретной заявки
# ----------------------
@router.callback_query(lambda c: c.data and c.data.startswith("cancel_entry:"))
async def callback_cancel_entry(query: CallbackQuery):
    await query.answer()
    entry_id = int(query.data.split(":", 1)[1])
    headers = {}
    if BOT_SECRET:
        headers["X-BOT-SECRET"] = BOT_SECRET

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(api_url(f"api/entries/{entry_id}/cancel/"), headers=headers)
            try:
                data = resp.json()
            except Exception:
                data = None
    except Exception as e:
        await query.message.answer(f"Ошибка при отмене: {e}")
        return

    removed = None
    if isinstance(data, dict):
        removed = data.get("cancelled") or data.get("removed")

    if removed:
        # уведомим пользователя кратко
        try:
            await query.message.answer(f"Заявка #{entry_id} отменена.")
        except Exception:
            pass
    else:
        # если сервер вернул 200/204 — считаем отменой; иначе покажем код
        if resp.status_code in (200, 204):
            try:
                await query.message.answer(f"Заявка #{entry_id} отмечена как отменённая.")
            except Exception:
                pass
        else:
            await query.message.answer(f"Не удалось отменить заявку (код {resp.status_code}).")

    # После отмены — обновляем список (вызов refresh_all)
    # Попробуем редактировать текущее сообщение (чтобы не плодить)
    try:
        await callback_refresh_all(query)
    except Exception:
        # на всякий случай — вызов напрямую
        await callback_refresh_all(query)


# ----------------------
# CALLBACK: отмена всех заявок
# ----------------------
@router.callback_query(lambda c: c.data == "cancel_all")
async def callback_cancel_all(query: CallbackQuery):
    await query.answer()
    try:
        await query.message.delete()
    except Exception:
        pass
    tg_id = query.from_user.id
    headers = {}
    if BOT_SECRET:
        headers["X-BOT-SECRET"] = BOT_SECRET

    # Получим список заявок пользователя
    entries = await fetch_user_entries(tg_id)
    if not entries:
        await query.message.answer("У вас нет активных заявок.")
        return

    cancelled = []
    errors = []
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            for ent in entries:
                eid = ent.get("id")
                try:
                    r = await client.post(api_url(f"api/entries/{eid}/cancel/"), headers=headers)
                    if r.status_code in (200, 204):
                        cancelled.append(eid)
                    else:
                        errors.append((eid, r.status_code))
                except Exception as e:
                    errors.append((eid, str(e)))
    except Exception as e:
        await query.message.answer(f"Ошибка при массовой отмене: {e}")
        return

    await query.message.answer(f"Отменено заявок: {len(cancelled)}.")
    if errors:
        await query.message.answer(f"Ошибки при отмене: {errors[:5]}")  # короткий отчет

    # Обновляем список
    try:
        await callback_refresh_all(query)
    except Exception:
        await callback_refresh_all(query)

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

@router.message(CommandStart())
async def start(m: types.Message, state: FSMContext):
    await state.clear()
    await m.answer("<b>Привет!</b> Как тебя зовут?")
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
        await message.answer("Не удалось получить список стендов (сервер).", reply_markup=main_menu)
        return

    if not events:
        await message.answer("Сейчас нет доступных стендов.", reply_markup=main_menu)
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=e["name"], callback_data=f"ev:{e['id']}")] for e in events
    ])
    await message.answer("Выберите стенд:", reply_markup=kb)
    await state.set_state(Form.choose_event)

# helper: получить список стендов и отправить inline-клавиатуру
async def send_events_list(chat_id: int, state: FSMContext | None = None) -> bool:
    headers = {}
    if BOT_SECRET:
        headers["X-BOT-SECRET"] = BOT_SECRET

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(api_url("api/events/"), headers=headers, timeout=10.0)
            resp.raise_for_status()
            events = resp.json()
    except Exception:
        await bot.send_message(chat_id, "Не удалось получить список стендов (сервер). Попробуйте позже.")
        return False

    if not events:
        await bot.send_message(chat_id, "Сейчас нет доступных стендов.")
        return False

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=e["name"], callback_data=f"ev:{e['id']}")] for e in events
        ]
    )

    # Отправляем новое сообщение с клавиатурой
    await bot.send_message(chat_id, "Выберите стенд:", reply_markup=kb)

    # Если передали state — ставим ожидаемое состояние
    if state is not None:
        await state.set_state(Form.choose_event)
    return True


# 1) Получаем имя
@router.message()
async def got_name(message: types.Message, state: FSMContext):
    # удаляем сообщение пользователя (если разрешено)
    # try:
    #     await message.delete()
    # except Exception:
    #     pass

    # Если сейчас не состояние ввода имени — игнорируем
    if await state.get_state() != Form.name.state:
        return

    name = (message.text or "").strip()
    if not name:
        await message.answer("Напиши имя, пожалуйста.")
        return

    # Сохраняем данные пользователя
    await state.update_data(name=name, tg_id=message.from_user.id, username=message.from_user.username)

    # Вызов helper'а, который отправит список стендов и поставит состояние choose_event
    ok = await send_events_list(chat_id=message.from_user.id, state=state)
    if not ok:
        # если не удалось получить стенды — очищаем state, чтобы не застрять
        await state.clear()


# 2) Показать инфо и кнопки Подтвердить/Отмена
@router.callback_query(lambda c: c.data and c.data.startswith("ev:"))
async def ev_info(query: CallbackQuery, state: FSMContext):
    await query.answer()
    await query.message.delete()
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
    eta_text = f"<b>Примерное</b> время прохождения на каждого участника: <i>{ev.get('avg_service_minutes', 3)} минут на человека</i>"
    text = f"<b>Стенд: {ev['name']}</b>\n{ev.get('description','')}\n\n{eta_text}\n\nНажмите <b><i>✅ Подтвердить</i></b>, чтобы встать в очередь на данный стенд."
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"confirm:{event_id}"),
         InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_action")]
    ])
    await query.message.answer(text, reply_markup=kb)
    await state.update_data(selected_event=event_id)
    await state.set_state(Form.confirm_event)

@router.callback_query(lambda c: c.data == "cancel_action")
async def cancel_action_cb(query: CallbackQuery, state: FSMContext):
    await query.answer()
    # пытаемся удалить карточку/сообщение с кнопкой
    try:
        await query.message.delete()
    except Exception:
        pass

    # вызываем helper, который отправит список стендов и установит state
    ok = await send_events_list(chat_id=query.from_user.id, state=state)
    if not ok:
        await bot.send_message(query.from_user.id, "Ошибка: не удалось получить стенды. Попробуй позже.")


# 3) Подтверждение — отправляем в API
@router.callback_query(lambda c: c.data and c.data.startswith("confirm:"))
async def confirm_join_cb(query: CallbackQuery, state: FSMContext):
    await query.answer()
    await query.message.delete()
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
            # await query.message.answer(f"Ошибка сервера: {e.response.status_code}", reply_markup=main_menu)
            await query.message.answer(f"Не удалось записаться (", reply_markup=main_menu)
            await state.clear()
            return
        except Exception as e:
            # await query.message.answer(f"Не удалось записаться: {e}", reply_markup=main_menu)
            await query.message.answer(f"Не удалось записаться (", reply_markup=main_menu)
            await state.clear()
            return

    pos = result.get("position")
    eta = result.get("eta_minutes")
    await query.message.answer(f"Ты встал в очередь. Твоя позиция: {pos}. Оценка ожидания: ~{eta} мин.",
                               reply_markup=main_menu)
                               # reply_markup=InlineKeyboardMarkup(
                               #     inline_keyboard=[
                               #         [InlineKeyboardButton(text="Отменить очередь",
                               #                               callback_data=f"leave:{event_id}")]
                               #     ]
                               # ))
    # await query.message.answer('Ты крутой',reply_markup=main_menu)
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
