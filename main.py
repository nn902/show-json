import os
import json
import html
import logging
import sqlite3
import time
import re
import asyncio
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
    return bool(row and row[0] and row[0] > time.time())

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
    if message.entities and message.text:
        for entity in message.entities:
            if entity.type == "custom_emoji":
                emoji_char = message.text[entity.offset:entity.offset + entity.length]
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
                    f"👤 Юзернейм: @{chat.username if chat.username else 'Скрыт'}\n"
                    f"🆔 ID чата:\n<code>{chat.id}</code>"
                )
                await message.answer(chat_info, parse_mode="HTML")
            except TelegramBadRequest:
                await message.answer("⚠️ Не удалось получить данные. Бот не добавлен в этот чат или ссылка приватная.", parse_mode="HTML")
            except Exception as e:
                logging.error(f"Ошибка парсинга чата: {e}")

    # --- 4. ОСНОВНОЙ JSON И ID ---
    try:
        msg_dict = message.model_dump(exclude_none=True, mode='json')
        json_str = json.dumps(msg_dict, indent=2, ensure_ascii=False)
        chat_id = message.chat.id

        if not is_user_vip:
            ad_comment = f'\n\n// 🤖 Сгенерировано в @{BOT_USERNAME}\n// 💎 Убрать рекламу на 30 дней (1 ⭐️) -> нажми кнопку ниже'
            json_str += ad_comment

        # Защита от слишком длинных сообщений (Телеграм не пропускает текст > 4096 символов)
        if len(json_str) > 3500:
            file_data = json_str.encode('utf-8')
            input_file = BufferedInputFile(file_data, filename=f"message_{message.message_id}.json")
            await message.reply_document(input_file, caption="📁 JSON слишком большой, отправляю файлом.")
        else:
            safe_json_str = html.escape(json_str)
            json_block = f"<pre><code class=\"language-json\">{safe_json_str}</code></pre>"
            await message.reply(json_block, parse_mode="HTML")

        # Вывод кликабельных ID
        ids_block = (
            f"👤 <b>ID отправителя:</b> <code>{user_id}</code>\n"
            f"💬 <b>ID чата:</b> <code>{chat_id}</code>\n"
            f"🆔 <b>Message ID:</b> <code>{message.message_id}</code>"
        )

        kb = None
        if not is_user_vip:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💎 Убрать рекламу на 30 дней (1 ⭐️)", callback_data="buy_vip")]
            ])
            ids_block += f"\n\n📢 <i>Реклама: бот создан при поддержке @{BOT_USERNAME}</i>"

        await message.answer(ids_block, reply_markup=kb, parse_mode="HTML")

    except Exception as e:
        logging.error(f"Ошибка обработки: {e}")
        await message.reply("❌ Не удалось обработать сообщение.")

# ==============================================================================
# 💎 ОПЛАТА ЗВЕЗДАМИ (1 Star = 30 дней без рекламы)
# ==============================================================================
@router.callback_query(F.data == "buy_vip")
async def process_buy_vip(callback: CallbackQuery):
    await callback.answer()
    
    if is_vip(callback.from_user.id):
        return await callback.answer("У вас уже есть VIP статус!", show_alert=True)

    await bot.send_invoice(
        chat_id=callback.message.chat.id,
        title="VIP статус на 30 дней",
        description="Убирает рекламный комментарий из JSON-кода на 30 дней.",
        payload="vip_30_days",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label="VIP на 30 дней", amount=1)]
    )

@router.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: PreCheckoutQuery):
    await pre_checkout_query.answer(ok=True)

@router.message(F.successful_payment)
async def process_successful_payment(message: Message):
    user_id = message.from_user.id
    set_vip(user_id, days=30)
    
    await message.answer(
        "🎉 <b>Оплата прошла успешно!</b>\n\n"
        "Реклама убрана на <b>30 дней</b>. Спасибо за поддержку проекта! 💎",
        parse_mode="HTML"
    )

# ==============================================================================
# 🚀 ЗАПУСК
# ==============================================================================
async def main():
    init_db()
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    print(f"🚀 @{BOT_USERNAME} запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
