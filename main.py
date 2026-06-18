# ============================================================================
# ИМПОРТ БИБЛИОТЕК
# ============================================================================
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton, 
    MenuButtonCommands,
    KeyboardButton, ReplyKeyboardMarkup,
    ReplyKeyboardRemove
)
from aiogram.exceptions import TelegramBadRequest
from aiohttp import web
import json
import os
from datetime import datetime, timedelta
import asyncio
import re
import logging

# ============================================================================
# НАСТРОЙКИ ЛОГИРОВАНИЯ
# ============================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='bot.log',
    filemode='a'
)
console = logging.StreamHandler()
console.setLevel(logging.INFO)
logging.getLogger('').addHandler(console)
logger = logging.getLogger(__name__)

# ============================================================================
# НАСТРОЙКИ
# ============================================================================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_ID = 1439539656

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
booking_lock = asyncio.Lock()

# ============================================================================
# ССЫЛКИ
# ============================================================================
YANDEX_MAPS_URL = "https://yandex.by/maps/?text=Жлобин, ул. Матросова, 39"
INSTAGRAM_URL = "https://instagram.com/_novakeratin"

# ============================================================================
# УМНОЕ УПРАВЛЕНИЕ СООБЩЕНИЯМИ
# ============================================================================
last_bot_messages = {}

async def send_bot_message(user_id, chat_id, text, reply_markup=None, parse_mode=None):
    try:
        msg = await bot.send_message(
            chat_id, 
            text, 
            reply_markup=reply_markup, 
            parse_mode=parse_mode
        )
        last_bot_messages[user_id] = msg.message_id
        return msg
    except Exception as e:
        logger.error(f"Ошибка отправки сообщения: {e}")
        return None

# ============================================================================
# БЕЗОПАСНЫЕ ОБЁРТКИ
# ============================================================================
async def safe_answer(callback_query, text=None, show_alert=False):
    try:
        if text:
            await callback_query.answer(text, show_alert=show_alert)
        else:
            await callback_query.answer()
    except Exception as e:
        logger.warning(f"Не удалось ответить на callback_query: {e}")

async def safe_delete(message):
    try:
        await message.delete()
    except Exception as e:
        logger.warning(f"Не удалось удалить сообщение: {e}")

async def safe_send_message(chat_id, text, parse_mode=None, reply_markup=None):
    try:
        return await bot.send_message(
            chat_id, 
            text, 
            parse_mode=parse_mode, 
            reply_markup=reply_markup
        )
    except Exception as e:
        logger.error(f"Не удалось отправить сообщение в {chat_id}: {e}")
        return None

# ============================================================================
# ВИЗУАЛЬНЫЕ ЭЛЕМЕНТЫ
# ============================================================================
DIVIDER = "━━━━━━━━━━━━━━━━━━━━"
THIN_DIVIDER = "────────────────────"

# ============================================================================
# РУССКИЕ НАЗВАНИЯ ДНЕЙ НЕДЕЛИ И МЕСЯЦЕВ
# ============================================================================
WEEKDAYS_RU = {
    0: "Пн", 1: "Вт", 2: "Ср", 3: "Чт", 4: "Пт", 5: "Сб", 6: "Вс"
}

MONTHS_RU = {
    1: "января", 2: "февраля", 3: "марта", 4: "апреля",
    5: "мая", 6: "июня", 7: "июля", 8: "августа",
    9: "сентября", 10: "октября", 11: "ноября", 12: "декабря"
}

def format_date_ru(date_str):
    try:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        day = date_obj.strftime("%d.%m")
        weekday = WEEKDAYS_RU[date_obj.weekday()]
        return f"{day} ({weekday})"
    except:
        return date_str

def format_date_full_ru(date_str):
    try:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        day = date_obj.day
        month = MONTHS_RU[date_obj.month]
        year = date_obj.year
        weekday_full = {
            0: "понедельник", 1: "вторник", 2: "среда", 3: "четверг",
            4: "пятница", 5: "суббота", 6: "воскресенье"
        }[date_obj.weekday()]
        return f"{day} {month} {year}, {weekday_full}"
    except:
        return date_str

# ============================================================================
# ДЛИТЕЛЬНОСТЬ И ЦЕНЫ ПРОЦЕДУР
# ============================================================================
def get_service_duration(service):
    durations = {
        "cold_restoration": 2.5,
        "keratin_botox": 4,
        "total_reconstruction": 5
    }
    return durations.get(service, 2.5)

def get_service_name(service):
    names = {
        "cold_restoration": "❄️ Холодное восстановление",
        "keratin_botox": "✨ Кератин / Ботокс",
        "total_reconstruction": "💎 Тотальная реконструкция"
    }
    return names.get(service, "Неизвестная услуга")

def get_service_price(service):
    prices = {
        "cold_restoration": 80,
        "keratin_botox": 150,
        "total_reconstruction": 200
    }
    return prices.get(service, 0)

# ============================================================================
# УПРАВЛЕНИЕ РАСПИСАНИЕМ
# ============================================================================
def generate_weekend_schedule():
    try:
        schedule = {}
        today = datetime.now().date()
        days_added = 0
        current_date = today + timedelta(days=1)
        
        while days_added < 8:
            if current_date.weekday() == 5 or current_date.weekday() == 6:
                date_str = current_date.strftime("%Y-%m-%d")
                schedule[date_str] = {}
                for hour in range(9, 18):
                    time_str = f"{hour:02d}:00"
                    schedule[date_str][time_str] = "free"
                days_added += 1
            current_date += timedelta(days=1)
        return schedule
    except Exception as e:
        logger.error(f"Ошибка генерации расписания: {e}")
        return {}

def update_schedule(data):
    try:
        today = datetime.now().date()
        dates_to_remove = []
        for d in data["schedule"]:
            try:
                if datetime.strptime(d, "%Y-%m-%d").date() < today:
                    dates_to_remove.append(d)
            except:
                dates_to_remove.append(d)
        
        for d in dates_to_remove:
            del data["schedule"][d]
        
        existing_dates = set(data["schedule"].keys())
        new_schedule = generate_weekend_schedule()
        for date_str, times in new_schedule.items():
            if date_str not in existing_dates:
                data["schedule"][date_str] = times
        
        for date_str in list(data["schedule"].keys()):
            try:
                date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
                if date_obj >= today:
                    bookings_on_date = [b for b in data["bookings"] if b.get("date") == date_str]
                    if not bookings_on_date:
                        for t in data["schedule"][date_str]:
                            data["schedule"][date_str][t] = "free"
                    else:
                        booked_times = {b.get("time") for b in bookings_on_date if b.get("time")}
                        for t in data["schedule"][date_str]:
                            if t not in booked_times:
                                data["schedule"][date_str][t] = "free"
            except Exception as e:
                logger.error(f"Ошибка обработки даты {date_str}: {e}")
                continue
        
        return data
    except Exception as e:
        logger.error(f"Ошибка обновления расписания: {e}")
        return data

