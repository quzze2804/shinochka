from aiogram import Router, F
from aiogram.filters import Command, Text
from aiogram.types import Message
from keyboards import main_menu_keyboard
from datetime import datetime, time, timedelta
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

router = Router()

# Память для записей: {user_id: [datetime, ...]}
user_appointments = {}

# Занятые слоты: {datetime: user_id}
booked_slots = {}

def generate_slots(date):
    slots = []
    start = datetime.combine(date, time(8, 0))
    end = datetime.combine(date, time(17, 0))
    current = start
    while current <= end:
        slots.append(current)
        current += timedelta(minutes=30)
    return slots

def format_slot(dt):
    return dt.strftime("%Y-%m-%d %H:%M")

@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "👋 Вітаємо у шиномонтажі!\nОберіть дію нижче 👇",
        reply_markup=main_menu_keyboard()
    )

@router.message(Text("🛠 Записатися"))
async def cmd_book(message: Message):
    today = datetime.now().date()
    dates = [today, today + timedelta(days=1), today + timedelta(days=2)]
    buttons = [f"{d.strftime('%Y-%m-%d')}" for d in dates]

    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    for b in buttons:
        keyboard.add(b)

    await message.answer("Оберіть дату для запису:", reply_markup=keyboard)
    await BookStates.waiting_for_date.set()

class BookStates(StatesGroup):
    waiting_for_date = State()
    waiting_for_slot = State()
    waiting_for_confirmation = State()

@router.message(BookStates.waiting_for_date)
async def process_date(message: Message, state: FSMContext):
    try:
        selected_date = datetime.strptime(message.text, "%Y-%m-%d").date()
    except:
        await message.answer("Некоректна дата, спробуйте ще раз у форматі РРРР-ММ-ДД")
        return

    slots = generate_slots(selected_date)
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    for slot in slots:
        if slot in booked_slots:
            keyboard.add(KeyboardButton(text=f"❌ {slot.strftime('%H:%M')}"))
        else:
            keyboard.add(KeyboardButton(text=slot.strftime('%H:%M')))

    await message.answer(f"Оберіть час для {selected_date}:", reply_markup=keyboard)
    await state.update_data(selected_date=selected_date)
    await BookStates.waiting_for_slot.set()

@router.message(BookStates.waiting_for_slot)
async def process_slot(message: Message, state: FSMContext):
    data = await state.get_data()
    selected_date = data.get("selected_date")
    time_text = message.text.replace("❌ ", "")

    try:
        selected_time = datetime.strptime(time_text, "%H:%M").time()
    except:
        await message.answer("Некоректний час, спробуйте ще раз.")
        return

    selected_datetime = datetime.combine(selected_date, selected_time)

    if selected_datetime in booked_slots:
        await message.answer("Цей час уже зайнятий, оберіть інший.")
        return

    await state.update_data(selected_datetime=selected_datetime)
    await message.answer(f"Ви обрали {format_slot(selected_datetime)}. Підтвердьте запис (так/ні)")
    await BookStates.waiting_for_confirmation.set()

@router.message(BookStates.waiting_for_confirmation)
async def process_confirmation(message: Message, state: FSMContext):
    text = message.text.lower()
    data = await state.get_data()
    dt = data.get("selected_datetime")

    if text not in ("так", "ні"):
        await message.answer("Будь ласка, відповідайте 'так' або 'ні'.")
        return

    if text == "ні":
        await message.answer("Запис скасовано. Можна почати заново через меню.")
        await state.clear()
        return

    user_id = message.from_user.id
    user_appointments.setdefault(user_id, [])
    user_appointments[user_id].append(dt)
    booked_slots[dt] = user_id

    from main import bot
    admin_id = int((await bot.get("ADMIN_CHAT_ID")) or 7285220061)
    await bot.send_message(admin_id, f"Нова бронь: {message.from_user.full_name} на {format_slot(dt)}")

    await message.answer(f"✅ Запис підтверджено на {format_slot(dt)}!")
    await state.clear()

@router.message(Text("📅 Мої записи"))
async def show_my_appointments(message: Message):
    user_id = message.from_user.id
    appts = user_appointments.get(user_id, [])
    if not appts:
        await message.answer("У вас немає записів.")
        return

    text = "Ваші записи:\n" + "\n".join(f"- {format_slot(dt)}" for dt in appts)
    await message.answer(text)

