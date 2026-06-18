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
ADMIN_ID = 5023137327

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
booking_lock = asyncio.Lock()

# ============================================================================
# ССЫЛКИ
# ============================================================================
YANDEX_MAPS_URL = "https://yandex.by/maps/?text=Жлобин, ул. Матросова, 39"
INSTAGRAM_URL = "https://instagram.com/_novakeratin"
TELEGRAM_USERNAME = "@_novakeratin"
TELEGRAM_LINK = "https://t.me/_novakeratin"

# ============================================================================
# УПРАВЛЕНИЕ СООБЩЕНИЯМИ
# ============================================================================
user_messages = {}

def load_user_messages():
    try:
        filename = "user_messages.json"
        if os.path.exists(filename):
            with open(filename, "r", encoding="utf-8") as file:
                data = json.load(file)
                return {int(k): v for k, v in data.items()}
        return {}
    except Exception as e:
        logger.error(f"Ошибка загрузки user_messages: {e}")
        return {}

def save_user_messages():
    try:
        filename = "user_messages.json"
        data = {str(k): v for k, v in user_messages.items()}
        with open(filename, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения user_messages: {e}")

user_messages = load_user_messages()

async def send_bot_message(user_id, chat_id, text, reply_markup=None, parse_mode=None):
    try:
        msg = await bot.send_message(
            chat_id, 
            text, 
            reply_markup=reply_markup, 
            parse_mode=parse_mode
        )
        if user_id not in user_messages:
            user_messages[user_id] = []
        user_messages[user_id].append(msg.message_id)
        save_user_messages()
        return msg
    except Exception as e:
        logger.error(f"Ошибка отправки сообщения: {e}")
        return None

async def cleanup_previous_messages(user_id, chat_id, keep_message_id=None):
    if user_id not in user_messages:
        return
    
    message_ids = user_messages[user_id].copy()
    
    for msg_id in message_ids:
        if keep_message_id and msg_id == keep_message_id:
            continue
        
        try:
            await bot.delete_message(chat_id=chat_id, message_id=msg_id)
            if msg_id in user_messages.get(user_id, []):
                user_messages[user_id].remove(msg_id)
        except Exception as e:
            if msg_id in user_messages.get(user_id, []):
                user_messages[user_id].remove(msg_id)
            logger.debug(f"Не удалось удалить сообщение {msg_id}: {e}")
        
        await asyncio.sleep(0.05)
    
    save_user_messages()

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
# ПРОГРАММА ЛОЯЛЬНОСТИ
# ============================================================================
def load_loyalty_data():
    """Загружает данные программы лояльности"""
    try:
        filename = "loyalty.json"
        if os.path.exists(filename):
            with open(filename, "r", encoding="utf-8") as file:
                return json.load(file)
        return {}
    except Exception as e:
        logger.error(f"Ошибка загрузки loyalty: {e}")
        return {}

def save_loyalty_data(data):
    """Сохраняет данные программы лояльности"""
    try:
        filename = "loyalty.json"
        with open(filename, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения loyalty: {e}")

def get_user_visits(user_id):
    """Получает количество посещений пользователя"""
    loyalty = load_loyalty_data()
    return loyalty.get(str(user_id), {}).get("visits", 0)

def increment_user_visits(user_id):
    """Увеличивает счётчик посещений пользователя"""
    loyalty = load_loyalty_data()
    user_id_str = str(user_id)
    
    if user_id_str not in loyalty:
        loyalty[user_id_str] = {"visits": 0, "total_spent": 0}
    
    loyalty[user_id_str]["visits"] = loyalty[user_id_str].get("visits", 0) + 1
    save_loyalty_data(loyalty)
    
    return loyalty[user_id_str]["visits"]

def get_user_discount(user_id):
    """Возвращает процент скидки для пользователя"""
    visits = get_user_visits(user_id)
    
    if visits >= 5:
        return 15
    elif visits >= 3:
        return 10
    else:
        return 0

def get_discount_message(user_id):
    """Возвращает сообщение о текущей скидке и прогрессе"""
    visits = get_user_visits(user_id)
    discount = get_user_discount(user_id)
    
    if visits >= 5:
        return f"🎁 <b>Ваша скидка: {discount}%</b>\n\nВы наш постоянный клиент! Скидка 15% на все процедуры."
    elif visits >= 3:
        next_discount_at = 5
        remaining = next_discount_at - visits
        return f"🎁 <b>Ваша скидка: {discount}%</b>\n\nДо скидки 15% осталось ещё {remaining} визит(ов)."
    else:
        next_discount_at = 3
        remaining = next_discount_at - visits
        return f" <b>Программа лояльности</b>\n\nУ вас {visits} визит(ов).\nДо скидки 10% осталось {remaining} визит(ов).\n\n3 визита = 10% скидка\n5 визитов = 15% скидка"

# ============================================================================
# УВЕДОМЛЕНИЯ МАСТЕРУ
# ============================================================================
async def send_admin_notification(text):
    try:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=" Открыть меню", callback_data="back_to_menu")]
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