def clean_old_bookings(data):
    try:
        now = datetime.now()
        cleaned = []
        for b in data.get("bookings", []):
            try:
                dt = datetime.strptime(f"{b.get('date', '')} {b.get('time', '')}", "%Y-%m-%d %H:%M")
                if dt >= now:
                    cleaned.append(b)
            except:
                continue
        data["bookings"] = cleaned
        return data
    except Exception as e:
        logger.error(f"Ошибка очистки старых записей: {e}")
        return data

def check_time_overlap(start_time, duration, existing_bookings, date_str):
    try:
        sh, sm = map(int, start_time.split(':'))
        start_min = sh * 60 + sm
        end_min = start_min + int(duration * 60)
        
        for b in existing_bookings:
            if b.get("date") != date_str:
                continue
            try:
                eh, em = map(int, b.get("time", "00:00").split(':'))
                ex_start = eh * 60 + em
                ex_end = ex_start + int(get_service_duration(b.get("service", "")) * 60)
                if not (end_min <= ex_start or start_min >= ex_end):
                    return True
            except:
                continue
        return False
    except:
        return False

def check_long_procedure_booked(existing_bookings, date_str):
    try:
        for b in existing_bookings:
            if b.get("date") == date_str and b.get("service") in ["keratin_botox", "total_reconstruction"]:
                return True
        return False
    except:
        return False

def get_available_times_for_service(date_str, schedule, existing_bookings, service):
    try:
        if date_str not in schedule:
            return []
        
        duration = get_service_duration(service)
        available = []
        
        for t in sorted(schedule[date_str].keys()):
            try:
                h, m = map(int, t.split(':'))
                end_hour = h + int(duration)
                end_min = m + int((duration % 1) * 60)
                if end_min >= 60:
                    end_hour += 1
                    end_min -= 60
                
                if end_hour > 17 or (end_hour == 17 and end_min > 0):
                    continue
                
                if service in ["keratin_botox", "total_reconstruction"]:
                    if check_long_procedure_booked(existing_bookings, date_str):
                        continue
                
                if schedule[date_str][t] != "free":
                    continue
                
                if check_time_overlap(t, duration, existing_bookings, date_str):
                    continue
                
                available.append(t)
            except:
                continue
        
        return available
    except Exception as e:
        logger.error(f"Ошибка получения доступных времен: {e}")
        return []

# ============================================================================
# РАБОТА С ВЕРИФИЦИРОВАННЫМИ ПОЛЬЗОВАТЕЛЯМИ
# ============================================================================
def load_verified_users():
    try:
        filename = "verified_users.json"
        if os.path.exists(filename):
            with open(filename, "r", encoding="utf-8") as file:
                return json.load(file)
        else:
            return {}
    except Exception as e:
        logger.error(f"Ошибка загрузки verified_users: {e}")
        return {}

def save_verified_user(user_id, name, phone):
    try:
        filename = "verified_users.json"
        verified_users = load_verified_users()
        verified_users[str(user_id)] = {
            "name": name,
            "phone": phone,
            "verified_at": datetime.now().isoformat()
        }
        with open(filename, "w", encoding="utf-8") as file:
            json.dump(verified_users, file, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"Ошибка сохранения верифицированного пользователя: {e}")
        return False

def get_verified_user(user_id):
    verified_users = load_verified_users()
    return verified_users.get(str(user_id))

# ============================================================================
# УВЕДОМЛЕНИЯ МАСТЕРУ
# ============================================================================
async def send_admin_notification(text):
    try:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 Открыть меню", callback_data="back_to_menu")]
        ])
        await safe_send_message(ADMIN_ID, text, parse_mode="HTML", reply_markup=keyboard)
        logger.info("Уведомление отправлено мастеру")
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления мастеру: {e}")

async def send_admin_alert(text):
    try:
        await safe_send_message(ADMIN_ID, text, parse_mode="HTML")
        logger.info("Важное уведомление отправлено мастеру")
    except Exception as e:
        logger.error(f"Ошибка отправки важного уведомления: {e}")

# ============================================================================
# СОСТОЯНИЯ
# ============================================================================
class BookingState(StatesGroup):
    waiting_for_contact = State()
    waiting_for_service = State()
    waiting_for_date = State()
    waiting_for_time = State()