@router.message(Text("❌ Скасувати запис"))
async def cancel_appointment_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    appts = user_appointments.get(user_id, [])
    if not appts:
        await message.answer("У вас немає записів для скасування.")
        return

    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    for dt in appts:
        keyboard.add(KeyboardButton(format_slot(dt)))

    await message.answer("Оберіть запис для скасування:", reply_markup=keyboard)
    await state.set_state("cancelling")

@router.message()
async def handle_cancel_confirm(message: Message, state: FSMContext):
    if await state.get_state() != "cancelling":
        return

    user_id = message.from_user.id
    appts = user_appointments.get(user_id, [])
    text = message.text

    for dt in appts:
        if format_slot(dt) == text:
            appts.remove(dt)
            booked_slots.pop(dt, None)
            await message.answer(f"✅ Запис на {text} скасовано.")
            await state.clear()
            return

    await message.answer("Запис не знайдено, спробуйте ще раз.")

@router.message(Text("🔄 Перенести запис"))
async def start_reschedule(message: Message, state: FSMContext):
    user_id = message.from_user.id
    appts = user_appointments.get(user_id, [])
    if not appts:
        await message.answer("У вас немає записів для перенесення.")
        return

    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    for dt in appts:
        keyboard.add(KeyboardButton(format_slot(dt)))

    await message.answer("Оберіть запис для перенесення:", reply_markup=keyboard)
    await state.set_state("rescheduling_select")

@router.message()
async def handle_reschedule_select(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state != "rescheduling_select":
        return

    user_id = message.from_user.id
    appts = user_appointments.get(user_id, [])
    text = message.text

    for dt in appts:
        if format_slot(dt) == text:
            await state.update_data(reschedule_dt=dt)
            await message.answer("Оберіть нову дату для перенесення (РРРР-ММ-ДД):")
            await BookStates.waiting_for_date.set()
            await state.set_state("rescheduling_date")
            return

    await message.answer("Запис не знайдено, спробуйте ще раз.")

@router.message()
async def handle_reschedule_date(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state != "rescheduling_date":
        return

    try:
        selected_date = datetime.strptime(message.text, "%Y-%m-%d").date()
    except:
        await message.answer("Некоректна дата, спробуйте ще раз у форматі РРРР-ММ-ДД")
        return

    slots = generate_slots(selected_date)
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    for slot in slots:
        if slot in booked_slots:
            keyboard.add(KeyboardButton(text=f"❌ {slot.strftime('%H:%M')}"))
        else:
            keyboard.add(KeyboardButton(text=slot.strftime('%H:%M')))

    await message.answer(f"Оберіть новий час для {selected_date}:", reply_markup=keyboard)
    await state.update_data(selected_date=selected_date)
    await state.set_state("rescheduling_slot")

@router.message()
async def handle_reschedule_slot(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state != "rescheduling_slot":
        return

    data = await state.get_data()
    selected_date = data.get("selected_date")
    time_text = message.text.replace("❌ ", "")

    try:
        selected_time = datetime.strptime(time_text, "%H:%M").time()
    except:
        await message.answer("Некоректний час, спробуйте ще раз.")
        return

    selected_datetime = datetime.combine(selected_date, selected_time)

    if selected_datetime in booked_slots:
        await message.answer("Цей час вже зайнятий, оберіть інший.")
        return

    data = await state.get_data()
    old_dt = data.get("reschedule_dt")
    user_id = message.from_user.id

    user_appointments[user_id].remove(old_dt)
    booked_slots.pop(old_dt, None)

    user_appointments.setdefault(user_id, []).append(selected_datetime)
    booked_slots[selected_datetime] = user_id

    from main import bot
    admin_id = int((await bot.get("ADMIN_CHAT_ID")) or 7285220061)
    await bot.send_message(admin_id, f"Перенос броні: {message.from_user.full_name} з {format_slot(old_dt)} на {format_slot(selected_datetime)}")

    await message.answer(f"✅ Запис перенесено на {format_slot(selected_datetime)}!")
    await state.clear()