class ReviewState(StatesGroup):
    waiting_for_rating = State()
    waiting_for_review_text = State()

# ============================================================================
# ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ: Кнопка меню
# ============================================================================
def get_menu_button():
    return InlineKeyboardButton(text="🏠 Меню", callback_data="back_to_menu")

def add_menu_button(keyboard):
    keyboard.inline_keyboard.append([get_menu_button()])
    return keyboard

# ============================================================================
# ГЛАВНОЕ МЕНЮ (с новой кнопкой FAQ)
# ============================================================================
async def show_main_menu(message_or_callback):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Записаться", callback_data="start_booking")],
        [InlineKeyboardButton(text="📋 Мои записи", callback_data="my_bookings")],
        [InlineKeyboardButton(text="❓ Частые вопросы", callback_data="faq")],  # НОВАЯ КНОПКА
        [InlineKeyboardButton(text="❗ Противопоказания", callback_data="contraindications_info")],
        [InlineKeyboardButton(text="📍 Как добраться", callback_data="how_to_get")]
    ])
    
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
        
        msg = await bot.send_message(chat_id, text, reply_markup=keyboard, parse_mode="HTML")
        
        if user_id not in user_messages:
            user_messages[user_id] = []
        user_messages[user_id].append(msg.message_id)
        save_user_messages()
        
        await cleanup_previous_messages(user_id, chat_id, keep_message_id=msg.message_id)
    else:
        user_id = message_or_callback.from_user.id
        chat_id = message_or_callback.message.chat.id
        
        try:
            await message_or_callback.message.edit_text(
                text=text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            if user_id in user_messages:
                user_messages[user_id] = [message_or_callback.message.message_id]
            else:
                user_messages[user_id] = [message_or_callback.message.message_id]
            save_user_messages()
        except Exception as e:
            msg = await message_or_callback.message.answer(text, reply_markup=keyboard, parse_mode="HTML")
            if user_id not in user_messages:
                user_messages[user_id] = []
            user_messages[user_id].append(msg.message_id)
            save_user_messages()
            await cleanup_previous_messages(user_id, chat_id, keep_message_id=msg.message_id)

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
# НАПОМИНАНИЯ (включая сбор отзывов)
# ============================================================================
async def reminder_task():
    logger.info("🔔 Задача напоминаний запущена!")
    while True:
        try:
            await check_and_send_reminders()
            await check_and_send_review_requests()  # НОВАЯ ФУНКЦИЯ
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

async def check_and_send_review_requests():
    """Отправляет запрос отзыва через 3 часа после окончания записи"""
    try:
        data = load_data()
        now = datetime.now()
        
        for b in data.get("bookings", []):
            if "user_id" not in b:
                continue
            
            if b.get("review_requested", False):
                continue
            
            try:
                dt = datetime.strptime(f"{b.get('date', '')} {b.get('time', '')}", "%Y-%m-%d %H:%M")
                duration = get_service_duration(b.get("service", ""))
                end_dt = dt + timedelta(hours=duration)
                
                hours_after = (now - end_dt).total_seconds() / 3600
                
                if 3 <= hours_after <= 3.1:
                    await send_review_request(b)
                    b["review_requested"] = True
                    save_data(data)
            except:
                continue
    except Exception as e:
        logger.error(f"Ошибка проверки отзывов: {e}")

async def send_review_request(booking):
    """Отправляет клиенту запрос отзыва"""
    try:
        text = (
            f"⭐ <b>Как вам процедура?</b>\n\n"
            f"Здравствуйте, <b>{booking.get('name', 'Клиент')}</b>!\n\n"
            f"Надеемся, вам понравился визит. Пожалуйста, оцените качество услуги от 1 до 5:\n\n"
            f"1 — 😞 Очень плохо\n"
            f"2 — 😕 Плохо\n"
            f"3 — 😐 Нормально\n"
            f"4 — 😊 Хорошо\n"
            f"5 — 🤩 Отлично"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="1", callback_data=f"review_1_{booking.get('date', '')}_{booking.get('time', '')}")],
            [InlineKeyboardButton(text="2", callback_data=f"review_2_{booking.get('date', '')}_{booking.get('time', '')}")],
            [InlineKeyboardButton(text="3", callback_data=f"review_3_{booking.get('date', '')}_{booking.get('time', '')}")],
            [InlineKeyboardButton(text="4", callback_data=f"review_4_{booking.get('date', '')}_{booking.get('time', '')}")],
            [InlineKeyboardButton(text="5", callback_data=f"review_5_{booking.get('date', '')}_{booking.get('time', '')}")]
        ])
        
        await safe_send_message(booking["user_id"], text, parse_mode="HTML", reply_markup=keyboard)
        logger.info(f"✅ Запрос отзыва отправлен клиенту {booking['user_id']}")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки запроса отзыва: {e}")

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
# FAQ (ЧАСТЫЕ ВОПРОСЫ) - НОВАЯ ФУНКЦИЯ
# ============================================================================
@dp.callback_query(lambda c: c.data == 'faq')
async def faq(callback_query: types.CallbackQuery, state: FSMContext):
    try:
        text = (
            f" <b>Частые вопросы</b>\n\n"
            f"<b>1. Сколько держится эффект кератина?</b>\n"
            f"Эффект длится 3-4 месяца при правильном уходе.\n\n"
            f"<b>2. Нужно ли мыть голову перед процедурой?</b>\n"
            f"Да, волосы должны быть чистыми. Если вы моете голову утром — это идеально.\n\n"
            f"<b>3. Можно ли красить волосы после кератина?</b>\n"
            f"Рекомендуется подождать 2 недели после процедуры.\n\n"
            f"<b>4. Как ухаживать после процедуры?</b>\n"
            f"Используйте безсульфатные шампуни, избегайте морской воды первые 2 недели.\n\n"
            f"<b>5. Какие составы вы используете?</b>\n"
            f"Профессиональные составы премиум-класса (Brazil, Japan).\n\n"
            f"<b>6. Больно ли делать процедуру?</b>\n"
            f"Нет, процедура комфортная. Возможно лёгкое пощипывание при нанесении состава.\n\n"
            f"<b>7. Можно ли делать беременным?</b>\n"
            f"Нет, беременность является противопоказанием.\n\n"
            f"❗ <b>Есть другие вопросы?</b>\n"
            f"Напишите мастеру: <a href='{TELEGRAM_LINK}'>{TELEGRAM_USERNAME}</a>"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📅 Записаться", callback_data="start_booking")],
            [InlineKeyboardButton(text="◂ Назад", callback_data="back_to_menu")]
        ])
        keyboard = add_menu_button(keyboard)
        
        await send_bot_message(
            callback_query.from_user.id,
            callback_query.message.chat.id,
            text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        await safe_answer(callback_query)
    except Exception as e:
        logger.error(f"Ошибка FAQ: {e}")

# ============================================================================
# ОБРАБОТЧИК ОТЗЫВОВ - НОВАЯ ФУНКЦИЯ
# ============================================================================
@dp.callback_query(lambda c: c.data.startswith('review_'))
async def process_review(callback_query: types.CallbackQuery, state: FSMContext):
    try:
        parts = callback_query.data.split('_')
        rating = int(parts[1])
        date_str = parts[2]
        time_str = parts[3]
        user_id = callback_query.from_user.id
        
        # Находим запись
        data = load_data()
        booking = None
        for b in data.get("bookings", []):
            if b.get("date") == date_str and b.get("time") == time_str and b.get("user_id") == user_id:
                booking = b
                break
        
        if not booking:
            await send_bot_message(user_id, callback_query.message.chat.id, "❌ Запись не найдена.")
            await safe_answer(callback_query)
            return
        
        if rating >= 4:
            # Хорошая оценка - просим написать отзыв
            text = (
                f"🎉 <b>Спасибо за высокую оценку!</b>\n\n"
                f"Мы рады, что вам понравилось!\n\n"
                f"Можете написать краткий отзыв о процедуре? Это поможет другим клиентам.\n\n"
                f"<i>Или пропустите этот шаг — ваше мнение уже важно для нас! ✨</i>"
            )
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✍️ Написать отзыв", callback_data=f"review_text_{date_str}_{time_str}")],
                [InlineKeyboardButton(text="⏭️ Пропустить", callback_data="review_skip")]
            ])
            keyboard = add_menu_button(keyboard)
            
            await send_bot_message(user_id, callback_query.message.chat.id, text, reply_markup=keyboard, parse_mode="HTML")
        else:
            # Плохая оценка - уведомляем мастера
            service_name = booking.get("service_name", get_service_name(booking.get("service", "")))
            
            alert_text = (
                f"️ <b>Низкая оценка от клиента!</b>\n\n"
                f"👤 <b>{booking.get('name', '')}</b>\n"
                f"📞 {booking.get('phone', '')}\n"
                f"📅 {format_date_full_ru(date_str)} {time_str}\n"
                f"💆‍♀️ {service_name}\n"
                f"⭐ Оценка: {rating}/5\n\n"
                f"Рекомендуется связаться с клиентом для уточнения ситуации."
            )
            
            await send_admin_alert(alert_text)
            
            text = (
                f"😔 <b>Нам жаль, что вам не понравилось.</b>\n\n"
                f"Мастер свяжется с вами для уточнения деталей.\n\n"
                f"Спасибо за честную оценку!"
            )
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🏠 В главное меню", callback_data="back_to_menu")]
            ])
            
            await send_bot_message(user_id, callback_query.message.chat.id, text, reply_markup=keyboard, parse_mode="HTML")
        
        await safe_answer(callback_query)
    except Exception as e:
        logger.error(f"Ошибка обработки отзыва: {e}")