# ============================================================================
# ГЛАВНОЕ МЕНЮ
# ============================================================================
async def show_main_menu(message_or_callback):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Записаться", callback_data="start_booking")],
        [InlineKeyboardButton(text="📋 Мои записи", callback_data="my_bookings")],
        [InlineKeyboardButton(text="👩‍🎨 О мастере", callback_data="about_master")],
        [InlineKeyboardButton(text="⭐ Отзывы", callback_data="reviews")],
        [InlineKeyboardButton(text="❗ Противопоказания", callback_data="contraindications_info")],
        [InlineKeyboardButton(text="📍 Как добраться", callback_data="how_to_get")]
    ])
    
    # Для мастера добавляем кнопку панели
    if isinstance(message_or_callback, types.CallbackQuery):
        if message_or_callback.from_user.id == ADMIN_ID:
            keyboard.inline_keyboard.append([
                InlineKeyboardButton(text="👨‍💼 Панель мастера", callback_data="admin_panel")
            ])
    elif isinstance(message_or_callback, types.Message):
        if message_or_callback.from_user.id == ADMIN_ID:
            keyboard.inline_keyboard.append([
                InlineKeyboardButton(text="👨‍💼 Панель мастера", callback_data="admin_panel")
            ])
    
    text = (
        f"✨ <b>Добро пожаловать в Nova Keratin!</b>\n\n"
        f"👩‍🎨 <b>Мастер Мария</b>\n"
        f"📍 Жлобин, ул. Матросова, 39\n"
        f"⏰ Работаю Сб-Вс, 9:00-17:00\n\n"
        f"Выберите действие:"
    )
    
    if isinstance(message_or_callback, types.Message):
        user_id = message_or_callback.from_user.id
        chat_id = message_or_callback.chat.id
        
        if user_id in last_bot_messages:
            try:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=last_bot_messages[user_id],
                    text=text,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
                return
            except Exception as e:
                logger.warning(f"Не удалось отредактировать сообщение: {e}")
        
        msg = await bot.send_message(chat_id, text, reply_markup=keyboard, parse_mode="HTML")
        last_bot_messages[user_id] = msg.message_id
    else:
        try:
            await message_or_callback.message.edit_text(
                text=text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            last_bot_messages[message_or_callback.from_user.id] = message_or_callback.message.message_id
        except Exception as e:
            msg = await message_or_callback.message.answer(text, reply_markup=keyboard, parse_mode="HTML")
            last_bot_messages[message_or_callback.from_user.id] = msg.message_id

# ============================================================================
# РАБОТА С ДАННЫМИ
# ============================================================================
def load_data():
    try:
        filename = "bookings.json"
        if os.path.exists(filename):
            try:
                with open(filename, "r", encoding="utf-8") as file:
                    data = json.load(file)
                
                if "bookings" not in data:
                    data["bookings"] = []
                if "schedule" not in data:
                    data["schedule"] = generate_weekend_schedule()
                
                data = clean_old_bookings(data)
                data = update_schedule(data)
                save_data(data)
                return data
            except json.JSONDecodeError as e:
                data = {"bookings": [], "schedule": generate_weekend_schedule()}
                save_data(data)
                return data
            except Exception as e:
                data = {"bookings": [], "schedule": generate_weekend_schedule()}
                save_data(data)
                return data
        else:
            data = {"bookings": [], "schedule": generate_weekend_schedule()}
            save_data(data)
            return data
    except Exception as e:
        return {"bookings": [], "schedule": {}}

def save_data(data):
    try:
        filename = "bookings.json"
        temp_filename = filename + ".tmp"
        with open(temp_filename, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
        os.replace(temp_filename, filename)
    except Exception as e:
        logger.error(f"Ошибка сохранения данных: {e}")

# ============================================================================
# НАПОМИНАНИЯ
# ============================================================================
async def reminder_task():
    logger.info("🔔 Задача напоминаний запущена!")
    while True:
        try:
            await check_and_send_reminders()
        except Exception as e:
            logger.error(f"❌ Ошибка в задаче напоминаний: {e}")
        await asyncio.sleep(60)

async def check_and_send_reminders():
    try:
        data = load_data()
        now = datetime.now()
        reminders_sent = False
        
        for b in data.get("bookings", []):
            if "user_id" not in b:
                continue
            try:
                dt = datetime.strptime(f"{b.get('date', '')} {b.get('time', '')}", "%Y-%m-%d %H:%M")
            except:
                continue
            
            minutes_until = (dt - now).total_seconds() / 60
            
            if 23*60+55 <= minutes_until <= 24*60+5 and not b.get("reminded_24h"):
                await send_client_reminder(b)
                b["reminded_24h"] = True
                reminders_sent = True
            
            if 1*60+55 <= minutes_until <= 2*60+5 and not b.get("admin_reminded_2h"):
                await send_admin_reminder(b)
                b["admin_reminded_2h"] = True
                reminders_sent = True
        
        if reminders_sent:
            save_data(data)
    except Exception as e:
        logger.error(f"Ошибка проверки напоминаний: {e}")

async def send_client_reminder(booking):
    try:
        date_display = format_date_full_ru(booking.get("date", ""))
        service_name = booking.get("service_name", get_service_name(booking.get("service", "")))
        
        text = (
            f"🔔 <b>Напоминание</b>\n\n"
            f"Здравствуйте, <b>{booking.get('name', 'Клиент')}</b>! ✨\n\n"
            f"Завтра мы ждём вас:\n\n"
            f"📅 {date_display}\n"
            f"⏰ {booking.get('time', '')}\n"
            f"💆‍♀️ {service_name}\n\n"
            f"📍 <b>Адрес:</b>\nул. Матросова, 39, 1 этаж\n\n"
            f"<i>Если планы изменились — отмените запись в боте</i>"
        )
        
        await safe_send_message(booking["user_id"], text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"❌ Ошибка напоминания: {e}")

async def send_admin_reminder(booking):
    try:
        date_display = format_date_full_ru(booking.get("date", ""))
        service_name = booking.get("service_name", get_service_name(booking.get("service", "")))
        
        start_hour, start_min = map(int, booking.get("time", "00:00").split(':'))
        duration = get_service_duration(booking.get("service", ""))
        end_hour = start_hour + int(duration)
        end_min = start_min + int((duration % 1) * 60)
        if end_min >= 60:
            end_hour += 1
            end_min -= 60
        end_time = f"{end_hour:02d}:{end_min:02d}"
        
        text = (
            f"⏰ <b>Скоро запись</b>\n\n"
            f"Через 2 часа:\n\n"
            f"👤 <b>{booking.get('name', 'Неизвестно')}</b>\n"
            f"📞 {booking.get('phone', '')}\n"
            f"📅 {date_display}\n"
            f"⏰ {booking.get('time', '')} — {end_time}\n"
            f"💆‍♀️ {service_name}\n\n"
            f"📍 ул. Матросова, 39, 1 этаж"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 Открыть меню", callback_data="back_to_menu")]
        ])
        
        await safe_send_message(ADMIN_ID, text, parse_mode="HTML", reply_markup=keyboard)
    except Exception as e:
        logger.error(f"❌ Ошибка напоминания мастеру: {e}")

# ============================================================================
# ИНФОРМАЦИОННЫЕ КНОПКИ
# ============================================================================
@dp.callback_query(lambda c: c.data == 'about_master')
async def about_master(callback_query: types.CallbackQuery, state: FSMContext):
    try:
        text = (
            f"👩‍🎨 <b>О мастере</b>\n\n"
            f"<b>Мария</b> — сертифицированный мастер реконструкции волос\n\n"
            f"✨ <b>Опыт работы:</b> более 3 лет\n"
            f"🎓 <b>Образование:</b> профессиональные курсы по кератиновому выпрямлению и восстановлению волос\n"
            f"💎 <b>Специализация:</b> все виды реконструкции волос\n\n"
            f"📸 <b>Портфолио работ:</b>\n@_novakeratin\n\n"
            f"📍 <b>Адрес:</b> ул. Матросова, 39, 1 этаж (Жлобин)\n"
            f"⏰ <b>Время работы:</b> Суббота и Воскресенье, 9:00-17:00"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◂ Назад", callback_data="back_to_menu")]
        ])
        
        await send_bot_message(
            callback_query.from_user.id,
            callback_query.message.chat.id,
            text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        await safe_answer(callback_query)
    except Exception as e:
        logger.error(f"Ошибка 'О мастере': {e}")

@dp.callback_query(lambda c: c.data == 'reviews')
async def reviews(callback_query: types.CallbackQuery, state: FSMContext):
    try:
        text = (
            f"⭐ <b>Отзывы клиентов</b>\n\n"
            f"Более 200 довольных клиентов! 💕\n\n"
            f"📸 <b>Смотрите фото работ и отзывы в Instagram:</b>\n"
            f"@_novakeratin\n\n"
            f"💬 <b>Или напишите мастеру напрямую:</b>\n"
            f"@_novakeratin"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📸 Открыть Instagram", url=INSTAGRAM_URL)],
            [InlineKeyboardButton(text="◂ Назад", callback_data="back_to_menu")]
        ])
        
        await send_bot_message(
            callback_query.from_user.id,
            callback_query.message.chat.id,
            text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        await safe_answer(callback_query)
    except Exception as e:
        logger.error(f"Ошибка 'Отзывы': {e}")

@dp.callback_query(lambda c: c.data == 'contraindications_info')
async def contraindications_info(callback_query: types.CallbackQuery, state: FSMContext):
    try:
        text = (
            f"⚠️ <b>Противопоказания к процедурам</b>\n\n"
            f"<b>Абсолютные противопоказания:</b>\n"
            f"1. Беременность\n"
            f"2. Грудное вскармливание\n"
            f"3. Аллергические реакции на формальдегид\n"
            f"4. Приём сильных медикаментов\n"
            f"5. Заболевания кожи головы\n"
            f"6. Бронхиальная и аллергическая астма\n"
            f"7. Онкология и предраковые состояния\n"
            f"8. Высокая чувствительность кожи\n\n"
            f"<b>С осторожностью (посоветуйтесь с врачом):</b>\n"
            f"1. Заболевания, воспаления слизистых\n"
            f"2. Повышенная раздражаемость слизистых\n"
            f"3. Проблемы со зрением и ЦНС\n"
            f"4. Повышенная слезоточивость\n"
            f"5. Дети до 18 лет\n\n"
            f"❗ Если у вас есть что-то из перечисленного, проконсультируйтесь с мастером перед записью!\n\n"
            f"📞 <b>Консультация:</b> @_novakeratin"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📅 Записаться", callback_data="start_booking")],
            [InlineKeyboardButton(text="◂ Назад", callback_data="back_to_menu")]
        ])
        
        await send_bot_message(
            callback_query.from_user.id,
            callback_query.message.chat.id,
            text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        await safe_answer(callback_query)
    except Exception as e:
        logger.error(f"Ошибка 'Противопоказания': {e}")

@dp.callback_query(lambda c: c.data == 'how_to_get')
async def how_to_get(callback_query: types.CallbackQuery, state: FSMContext):
    try:
        text = (
            f"📍 <b>Как добраться</b>\n\n"
            f"<b>Адрес:</b>\n"
            f"ул. Матросова, 39, 1 этаж\n"
            f"г. Жлобин\n\n"
            f"🏢 <b>Ориентиры:</b>\n"
            f"Напротив магазинов «Светофор» и «Мастак»\n\n"
            f"🕐 <b>Время работы:</b>\n"
            f"Суббота и Воскресенье\n"
            f"9:00 — 17:00\n\n"
            f"📸 <b>Instagram:</b>\n"
            f"@_novakeratin"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🗺️ Открыть в Яндекс.Картах", url=YANDEX_MAPS_URL)],
            [InlineKeyboardButton(text="◂ Назад", callback_data="back_to_menu")]
        ])
        
        await send_bot_message(
            callback_query.from_user.id,
            callback_query.message.chat.id,
            text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        await safe_answer(callback_query)
    except Exception as e:
        logger.error(f"Ошибка 'Как добраться': {e}")

# ============================================================================
# АДМИН-ПАНЕЛЬ
# ============================================================================
@dp.callback_query(lambda c: c.data == 'admin_panel')
async def admin_panel(callback_query: types.CallbackQuery, state: FSMContext):
    try:
        if callback_query.from_user.id != ADMIN_ID:
            await safe_answer(callback_query, "⛔ Только для мастера", show_alert=True)
            return
        
        await state.clear()
        data = load_data()
        
        if not data.get("bookings"):
            text = (
                f"📋 <b>Панель мастера</b>\n\n"
                f"<i>Записей пока нет</i>\n\n"
                f"Как только появится первая запись — она отобразится здесь."
            )
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 В главное меню", callback_data="back_to_menu")]
            ])
            
            await send_bot_message(
                callback_query.from_user.id,
                callback_query.message.chat.id,
                text,
                parse_mode="HTML",
                reply_markup=keyboard
            )
        else:
            sorted_bookings = sorted(data["bookings"], key=lambda x: (x.get("date", ""), x.get("time", "")))
            
            text = (
                f"📋 <b>Панель мастера</b>\n\n"
                f"<i>Ближайшие записи:</i>\n\n"
            )
            
            keyboard_buttons = []
            current_date = None
            
            for b in sorted_bookings:
                if b.get("date") != current_date:
                    current_date = b.get("date")
                    text += f"<b>▸ {format_date_full_ru(current_date)}</b>\n{THIN_DIVIDER}\n"
                
                service_name = b.get("service_name", get_service_name(b.get("service", "")))
                duration = get_service_duration(b.get("service", ""))
                
                try:
                    sh, sm = map(int, b.get("time", "00:00").split(':'))
                    eh = sh + int(duration)
                    em = sm + int((duration % 1) * 60)
                    if em >= 60:
                        eh += 1
                        em -= 60
                    end_time = f"{eh:02d}:{em:02d}"
                except:
                    end_time = "??:??"
                
                text += (
                    f"  ⏰ {b.get('time', '')} — {end_time}\n"
                    f"  👤 {b.get('name', 'Неизвестно')}\n"
                    f"  📞 {b.get('phone', '')}\n"
                    f"  💆‍♀️ {service_name}\n\n"
                )
                
                callback_data = f"admin_cancel_{b.get('date', '')}_{b.get('time', '')}"
                keyboard_buttons.append([
                    InlineKeyboardButton(
                        text=f"❌ Отменить {b.get('date', '')} {b.get('time', '')} - {b.get('name', '')}",
                        callback_data=callback_data
                    )
                ])
            
            keyboard_buttons.append([InlineKeyboardButton(text="🔙 В главное меню", callback_data="back_to_menu")])
            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
            
            await send_bot_message(
                callback_query.from_user.id,
                callback_query.message.chat.id,
                text,
                parse_mode="HTML",
                reply_markup=keyboard
            )
        
        await safe_answer(callback_query)
    except Exception as e:
        logger.error(f"Ошибка админ-панели: {e}")

