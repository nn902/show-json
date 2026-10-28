import os
import json
import html
import logging
import sqlite3
import time
import re
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice, PreCheckoutQuery, BufferedInputFile
from aiogram.filters import Command
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest

# --- НАСТРОЙКИ ---
TOKEN = os.getenv("BOT_TOKEN", "ТВОЙ_ТОКЕН_СЮДА")
BOT_USERNAME = "nm_show_agent"

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
router = Router()

logging.basicConfig(level=logging.INFO)

# ==============================================================================
# 🗄 БАЗА ДАННЫХ (SQLite)
# ==============================================================================
DB_FILE = "users_vip.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, vip_until INTEGER DEFAULT 0)")
    conn.commit()
    conn.close()

def is_vip(user_id: int) -> bool:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT vip_until FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row and row[0] and row[0] > time.time()

def set_vip(user_id: int, days: int = 30):
    vip_until = int(time.time() + (days * 86400))
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO users (user_id, vip_until) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET vip_until = ?", (user_id, vip_until, vip_until))
    conn.commit()
    conn.close()

# ==============================================================================
# 🧠 ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==============================================================================

def extract_chat_target(text: str):
    if not text: return None
    if text.startswith("@"): return text.split()[0]
    match = re.search(r't\.me/([a-zA-Z0-9_]+)', text)
    if match: return "@" + match.group(1)
    match_invite = re.search(r't\.me/(\+[a-zA-Z0-9_-]+)', text)
    if match_invite: return match_invite.group(1)
    return None

# ==============================================================================
# 📥 ОСНОВНОЙ ОБРАБОТЧИК
# ==============================================================================
@router.message()
async def handle_any_message(message: Message):
    user_id = message.from_user.id
    is_user_vip = is_vip(user_id)

    # --- 1. ПАРСЕР СТИКЕРОВ ---
    if message.sticker:
        sticker = message.sticker
        sticker_info = (
            f"🎨 <b>Данные стикера:</b>\n"
            f"🆔 File ID:\n<code>{sticker.file_id}</code>\n"
            f"🔗 Unique ID:\n<code>{sticker.file_unique_id}</code>\n"
            f"🎭 Эмодзи: {sticker.emoji or 'Нет'}\n"
            f"📦 Набор: {sticker.set_name or 'Кастомный'}"
        )
        await message.reply(sticker_info, parse_mode="HTML")

    # --- 2. ПАРСЕР ПРЕМИУМ-ЭМОДЗИ ---
    if message.entities:
        for entity in message.entities:
            if entity.type == "custom_emoji":
                # Вырезаем сам смайлик из текста
                emoji_char = message.text[entity.offset:entity.offset + entity.length]
                # Формируем готовую строку для HTML
                ready_code = f'<tg-emoji emoji-id="{entity.custom_emoji_id}">{emoji_char}</tg-emoji>'
                await message.answer(
                    f"✨ <b>Готовый HTML-код для вставки:</b>\n<code>{html.escape(ready_code)}</code>", 
                    parse_mode="HTML"
                )

    # --- 3. ПАРСЕР ССЫЛОК НА ЧАТЫ/КАНАЛЫ ---
    if message.text:
        chat_target = extract_chat_target(message.text)
        if chat_target:
            try:
                chat = await bot.get_chat(chat_target)
                chat_info = (
                    f"📢 <b>Информация о чате/канале:</b>\n"
                    f"📝 Название: <b>{html.escape(chat.title or 'Без названия')}</b>\n"
                    f"📁 Тип: <b>{chat.type}</b>\n"
                    f"👤 Юзернейм:
