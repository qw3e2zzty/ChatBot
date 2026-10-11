import asyncio
import html
import logging
import os
import sqlite3
from contextlib import closing
from datetime import datetime

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))  # ваш Telegram ID, сюда приходят заявки
DB_PATH = os.getenv("DB_PATH", "leads.db")  # на Railway: /data/leads.db (том)


# ---------- База данных ----------
def init_db():
    with closing(sqlite3.connect(DB_PATH)) as db:
        db.execute(
            """CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT,
                program TEXT,
                name TEXT,
                contact TEXT,
                tg_username TEXT,
                tg_id INTEGER
            )"""
        )
        db.commit()


def save_lead(program, name, contact, tg_username, tg_id):
    with closing(sqlite3.connect(DB_PATH)) as db:
        db.execute(
            "INSERT INTO leads (created_at, program, name, contact, tg_username, tg_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (datetime.now().strftime("%Y-%m-%d %H:%M"), program, name, contact, tg_username, tg_id),
        )
        db.commit()


def get_leads(limit=10):
    with closing(sqlite3.connect(DB_PATH)) as db:
        return db.execute(
            "SELECT id, created_at, program, name, contact FROM leads ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()

# ---------- Данные (редактируйте под себя) ----------
TRAINER_NAME = "Анна"
ABOUT = (
    f"👋 Я {TRAINER_NAME}, тренер по стретчингу.\n\n"
    "• Опыт: 7 лет\n"
    "• Работаю с новичками и с теми, кто давно «деревянный»\n"
    "• Формат: индивидуально, мини-группы, онлайн\n\n"
    "Цель — гибкость без боли и с безопасной техникой."
)
CONTACTS = "📍 Адрес: ул. Примерная, 1\n📞 +7 900 000-00-00\n🕒 Пн–Сб, 9:00–21:00"

CATALOG = [
    {
        "id": "trial",
        "title": "Пробное занятие",
        "price": "500 ₽",
        "desc": "60 минут. Диагностика гибкости, знакомство с техникой, план под вашу цель.",
    },
    {
        "id": "personal",
        "title": "Персональная тренировка",
        "price": "2 500 ₽ / занятие",
        "desc": "Индивидуальная программа: шпагат, спина, бёдра — что нужно именно вам.",
    },
    {
        "id": "group",
        "title": "Мини-группа (до 6 человек)",
        "price": "8 000 ₽ / месяц",
        "desc": "8 занятий в месяц, 3 раза в неделю на выбор. Для регулярной практики.",
    },
    {
        "id": "online",
        "title": "Онлайн-программа",
        "price": "4 500 ₽ / месяц",
        "desc": "Видеоуроки, чат с тренером и разбор техники по видео.",
    },
]
ITEMS = {i["id"]: i for i in CATALOG}

FAQ = (
    "❓ <b>Частые вопросы</b>\n\n"
    "<b>Нужна ли подготовка?</b> Нет, начинаем с вашего уровня.\n"
    "<b>Есть ли противопоказания?</b> Да, при травмах позвоночника и суставов "
    "сначала консультация врача.\n"
    "<b>Что взять с собой?</b> Удобную одежду, коврик есть в зале."
)


# ---------- Клавиатуры ----------
def main_menu():
    kb = InlineKeyboardBuilder()
    kb.button(text="📋 Каталог программ", callback_data="catalog")
    kb.button(text="✍️ Записаться", callback_data="book:any")
    kb.button(text="👩‍🏫 О тренере", callback_data="about")
    kb.button(text="❓ Вопросы", callback_data="faq")
    kb.button(text="📞 Контакты", callback_data="contacts")
    kb.adjust(1, 1, 2, 1)
    return kb.as_markup()


def catalog_menu():
    kb = InlineKeyboardBuilder()
    for item in CATALOG:
        kb.button(text=f"{item['title']} — {item['price']}", callback_data=f"item:{item['id']}")
    kb.button(text="⬅️ В меню", callback_data="menu")
    kb.adjust(1)
    return kb.as_markup()


def item_menu(item_id: str):
    kb = InlineKeyboardBuilder()
    kb.button(text="✍️ Записаться", callback_data=f"book:{item_id}")
    kb.button(text="⬅️ К каталогу", callback_data="catalog")
    kb.adjust(1)
    return kb.as_markup()


def back_menu():
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ В меню", callback_data="menu")
    return kb.as_markup()


# ---------- Состояния записи ----------
class Booking(StatesGroup):
    name = State()
    phone = State()


router = Router()
WELCOME = "Привет! Я бот тренера по стретчингу 🧘‍♀️\nВыберите, что вас интересует:"


async def show(cb: CallbackQuery, text: str, markup):
    await cb.message.edit_text(text, reply_markup=markup)
    await cb.answer()


@router.message(CommandStart())
@router.message(Command("menu"))
async def start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(WELCOME, reply_markup=main_menu())


@router.message(Command("leads"))
async def show_leads(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.clear()
    rows = get_leads(10)
    if not rows:
        await message.answer("Заявок пока нет.")
        return
    lines = ["📒 <b>Последние заявки</b>\n"]
    for lead_id, created, program, name, contact in rows:
        lines.append(
            f"#{lead_id} · {created}\n"
            f"{html.escape(program)} — {html.escape(name)}, {html.escape(contact)}\n"
        )
    await message.answer("\n".join(lines))


@router.callback_query(F.data == "menu")
async def cb_menu(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await show(cb, WELCOME, main_menu())


@router.callback_query(F.data == "catalog")
async def cb_catalog(cb: CallbackQuery):
    await show(cb, "📋 <b>Каталог программ</b>\nВыберите, чтобы узнать подробнее:", catalog_menu())


@router.callback_query(F.data.startswith("item:"))
async def cb_item(cb: CallbackQuery):
    item = ITEMS[cb.data.split(":")[1]]
    text = f"<b>{item['title']}</b>\n\n{item['desc']}\n\n💰 {item['price']}"
    await show(cb, text, item_menu(item["id"]))


@router.callback_query(F.data == "about")
async def cb_about(cb: CallbackQuery):
    await show(cb, ABOUT, back_menu())


@router.callback_query(F.data == "faq")
async def cb_faq(cb: CallbackQuery):
    await show(cb, FAQ, back_menu())


@router.callback_query(F.data == "contacts")
async def cb_contacts(cb: CallbackQuery):
    await show(cb, CONTACTS, back_menu())


# ---------- Запись ----------
@router.callback_query(F.data.startswith("book:"))
async def cb_book(cb: CallbackQuery, state: FSMContext):
    item_id = cb.data.split(":")[1]
    program = ITEMS[item_id]["title"] if item_id in ITEMS else "Не выбрана"
    await state.update_data(program=program)
    await state.set_state(Booking.name)
    await cb.message.answer("Как вас зовут?")
    await cb.answer()


@router.message(Booking.name, F.text)
async def book_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await state.set_state(Booking.phone)
    await message.answer("Оставьте номер телефона или @username для связи:")


@router.message(Booking.phone, F.text)
async def book_phone(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    await state.clear()
    contact = message.text.strip()
    save_lead(
        data["program"], data["name"], contact,
        message.from_user.username or "", message.from_user.id,
    )
    lead = (
        "🔔 <b>Новая заявка</b>\n"
        f"Программа: {html.escape(data['program'])}\n"
        f"Имя: {html.escape(data['name'])}\n"
        f"Контакт: {html.escape(contact)}\n"
        f"Telegram: @{message.from_user.username or '—'} (id {message.from_user.id})"
    )
    if ADMIN_ID:
        await bot.send_message(ADMIN_ID, lead)
    await message.answer("Спасибо! Заявка принята, скоро свяжусь с вами 💛", reply_markup=main_menu())


@router.message()
async def fallback(message: Message):
    await message.answer("Выберите пункт в меню 👇", reply_markup=main_menu())


async def main():
    logging.basicConfig(level=logging.INFO)
    init_db()
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