@dp.callback_query(lambda c: c.data.startswith('admin_cancel_'))
async def admin_cancel_booking(callback_query: types.CallbackQuery, state: FSMContext):
    try:
        if callback_query.from_user.id != ADMIN_ID:
            await safe_answer(callback_query, "⛔ Только для мастера", show_alert=True)
            return
        
        parts = callback_query.data.split('_')
        date_str = parts[2]
        time_str = parts[3]
        
        data = load_data()
        booking_to_cancel = None
        
        for b in data.get("bookings", []):
            if b.get("date") == date_str and b.get("time") == time_str:
                booking_to_cancel = b
                break
        
        if not booking_to_cancel:
            await send_bot_message(
                callback_query.from_user.id,
                callback_query.message.chat.id,
                "❌ Запись не найдена."
            )
            await safe_answer(callback_query)
            return
        
        data["bookings"].remove(booking_to_cancel)
        if date_str in data["schedule"]:
            data["schedule"][date_str][time_str] = "free"
        save_data(data)
        
        date_display = format_date_full_ru(date_str)
        try:
            await safe_send_message(
                booking_to_cancel["user_id"],
                f"⚠️ Ваша запись на {date_display} в {time_str} была отменена мастером.\n\nПриносим извинения за неудобства. Пожалуйста, свяжитесь с мастером для уточнения деталей: @_novakeratin"
            )
        except Exception as e:
            logger.error(f"Не удалось уведомить клиента об отмене: {e}")
        
        await send_bot_message(
            callback_query.from_user.id,
            callback_query.message.chat.id,
            f"✅ Запись отменена:\n{booking_to_cancel.get('name', '')} - {date_display} {time_str}"
        )
        
        # Перезагружаем админ-панель
        await callback_query.message.delete()
        await admin_panel(callback_query, state)
        
        await safe_answer(callback_query, "Запись отменена")
    except Exception as e:
        logger.error(f"Ошибка отмены записи мастером: {e}")