@dp.callback_query(lambda c: c.data.startswith('review_text_'))
async def request_review_text(callback_query: types.CallbackQuery, state: FSMContext):
    try:
        parts = callback_query.data.split('_')
        date_str = parts[2]
        time_str = parts[3]
        
        await state.update_data(review_date=date_str, review_time=time_str)
        await state.set_state(ReviewState.waiting_for_review_text)
        
        text = (
            f"✍️ <b>Напишите ваш отзыв</b>\n\n"
            f"Что вам понравилось? Что можно улучшить?\n\n"
            f"<i>Ваш отзыв будет опубликован в Instagram с вашего разрешения.</i>"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=" Отмена", callback_data="review_skip")]
        ])
        keyboard = add_menu_button(keyboard)
        
        await send_bot_message(
            callback_query.from_user.id,
            callback_query.message.chat.id,
            text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        await safe_answer(callback_query)
    except Exception as e:
        logger.error(f"Ошибка запроса текста отзыва: {e}")

@dp.message(ReviewState.waiting_for_review_text)
async def process_review_text(message: types.Message, state: FSMContext):
    try:
        user_data = await state.get_data()
        date_str = user_data.get('review_date', '')
        time_str = user_data.get('review_time', '')
        
        review_text = message.text
        
        # Сохраняем отзыв
        reviews = load_reviews()
        if str(message.from_user.id) not in reviews:
            reviews[str(message.from_user.id)] = []
        
        reviews[str(message.from_user.id)].append({
            "date": datetime.now().isoformat(),
            "booking_date": date_str,
            "booking_time": time_str,
            "text": review_text,
            "rating": 5  # Предполагаем высокую оценку, раз клиент пишет отзыв
        })
        save_reviews(reviews)
        
        # Уведомляем мастера
        alert_text = (
            f"⭐ <b>Новый отзыв от клиента!</b>\n\n"
            f"👤 {message.from_user.first_name}\n"
            f"📅 {format_date_full_ru(date_str)} {time_str}\n\n"
            f"<b>Отзыв:</b>\n{review_text}"
        )
        await send_admin_alert(alert_text)
        
        text = (
            f"✅ <b>Спасибо за отзыв!</b>\n\n"
            f"Ваше мнение очень важно для нас. ✨\n\n"
            f"Мы опубликуем его в Instagram @_novakeratin"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=" В главное меню", callback_data="back_to_menu")]
        ])
        
        await state.clear()
        await send_bot_message(message.from_user.id, message.chat.id, text, reply_markup=keyboard, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Ошибка обработки текста отзыва: {e}")

@dp.callback_query(lambda c: c.data == 'review_skip')
async def skip_review(callback_query: types.CallbackQuery, state: FSMContext):
    try:
        await state.clear()
        
        text = (
            f"✅ <b>Спасибо за оценку!</b>\n\n"
            f"Ваше мнение важно для нас. ✨"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 В главное меню", callback_data="back_to_menu")]
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
        logger.error(f"Ошибка пропуска отзыва: {e}")

def load_reviews():
    try:
        filename = "reviews.json"
        if os.path.exists(filename):
            with open(filename, "r", encoding="utf-8") as file:
                return json.load(file)
        return {}
    except:
        return {}

def save_reviews(data):
    try:
        filename = "reviews.json"
        with open(filename, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения отзывов: {e}")

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
            f" <b>Образование:</b> профессиональные курсы по кератиновому выпрямлению и восстановлению волос\n"
            f"💎 <b>Специализация:</b> все виды реконструкции волос\n\n"
            f"📸 <b>Портфолио работ:</b>\n<a href='{TELEGRAM_LINK}'>{TELEGRAM_USERNAME}</a>\n\n"
            f" <b>Адрес:</b> ул. Матросова, 39, 1 этаж (Жлобин)\n"
            f" <b>Время работы:</b> Суббота и Воскресенье, 9:00-17:00"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◂ Назад", callback_data="back_to_menu")]
        ])
        keyboard = add_menu_button(keyboard)
        
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
            f"<a href='{TELEGRAM_LINK}'>{TELEGRAM_USERNAME}</a>"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📸 Открыть Instagram", url=INSTAGRAM_URL)],
            [InlineKeyboardButton(text="◂ Назад", callback_data="back_to_menu")]
        ])
        keyboard = add_menu_button(keyboard)
        
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
            f"📞 <b>Консультация:</b> <a href='{TELEGRAM_LINK}'>{TELEGRAM_USERNAME}</a>"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📅 Записаться", callback_data="start_booking")],
            [InlineKeyboardButton(text="◂ Назад", callback_data="back_to_menu")]
        ])
        keyboard = add_menu_button(keyboard)
        
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
        keyboard = add_menu_button(keyboard)
        
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
# АДМИН-ПАНЕЛЬ (с статистикой)
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
                [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
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
                    f"   {b.get('time', '')} — {end_time}\n"
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
            
            keyboard_buttons.append([InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")])
            keyboard_buttons.append([InlineKeyboardButton(text=" В главное меню", callback_data="back_to_menu")])
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

# ============================================================================
# СТАТИСТИКА ДЛЯ МАСТЕРА - НОВАЯ ФУНКЦИЯ
# ============================================================================
@dp.callback_query(lambda c: c.data == 'admin_stats')
async def admin_stats(callback_query: types.CallbackQuery, state: FSMContext):
    try:
        if callback_query.from_user.id != ADMIN_ID:
            await safe_answer(callback_query, "⛔ Только для мастера", show_alert=True)
            return
        
        data = load_data()
        bookings = data.get("bookings", [])
        
        if not bookings:
            text = (
                f"📊 <b>Статистика</b>\n\n"
                f"<i>Пока нет данных для статистики</i>\n\n"
                f"Статистика появится после первых записей."
            )
        else:
            now = datetime.now()
            
            # Статистика за неделю
            week_ago = now - timedelta(days=7)
            week_bookings = [b for b in bookings if datetime.strptime(f"{b.get('date', '')} {b.get('time', '')}", "%Y-%m-%d %H:%M") >= week_ago]
            
            # Статистика за месяц
            month_ago = now - timedelta(days=30)
            month_bookings = [b for b in bookings if datetime.strptime(f"{b.get('date', '')} {b.get('time', '')}", "%Y-%m-%d %H:%M") >= month_ago]
            
            # Подсчёт по услугам
            service_counts = {}
            service_revenue = {}
            for b in bookings:
                service = b.get("service", "")
                service_name = get_service_name(service)
                price = get_service_price(service)
                
                service_counts[service_name] = service_counts.get(service_name, 0) + 1
                service_revenue[service_name] = service_revenue.get(service_name, 0) + price
            
            # Общая выручка
            total_revenue = sum(get_service_price(b.get("service", "")) for b in bookings)
            week_revenue = sum(get_service_price(b.get("service", "")) for b in week_bookings)
            month_revenue = sum(get_service_price(b.get("service", "")) for b in month_bookings)
            
            # Уникальные клиенты
            unique_clients = len(set(b.get("user_id") for b in bookings))
            
            text = (
                f" <b>Статистика</b>\n\n"
                f"<b> За неделю:</b>\n"
                f"  Записей: {len(week_bookings)}\n"
                f"  Выручка: {week_revenue} BYN\n\n"
                f"<b>📅 За месяц:</b>\n"
                f"  Записей: {len(month_bookings)}\n"
                f"  Выручка: {month_revenue} BYN\n\n"
                f"<b>📈 Всего:</b>\n"
                f"  Записей: {len(bookings)}\n"
                f"  Выручка: {total_revenue} BYN\n"
                f"  Клиентов: {unique_clients}\n\n"
                f"<b> Популярные услуги:</b>\n"
            )
            
            sorted_services = sorted(service_counts.items(), key=lambda x: x[1], reverse=True)
            for service_name, count in sorted_services[:3]:
                revenue = service_revenue[service_name]
                text += f"  {service_name}: {count} ({revenue} BYN)\n"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")]
        ])
        keyboard = add_menu_button(keyboard)
        
        await send_bot_message(
            callback_query.from_user.id,
            callback_query.message.chat.id,
            text,
            parse_mode="HTML",
            reply_markup=keyboard
        )
        await safe_answer(callback_query)
    except Exception as e:
        logger.error(f"Ошибка статистики: {e}")

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
                f"⚠️ Ваша запись на {date_display} в {time_str} была отменена мастером.\n\nПриносим извинения за неудобства. Пожалуйста, свяжитесь с мастером для уточнения деталей: <a href='{TELEGRAM_LINK}'>{TELEGRAM_USERNAME}</a>",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Не удалось уведомить клиента об отмене: {e}")
        
        await send_bot_message(
            callback_query.from_user.id,
            callback_query.message.chat.id,
            f"✅ Запись отменена:\n{booking_to_cancel.get('name', '')} - {date_display} {time_str}"
        )
        
        await callback_query.message.delete()
        await admin_panel(callback_query, state)
        
        await safe_answer(callback_query, "Запись отменена")
    except Exception as e:
        logger.error(f"Ошибка отмены записи мастером: {e}")

@dp.callback_query(lambda c: c.data == 'back_to_menu')
async def back_to_menu(callback_query: types.CallbackQuery, state: FSMContext):
    try:
        user_id = callback_query.from_user.id
        chat_id = callback_query.message.chat.id
        
        try:
            await callback_query.message.delete()
            if user_id in user_messages and callback_query.message.message_id in user_messages[user_id]:
                user_messages[user_id].remove(callback_query.message.message_id)
                save_user_messages()
        except:
            pass
        
        await state.clear()
        await show_main_menu(callback_query)
        
        if user_id in user_messages and len(user_messages[user_id]) > 0:
            menu_message_id = user_messages[user_id][-1]
            await cleanup_previous_messages(user_id, chat_id, keep_message_id=menu_message_id)
    except Exception as e:
        logger.error(f"Ошибка возврата в меню: {e}")

# ============================================================================
# НАЧАЛО ЗАПИСИ (с программой лояльности)
# ============================================================================
@dp.callback_query(lambda c: c.data == 'start_booking')
async def process_start_booking(callback_query: types.CallbackQuery, state: FSMContext):
    try:
        user_id = callback_query.from_user.id
        chat_id = callback_query.message.chat.id
        
        try:
            await callback_query.message.delete()
            if user_id in user_messages and callback_query.message.message_id in user_messages[user_id]:
                user_messages[user_id].remove(callback_query.message.message_id)
                save_user_messages()
        except:
            pass
        
        verified_user = get_verified_user(user_id)
        
        if verified_user:
            await state.update_data(
                name=verified_user["name"],
                phone=verified_user["phone"]
            )
            await state.set_state(BookingState.waiting_for_service)
            
            # Получаем информацию о скидке
            discount = get_user_discount(user_id)
            visits = get_user_visits(user_id)
            
            discount_text = ""
            if discount > 0:
                discount_text = f"\n <b>Ваша скидка: {discount}%</b> (визитов: {visits})"
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❄️ Холодное восстановление — 80 BYN", callback_data="service_cold_restoration")],
                [InlineKeyboardButton(text="✨ Кератин / Ботокс — 150 BYN", callback_data="service_keratin_botox")],
                [InlineKeyboardButton(text=" Тотальная реконструкция — 200 BYN", callback_data="service_total_reconstruction")],
                [InlineKeyboardButton(text="◂ Назад", callback_data="back_to_menu")]
            ])
            keyboard = add_menu_button(keyboard)
            
            await send_bot_message(
                user_id,
                chat_id,
                f"✅ С возвращением, <b>{verified_user['name']}</b>!{discount_text}\n\nВыберите услугу:",
                reply_markup=keyboard,
                parse_mode="HTML"
            )
        else:
            await state.set_state(BookingState.waiting_for_contact)
            
            contact_keyboard = ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="📱 Поделиться контактом", request_contact=True)],
                    [KeyboardButton(text="❌ Отмена")]
                ],
                resize_keyboard=True,
                one_time_keyboard=True
            )
            
            await send_bot_message(
                user_id,
                chat_id,
                f" <b>Запись на процедуру</b>\n\n"
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
    try:
        user_id = message.from_user.id
        chat_id = message.chat.id
        
        try:
            await message.delete()
            if user_id in user_messages and message.message_id in user_messages[user_id]:
                user_messages[user_id].remove(message.message_id)
                save_user_messages()
        except:
            pass
        
        if message.text and "Отмена" in message.text:
            await state.clear()
            await show_main_menu(message)
            return
        
        if not message.contact:
            await send_bot_message(
                user_id,
                chat_id,
                " Пожалуйста, нажмите кнопку «📱 Поделиться контактом» для подтверждения номера телефона."
            )
            return
        
        contact = message.contact
        phone = contact.phone_number
        name = contact.first_name or "Клиент"
        
        if contact.last_name:
            name = f"{contact.first_name} {contact.last_name}"
        
        save_verified_user(user_id, name, phone)
        
        await state.update_data(name=name, phone=phone)
        await state.set_state(BookingState.waiting_for_service)
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❄️ Холодное восстановление — 80 BYN", callback_data="service_cold_restoration")],
            [InlineKeyboardButton(text="✨ Кератин / Ботокс — 150 BYN", callback_data="service_keratin_botox")],
            [InlineKeyboardButton(text="💎 Тотальная реконструкция — 200 BYN", callback_data="service_total_reconstruction")],
            [InlineKeyboardButton(text="◂ Назад", callback_data="back_to_menu")]
        ])
        keyboard = add_menu_button(keyboard)
        
        await send_bot_message(
            user_id,
            chat_id,
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
                user_id,
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
        keyboard = add_menu_button(keyboard)
        
        service_name = get_service_name(service_code)
        
        await send_bot_message(
            user_id,
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
        keyboard = add_menu_button(keyboard)
        
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
# ВЫБОР ВРЕМЕНИ (с программой лояльности)
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
        
        # Увеличиваем счётчик посещений
        user_id = callback_query.from_user.id
        visits = increment_user_visits(user_id)
        discount = get_user_discount(user_id)
        
        # Применяем скидку
        final_price = price
        if discount > 0:
            final_price = int(price * (100 - discount) / 100)
        
        async with booking_lock:
            data = load_data()
            
            if data["schedule"].get(date_str, {}).get(time_str) != "free":
                await send_bot_message(
                    callback_query.from_user.id,
                    callback_query.message.chat.id,
                    " К сожалению, этот слот только что заняли. Пожалуйста, выберите другое время."
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
                "admin_reminded_2h": False,
                "review_requested": False,
                "discount_applied": discount,
                "final_price": final_price
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
            f"💰 {final_price} BYN"
        )
        if discount > 0:
            admin_text += f"\n🎁 Скидка: {discount}% (визит #{visits})"
        
        await send_admin_notification(admin_text)
        
        date_display = format_date_full_ru(date_str)
        start_hour, start_min = map(int, time_str.split(':'))
        end_hour = start_hour + int(duration)
        end_min = start_min + int((duration % 1) * 60)
        if end_min >= 60:
            end_hour += 1
            end_min -= 60
        end_time = f"{end_hour:02d}:{end_min:02d}"
        
        discount_info = ""
        if discount > 0:
            discount_info = f"\n <b>Применена скидка {discount}%!</b>\n💰 Итого: {final_price} BYN (вместо {price} BYN)"
        else:
            discount_info = f"\n💰 {price} BYN"
        
        final_message = (
            f"✅ <b>Запись подтверждена!</b>\n\n"
            f"Отлично, <b>{user_data.get('name', '')}</b>! ✨\n\n"
            f"Вы записаны на:\n"
            f"💆‍♀️ {service_name}\n\n"
            f"📅 {date_display}\n"
            f"⏰ {time_str} — {end_time}\n"
            f"{discount_info}\n\n"
            f" <b>Адрес:</b>\nул. Матросова, 39, 1 этаж\n(напротив Светофор, Мастак)\n\n"
            f"📞 <b>Контакты:</b>\n<a href='{TELEGRAM_LINK}'>{TELEGRAM_USERNAME}</a>\n\n"
            f"🔔 Мы напомним вам о записи за 24 часа до визита.\n\n"
            f"<i>Ждём вас! ✨</i>"
        )
        
        final_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=" В главное меню", callback_data="back_to_menu")]
        ])
        
        await state.clear()
        await send_bot_message(
            callback_query.from_user.id,
            callback_query.message.chat.id,
            final_message,
            reply_markup=final_keyboard,
            parse_mode="HTML"
        )
        await safe_answer(callback_query)
    except Exception as e:
        logger.error(f"Ошибка выбора времени: {e}")