@dp.callback_query(lambda c: c.data == 'back_to_menu')
async def back_to_menu(callback_query: types.CallbackQuery, state: FSMContext):
    try:
        await state.clear()
        await show_main_menu(callback_query)
    except Exception as e:
        logger.error(f"Ошибка возврата в меню: {e}")

# ============================================================================
# НАЧАЛО ЗАПИСИ С ПРОВЕРКОЙ ВЕРИФИКАЦИИ
# ============================================================================
@dp.callback_query(lambda c: c.data == 'start_booking')
async def process_start_booking(callback_query: types.CallbackQuery, state: FSMContext):
    try:
        user_id = callback_query.from_user.id
        verified_user = get_verified_user(user_id)
        
        if verified_user:
            # Пользователь уже верифицирован
            await state.update_data(
                name=verified_user["name"],
                phone=verified_user["phone"]
            )
            await state.set_state(BookingState.waiting_for_service)
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❄️ Холодное восстановление — 80 BYN (2.5 ч)", callback_data="service_cold_restoration")],
                [InlineKeyboardButton(text="✨ Кератин / Ботокс — 150 BYN (4 ч)", callback_data="service_keratin_botox")],
                [InlineKeyboardButton(text="💎 Тотальная реконструкция — 200 BYN (5 ч)", callback_data="service_total_reconstruction")],
                [InlineKeyboardButton(text="◂ Назад", callback_data="back_to_menu")]
            ])
            
            await send_bot_message(
                callback_query.from_user.id,
                callback_query.message.chat.id,
                f"✅ С возвращением, <b>{verified_user['name']}</b>!\n\nВыберите услугу:",
                reply_markup=keyboard,
                parse_mode="HTML"
            )
        else:
            # Пользователь не верифицирован - запрашиваем контакт через ОБЫЧНУЮ клавиатуру
            await state.set_state(BookingState.waiting_for_contact)
            
            # ⚠️ ВАЖНО: Используем ReplyKeyboardMarkup + KeyboardButton, а не InlineKeyboardButton!
            contact_keyboard = ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="📱 Поделиться контактом", request_contact=True)],
                    [KeyboardButton(text="❌ Отмена")]
                ],
                resize_keyboard=True,
                one_time_keyboard=True
            )
            
            await send_bot_message(
                callback_query.from_user.id,
                callback_query.message.chat.id,
                f"📅 <b>Запись на процедуру</b>\n\n"
                f"Для записи необходимо подтвердить номер телефона.\n\n"
                f"Нажмите кнопку <b>«📱 Поделиться контактом»</b> ниже.\n\n"
                f"<i>Это нужно один раз. В будущем подтверждать не потребуется.</i>",
                reply_markup=contact_keyboard,
                parse_mode="HTML"
            )
        
        await safe_answer(callback_query)
    except Exception as e:
        logger.error(f"Ошибка начала записи: {e}")

@dp.message(BookingState.waiting_for_contact)
async def process_contact(message: types.Message, state: FSMContext):
    """Обработка полученного контакта"""
    try:
        # Убираем обычную клавиатуру
        await message.answer("...", reply_markup=ReplyKeyboardRemove())
        
        # Проверяем, не нажал ли пользователь "Отмена"
        if message.text and "Отмена" in message.text:
            await state.clear()
            await show_main_menu(message)
            return
        
        if not message.contact:
            await send_bot_message(
                message.from_user.id,
                message.chat.id,
                "❌ Пожалуйста, нажмите кнопку «📱 Поделиться контактом» для подтверждения номера телефона."
            )
            return
        
        contact = message.contact
        phone = contact.phone_number
        name = contact.first_name or "Клиент"
        
        if contact.last_name:
            name = f"{contact.first_name} {contact.last_name}"
        
        # Сохраняем верифицированного пользователя
        save_verified_user(message.from_user.id, name, phone)
        
        await state.update_data(name=name, phone=phone)
        await state.set_state(BookingState.waiting_for_service)
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❄️ Холодное восстановление — 80 BYN (2.5 ч)", callback_data="service_cold_restoration")],
            [InlineKeyboardButton(text="✨ Кератин / Ботокс — 150 BYN (4 ч)", callback_data="service_keratin_botox")],
            [InlineKeyboardButton(text="💎 Тотальная реконструкция — 200 BYN (5 ч)", callback_data="service_total_reconstruction")],
            [InlineKeyboardButton(text="◂ Назад", callback_data="back_to_menu")]
        ])
        
        await send_bot_message(
            message.from_user.id,
            message.chat.id,
            f"✅ Спасибо, <b>{name}</b>!\nНомер {phone} подтверждён.\n\nВыберите услугу:",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Ошибка обработки контакта: {e}")

# ============================================================================
# ВЫБОР УСЛУГИ
# ============================================================================
@dp.callback_query(lambda c: c.data.startswith('service_'))
async def process_service(callback_query: types.CallbackQuery, state: FSMContext):
    try:
        service_code = callback_query.data.replace("service_", "")
        await state.update_data(service=service_code)
        await state.set_state(BookingState.waiting_for_date)
        
        user_id = callback_query.from_user.id
        data = load_data()
        user_bookings = [b for b in data.get("bookings", []) if b.get("user_id") == user_id]
        
        # Если у пользователя уже есть 2+ записи - предупреждаем мастера
        if len(user_bookings) >= 2:
            user_data = await state.get_data()
            alert_text = (
                f"⚠️ <b>ВНИМАНИЕ: Множественные записи!</b>\n\n"
                f"Пользователь <b>{user_data.get('name', '')}</b> ({user_data.get('phone', '')})\n"
                f"пытается сделать уже {len(user_bookings) + 1}-ю запись!\n\n"
                f"<b>Текущие записи:</b>\n"
            )
            
            for b in user_bookings:
                alert_text += f"• {format_date_ru(b['date'])} {b['time']} - {get_service_name(b['service'])}\n"
            
            await send_admin_alert(alert_text)
        
        schedule = data.get("schedule", {})
        existing_bookings = data.get("bookings", [])
        
        available_dates = []
        for date_str in sorted(schedule.keys()):
            try:
                date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                if date_obj.weekday() not in [5, 6]:
                    continue
                available_times = get_available_times_for_service(date_str, schedule, existing_bookings, service_code)
                if available_times:
                    available_dates.append(date_str)
            except:
                continue
        
        if not available_dates:
            service_name = get_service_name(service_code)
            await send_bot_message(
                callback_query.from_user.id,
                callback_query.message.chat.id,
                f"К сожалению, для услуги <b>{service_name}</b> все слоты заняты.",
                parse_mode="HTML"
            )
            await state.clear()
            await show_main_menu(callback_query)
            await safe_answer(callback_query)
            return
        
        keyboard_buttons = []
        for date_str in available_dates[:6]:
            try:
                date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                day_name = "Суббота" if date_obj.weekday() == 5 else "Воскресенье"
                date_display = date_obj.strftime("%d.%m")
                keyboard_buttons.append([InlineKeyboardButton(text=f"{date_display} ({day_name})", callback_data=f"date_{date_str}")])
            except:
                continue
        
        keyboard_buttons.append([InlineKeyboardButton(text="◂ Назад", callback_data="back_to_menu")])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        service_name = get_service_name(service_code)
        
        await send_bot_message(
            callback_query.from_user.id,
            callback_query.message.chat.id,
            f"📅 <b>{service_name}</b>\n\n💡 Мастер работает только по выходным!\n\nВыберите дату:",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        await safe_answer(callback_query)
    except Exception as e:
        logger.error(f"Ошибка выбора услуги: {e}")

# ============================================================================
# ВЫБОР ДАТЫ
# ============================================================================
@dp.callback_query(lambda c: c.data.startswith('date_'))
async def process_date(callback_query: types.CallbackQuery, state: FSMContext):
    try:
        date_str = callback_query.data.replace("date_", "")
        await state.update_data(date=date_str)
        await state.set_state(BookingState.waiting_for_time)
        
        data = load_data()
        schedule = data.get("schedule", {})
        existing_bookings = data.get("bookings", [])
        
        user_data = await state.get_data()
        service_code = user_data.get("service", "cold_restoration")
        
        free_times = get_available_times_for_service(date_str, schedule, existing_bookings, service_code)
        
        if not free_times:
            service_name = get_service_name(service_code)
            await send_bot_message(
                callback_query.from_user.id,
                callback_query.message.chat.id,
                f"На эту дату все слоты для <b>{service_name}</b> заняты.",
                parse_mode="HTML"
            )
            await state.set_state(BookingState.waiting_for_date)
            await safe_answer(callback_query)
            return
        
        keyboard_buttons = []
        for time_str in sorted(free_times):
            keyboard_buttons.append([InlineKeyboardButton(text=time_str, callback_data=f"time_{time_str}")])
        
        keyboard_buttons.append([InlineKeyboardButton(text="◂ Назад", callback_data="back_to_menu")])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        
        await send_bot_message(
            callback_query.from_user.id,
            callback_query.message.chat.id,
            f"✅ Выберите свободное время:",
            reply_markup=keyboard
        )
        await safe_answer(callback_query)
    except Exception as e:
        logger.error(f"Ошибка выбора даты: {e}")

# ============================================================================
# ВЫБОР ВРЕМЕНИ
# ============================================================================
@dp.callback_query(lambda c: c.data.startswith('time_'))
async def process_time(callback_query: types.CallbackQuery, state: FSMContext):
    try:
        current_state = await state.get_state()
        if current_state != BookingState.waiting_for_time.state:
            await safe_answer(callback_query)
            return
        
        time_str = callback_query.data.replace("time_", "")
        user_data = await state.get_data()
        date_str = user_data.get('date')
        service_code = user_data.get('service')
        
        duration = get_service_duration(service_code)
        service_name = get_service_name(service_code)
        price = get_service_price(service_code)
        
        async with booking_lock:
            data = load_data()
            
            if data["schedule"].get(date_str, {}).get(time_str) != "free":
                await send_bot_message(
                    callback_query.from_user.id,
                    callback_query.message.chat.id,
                    "⏰ К сожалению, этот слот только что заняли. Пожалуйста, выберите другое время."
                )
                await safe_answer(callback_query)
                return
            
            if service_code in ["keratin_botox", "total_reconstruction"]:
                for time_slot in data["schedule"][date_str].keys():
                    data["schedule"][date_str][time_slot] = "booked"
            else:
                data["schedule"][date_str][time_str] = "booked"
            
            new_booking = {
                "user_id": callback_query.from_user.id,
                "name": user_data.get('name', ''),
                "phone": user_data.get('phone', ''),
                "service": service_code,
                "service_name": service_name,
                "date": date_str,
                "time": time_str,
                "duration": duration,
                "notified_about_earlier_slot": False,
                "reminded_24h": False,
                "reminded_2h": False,
                "admin_reminded_2h": False
            }
            data["bookings"].append(new_booking)
            save_data(data)
        
        admin_text = (
            f"🔔 <b>Новая запись</b>\n\n"
            f"👤 <b>{user_data.get('name', '')}</b>\n"
            f"📞 {user_data.get('phone', '')}\n"
            f"📅 {format_date_full_ru(date_str)}\n"
            f"⏰ {time_str}\n"
            f"💆‍♀️ {service_name}\n"
            f"💰 {price} BYN"
        )
        await send_admin_notification(admin_text)
        
        date_display = format_date_full_ru(date_str)
        start_hour, start_min = map(int, time_str.split(':'))
        end_hour = start_hour + int(duration)
        end_min = start_min + int((duration % 1) * 60)
        if end_min >= 60:
            end_hour += 1
            end_min -= 60
        end_time = f"{end_hour:02d}:{end_min:02d}"
        
        final_message = (
            f"✅ <b>Запись подтверждена!</b>\n\n"
            f"Отлично, <b>{user_data.get('name', '')}</b>! ✨\n\n"
            f"Вы записаны на:\n"
            f"💆‍♀️ {service_name}\n\n"
            f"📅 {date_display}\n"
            f"⏰ {time_str} — {end_time}\n"
            f"💰 {price} BYN\n\n"
            f"📍 <b>Адрес:</b>\nул. Матросова, 39, 1 этаж\n(напротив Светофор, Мастак)\n\n"
            f"📞 <b>Контакты:</b>\nInstagram: @_novakeratin\n\n"
            f"🔔 Мы напомним вам о записи за 24 часа до визита.\n\n"
            f"<i>Ждём вас! ✨</i>"
        )
        
        await state.clear()
        await send_bot_message(
            callback_query.from_user.id,
            callback_query.message.chat.id,
            final_message,
            parse_mode="HTML"
        )
        await show_main_menu(callback_query)
        await safe_answer(callback_query)
    except Exception as e:
        logger.error(f"Ошибка выбора времени: {e}")

# ============================================================================
# МОИ ЗАПИСИ
# ============================================================================
@dp.callback_query(lambda c: c.data == 'my_bookings')
async def show_my_bookings(callback_query: types.CallbackQuery, state: FSMContext):
    try:
        await state.clear()
        user_id = callback_query.from_user.id
        data = load_data()
        user_bookings = [b for b in data.get("bookings", []) if b.get("user_id") == user_id]
        
        if not user_bookings:
            await send_bot_message(user_id, callback_query.message.chat.id, "У вас нет активных записей.")
            await show_main_menu(callback_query)
            await safe_answer(callback_query)
            return
        
        bookings_text = (
            f"📋 <b>Ваши записи</b>\n\n"
        )
        
        for b in user_bookings:
            date_display = format_date_full_ru(b.get("date", ""))
            service_name = b.get("service_name", get_service_name(b.get("service", "")))
            duration = get_service_duration(b.get("service", ""))
            price = get_service_price(b.get("service", ""))
            
            try:
                sh, sm = map(int, b.get("time", "00:00").split(':'))
                eh = sh + int(duration)
                em = sm + int((duration % 1) * 60)
                if em >= 60:
                    eh += 1
                    em -= 60
                end_time = f"{eh:02d}:{em:02d}"
            except:
                end_time = "??:??"
            
            bookings_text += (
                f"<b>▸ {date_display}</b>\n"
                f"  ⏰ {b.get('time', '')} — {end_time}\n"
                f"  💆‍♀️ {service_name}\n"
                f"  💰 {price} BYN\n\n"
            )
        
        bookings_text += f"<i>Управление записями доступно в главном меню</i>"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отменить запись", callback_data="cancel_booking")],
            [InlineKeyboardButton(text="◂ Назад", callback_data="back_to_menu")]
        ])
        
        await send_bot_message(user_id, callback_query.message.chat.id, bookings_text, parse_mode="HTML", reply_markup=keyboard)
        await safe_answer(callback_query)
    except Exception as e:
        logger.error(f"Ошибка показа записей: {e}")