# ============================================================================
# МОИ ЗАПИСИ (с программой лояльности)
# ============================================================================
@dp.callback_query(lambda c: c.data == 'my_bookings')
async def show_my_bookings(callback_query: types.CallbackQuery, state: FSMContext):
    try:
        await state.clear()
        user_id = callback_query.from_user.id
        data = load_data()
        user_bookings = [b for b in data.get("bookings", []) if b.get("user_id") == user_id]
        
        # Получаем информацию о лояльности
        visits = get_user_visits(user_id)
        discount = get_user_discount(user_id)
        loyalty_message = get_discount_message(user_id)
        
        if not user_bookings:
            text = f"У вас нет активных записей.\n\n{loyalty_message}"
            await send_bot_message(user_id, callback_query.message.chat.id, text, parse_mode="HTML")
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
            price = b.get("final_price", get_service_price(b.get("service", "")))
            
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
        
        bookings_text += f"{THIN_DIVIDER}\n{loyalty_message}"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отменить запись", callback_data="cancel_booking")],
            [InlineKeyboardButton(text="◂ Назад", callback_data="back_to_menu")]
        ])
        keyboard = add_menu_button(keyboard)
        
        await send_bot_message(user_id, callback_query.message.chat.id, bookings_text, parse_mode="HTML", reply_markup=keyboard)
        await safe_answer(callback_query)
    except Exception as e:
        logger.error(f"Ошибка показа записей: {e}")

# ============================================================================
# ОТМЕНА ЗАПИСИ
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
        keyboard = add_menu_button(keyboard)
        
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
                    [InlineKeyboardButton(text=" Нет", callback_data="no_reschedule")]
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
    
    if current_state is not None:
        return
    
    try:
        await message.delete()
    except:
        pass
    
    await show_main_menu(message)

# ============================================================================
# ЗДОРОВЬЕ СЕРВИСА
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
        logger.info(f"👨💼 ADMIN_ID: {ADMIN_ID}")
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
        print(f" Критическая ошибка: {e}")
        logging.error(f"Критическая ошибка при запуске: {e}", exc_info=True)