# ============================================================================
# ОТМЕНА ЗАПИСИ КЛИЕНТОМ
# ============================================================================
@dp.callback_query(lambda c: c.data == 'cancel_booking')
async def start_cancellation(callback_query: types.CallbackQuery, state: FSMContext):
    try:
        await state.clear()
        user_id = callback_query.from_user.id
        data = load_data()
        user_bookings = [b for b in data.get("bookings", []) if b.get("user_id") == user_id]
        
        if not user_bookings:
            await send_bot_message(user_id, callback_query.message.chat.id, "У вас нет активных записей.")
            await show_main_menu(callback_query)
            await safe_answer(callback_query)
            return
        
        keyboard_buttons = []
        for b in user_bookings:
            date_display = format_date_ru(b.get("date", ""))
            service_name = b.get("service_name", get_service_name(b.get("service", "")))
            button_text = f"{date_display} {b.get('time', '')} — {service_name}"
            callback_data = f"cancel_{b.get('date', '')}_{b.get('time', '')}"
            keyboard_buttons.append([InlineKeyboardButton(text=button_text, callback_data=callback_data)])
        
        keyboard_buttons.append([InlineKeyboardButton(text="◂ Назад", callback_data="back_to_menu")])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        await send_bot_message(user_id, callback_query.message.chat.id, "Какую запись вы хотите отменить?", reply_markup=keyboard)
        await safe_answer(callback_query)
    except Exception as e:
        logger.error(f"Ошибка начала отмены: {e}")

@dp.callback_query(lambda c: c.data.startswith('cancel_'))
async def confirm_cancellation(callback_query: types.CallbackQuery, state: FSMContext):
    try:
        parts = callback_query.data.split('_')
        date_str = parts[1]
        time_str = parts[2]
        user_id = callback_query.from_user.id
        
        data = load_data()
        booking_to_cancel = None
        for b in data.get("bookings", []):
            if (b.get("user_id") == user_id and b.get("date") == date_str and b.get("time") == time_str):
                booking_to_cancel = b
                break
        
        if not booking_to_cancel:
            await send_bot_message(user_id, callback_query.message.chat.id, "Запись не найдена.")
            await show_main_menu(callback_query)
            await safe_answer(callback_query)
            return
        
        data["bookings"].remove(booking_to_cancel)
        if date_str in data["schedule"]:
            data["schedule"][date_str][time_str] = "free"
        save_data(data)
        
        admin_cancel_text = (
            f"⚠️ <b>Отмена записи</b>\n\n"
            f"👤 <b>{booking_to_cancel.get('name', '')}</b>\n"
            f"📅 {format_date_full_ru(date_str)}\n"
            f"⏰ {time_str}\n"
            f"💆‍♀️ {booking_to_cancel.get('service_name', get_service_name(booking_to_cancel.get('service', '')))}"
        )
        await send_admin_notification(admin_cancel_text)
        
        date_display = format_date_full_ru(date_str)
        await send_bot_message(
            user_id,
            callback_query.message.chat.id,
            f"❌ Ваша запись на {date_display} в {time_str} отменена.\nБудем ждать вас в другой раз!"
        )
        
        asyncio.create_task(notify_clients_about_earlier_slot(date_str, time_str))
        await show_main_menu(callback_query)
        await safe_answer(callback_query)
    except Exception as e:
        logger.error(f"Ошибка подтверждения отмены: {e}")

async def notify_clients_about_earlier_slot(date_str, time_str):
    try:
        data = load_data()
        later_bookings = []
        for b in data.get("bookings", []):
            if (b.get("date") == date_str and b.get("time", "") > time_str and not b.get("notified_about_earlier_slot", False)):
                later_bookings.append(b)
        
        if not later_bookings:
            return
        
        for b in later_bookings:
            try:
                date_display = format_date_full_ru(date_str)
                message_text = f"🎉 Освободилось время на {date_display}:\n⏰ {time_str}\n\nВы записаны на {b.get('time', '')}. Хотите перенести?"
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="✅ Да, перенести", callback_data=f"reschedule_{date_str}_{time_str}_{b.get('date', '')}_{b.get('time', '')}")],
                    [InlineKeyboardButton(text="❌ Нет", callback_data="no_reschedule")]
                ])
                await safe_send_message(b["user_id"], message_text, reply_markup=keyboard)
                b["notified_about_earlier_slot"] = True
                save_data(data)
            except Exception as e:
                logger.error(f"Ошибка уведомления о переносе: {e}")
    except Exception as e:
        logger.error(f"Ошибка notify_clients: {e}")

@dp.callback_query(lambda c: c.data.startswith('reschedule_'))
async def reschedule_booking(callback_query: types.CallbackQuery, state: FSMContext):
    try:
        parts = callback_query.data.split('_')
        new_date = parts[1]
        new_time = parts[2]
        old_date = parts[3]
        old_time = parts[4]
        user_id = callback_query.from_user.id
        
        async with booking_lock:
            data = load_data()
            if data["schedule"].get(new_date, {}).get(new_time) != "free":
                await send_bot_message(
                    user_id,
                    callback_query.message.chat.id,
                    "⏰ Это время только что заняли. Ваша запись остаётся без изменений."
                )
                await show_main_menu(callback_query)
                await safe_answer(callback_query)
                return
            
            booking_to_move = None
            for b in data.get("bookings", []):
                if (b.get("user_id") == user_id and b.get("date") == old_date and b.get("time") == old_time):
                    booking_to_move = b
                    break
            
            if not booking_to_move:
                await send_bot_message(user_id, callback_query.message.chat.id, "Запись не найдена.")
                await show_main_menu(callback_query)
                await safe_answer(callback_query)
                return
            
            data["schedule"][old_date][old_time] = "free"
            data["schedule"][new_date][new_time] = "booked"
            booking_to_move["date"] = new_date
            booking_to_move["time"] = new_time
            booking_to_move["notified_about_earlier_slot"] = False
            booking_to_move["reminded_24h"] = False
            booking_to_move["reminded_2h"] = False
            booking_to_move["admin_reminded_2h"] = False
            save_data(data)
            
            date_display = format_date_full_ru(new_date)
            await send_bot_message(
                user_id,
                callback_query.message.chat.id,
                f"✅ Запись перенесена!\nНовая дата: {date_display}\nНовое время: {new_time}\n\nЖдём вас!"
            )
        
        await show_main_menu(callback_query)
        await safe_answer(callback_query)
    except Exception as e:
        logger.error(f"Ошибка переноса: {e}")

@dp.callback_query(lambda c: c.data == 'no_reschedule')
async def no_reschedule(callback_query: types.CallbackQuery, state: FSMContext):
    try:
        await send_bot_message(
            callback_query.from_user.id,
            callback_query.message.chat.id,
            "Хорошо, ваша запись остаётся без изменений."
        )
        await show_main_menu(callback_query)
        await safe_answer(callback_query)
    except Exception as e:
        logger.error(f"Ошибка отказа от переноса: {e}")

# ============================================================================
# КОМАНДА /start
# ============================================================================
@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    try:
        await state.clear()
        await show_main_menu(message)
    except Exception as e:
        logger.error(f"Ошибка /start: {e}")

# ============================================================================
# ОБРАБОТЧИК ВСЕХ СООБЩЕНИЙ
# ============================================================================
@dp.message()
async def show_menu_on_any_message(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    
    # Если пользователь в процессе верификации - не перехватываем
    if current_state is not None:
        return
    
    await show_main_menu(message)

# ============================================================================
# ЗДОРОВЬЕ СЕРВИСА (для Render.com)
# ============================================================================
async def health_check(request):
    return web.Response(text="OK")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", health_check)
    
    port = int(os.environ.get("PORT", 8080))
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    
    logger.info(f"✅ Health check сервер запущен на порту {port}")
    return runner

# ============================================================================
# ЗАПУСК БОТА
# ============================================================================
async def main():
    try:
        logger.info("Запуск бота...")
        
        if not isinstance(ADMIN_ID, int):
            logger.error("ADMIN_ID должен быть числом (без кавычек)!")
            return
        
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Webhook удален")
        
        web_runner = await start_web_server()
        
        asyncio.create_task(reminder_task())
        logger.info("Задача напоминаний запущена")
        
        logger.info("✅ Бот успешно запущен!")
        logger.info(f"👨‍💼 ADMIN_ID: {ADMIN_ID}")
        logger.info("Нажмите Ctrl+C для остановки")
        
        await dp.start_polling(bot)
    except KeyboardInterrupt:
        logger.info("👋 Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка в main: {e}", exc_info=True)
    finally:
        try:
            await bot.session.close()
            logger.info("Сессия бота закрыта")
        except:
            pass

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Бот остановлен")
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        logging.error(f"Критическая ошибка при запуске: {e}", exc_info=True)
