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
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest

TOKEN = os.getenv("BOT_TOKEN", "ТВОЙ_ТОКЕН_СЮДА")
BOT_USERNAME = "nm_show_agent"
ADMIN_ID = 7727345054
DEPUTY_USERNAME = "nmproda"

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
router = Router()

logging.basicConfig(level=logging.INFO)

E_DIAMOND = '<tg-emoji emoji-id="5427168083074628963">💎</tg-emoji>'
E_ROCKET  = '<tg-emoji emoji-id="5780773956030043338">🚀</tg-emoji>'
E_CHECK   = '<tg-emoji emoji-id="5206607081334906820">✔️</tg-emoji>'
E_CROSS   = '<tg-emoji emoji-id="5274099962655816924">❗️</tg-emoji>'
E_STAR    = '<tg-emoji emoji-id="5438496463044752972">⭐️</tg-emoji>'
E_FIRE    = '<tg-emoji emoji-id="5801004944211317728">🔥</tg-emoji>'
E_USER    = '<tg-emoji emoji-id="5841276284155467413">👤</tg-emoji>'
E_MONEY   = '<tg-emoji emoji-id="5373001317042101552">💰</tg-emoji>'
E_GEAR    = '<tg-emoji emoji-id="5373012449597335010">⚙️</tg-emoji>'
E_MEMO    = '<tg-emoji emoji-id="5431499171045581032">📝</tg-emoji>'
E_CHAT    = '<tg-emoji emoji-id="5443038326535759644">💬</tg-emoji>'

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

def extract_chat_target(text: str):
    text = text.strip()
    if re.fullmatch(r'@[a-zA-Z0-9_]{4,32}', text):
        return text
    match = re.fullmatch(r'(?:https?://)?t\.me/([a-zA-Z0-9_]{4,32})(?:/\d+)?', text)
    if match:
        return "@" + match.group(1)
    if re.fullmatch(r'(?:https?://)?t\.me/(?:\+|joinchat/)([a-zA-Z0-9_-]+)', text) or re.fullmatch(r'(?:https?://)?t\.me/c/\d+.*', text):
        return "PRIVATE_LINK"
    return None

class OrderState(StatesGroup):
    survey = State()

QUESTIONS = [
    f"1️⃣ {E_ROCKET} <b>Какова основная цель вашего бота?</b>\n\nОпишите в двух словах, какую проблему он должен решить. <i>(Например: автоматизация продаж, выдача файлов после подписки, модерация чата или развлекательная игра)</i>.",
    f"2️⃣ {E_USER} <b>Кто будет пользоваться ботом?</b>\n\nОпишите вашу аудиторию. <i>(Клиенты магазина, участники закрытого клуба, подписчики канала или случайные пользователи?)</i>",
    f"3️⃣ {E_GEAR} <b>Какие главные функции нужны?</b>\n\nНапишите список того, что должен уметь бот. <i>(Например: прием оплаты, рассылка, выдача подарков, система рефералов, админ-панель)</i>.",
    f"4️⃣ {E_DIAMOND} <b>Нужна ли админ-панель?</b>\n\nЧто именно должен контролировать администратор внутри бота? <i>(Например: смотреть статистику, выдавать баланс, блокировать юзеров)</i>.",
    f"5️⃣ {E_FIRE} <b>Нужна ли интеграция с другими системами?</b>\n\n(Сайт, сторонние API, базы данных, Telegram Stars). Выберите вариант на кнопках ниже.\n\n<i>⚠️ Внимание: Интеграция со сторонними сервисами добавляет +5% к итоговой стоимости.</i>",
    f"6️⃣ {E_MEMO} <b>Где нужно хранить данные?</b>\n\nЧто мы будем сохранять? <i>(Например: баланс пользователей, их историю действий или просто файлы. Вам нужна простая база данных или сложная система?)</i>",
    f"7️⃣ {E_MONEY} <b>Планируется ли монетизация?</b>\n\nБудут ли в боте платные подписки, донаты на Stars или внутренняя валюта, которую можно купить?",
    f"8️⃣ {E_CHAT} <b>Как должен выглядеть интерфейс?</b>\n\nОбычные кнопки под чатом, инлайн-кнопки в сообщениях или красивое Mini App (веб-приложение внутри Телеграма)?",
    f"9️⃣ {E_STAR} <b>Какие сроки и бюджет?</b>\n\nКогда бот должен быть готов и на какую сумму вы рассчитываете? <i>(Это поможет нам понять масштаб задачи)</i>."
]

@router.message(Command("order"))
async def cmd_order_start(message: Message, state: FSMContext):
    await state.clear()
    text = (
        f"{E_ROCKET} <b>Создание индивидуального Telegram-бота</b> {E_ROCKET}\n"
        "· · · · · · · · · · · · · · · · · · · · ·\n"
        "Готовы автоматизировать свой бизнес или создать крутой проект? "
        "Наш бот задаст вам <b>9 коротких вопросов</b>, чтобы мы могли оценить вашу задачу.\n\n"
        f"{E_CHECK} Это займет не больше 2 минут.\n"
        f"{E_FIRE} После прохождения опроса вы получите контакты менеджера.\n\n"
        "👇 Нажмите кнопку ниже, чтобы начать:"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="▶️ Начать опрос", callback_data="start_order_survey", style="success")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_order", style="danger")]
    ])
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data == "start_order_survey")
async def start_survey(callback: CallbackQuery, state: FSMContext):
    await state.set_state(OrderState.survey)
    await state.update_data(step=1, answers={})
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.message.answer(QUESTIONS[0], parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "cancel_order")
async def cancel_order_cb(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(f"{E_CROSS} Заказ отменен. Возвращайтесь, когда будете готовы!", parse_mode="HTML")
    await callback.answer()

@router.message(OrderState.survey)
async def process_survey_answers(message: Message, state: FSMContext):
    data = await state.get_data()
    step = data.get("step", 1)
    answers = data.get("answers", {})

    if step == 5:
        await message.answer("Пожалуйста, выберите вариант на кнопках выше 👆")
        return

    answers[f"q{step}"] = html.escape(message.text or "Медиафайл/Не текст")
    step += 1

    if step <= len(QUESTIONS):
        await state.update_data(step=step, answers=answers)
        if step == 5:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Да (+5%)", callback_data="int_yes", style="success"),
                 InlineKeyboardButton(text="❌ Нет", callback_data="int_no", style="danger")]
            ])
            await message.answer(QUESTIONS[4], reply_markup=kb, parse_mode="HTML")
        else:
            await message.answer(QUESTIONS[step - 1], parse_mode="HTML")
    else:
        await finish_order(message, state, answers, message.from_user)

@router.callback_query(OrderState.survey, F.data.startswith("int_"))
async def process_integration_buttons(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    answers = data.get("answers", {})
    
    if callback.data == "int_yes":
        answers["integration"] = f"{E_CROSS} <b>Да (+5% к стоимости)</b>"
        ans_text = "✅ Да (+5% к стоимости)"
    else:
        answers["integration"] = f"{E_CHECK} <b>Нет</b>"
        ans_text = "❌ Нет"

    step = 6
    await state.update_data(step=step, answers=answers)
    await callback.message.edit_text(f"5️⃣ {E_FIRE} <b>Интеграция с другими системами?</b>\n\nВаш ответ: {ans_text}", parse_mode="HTML")
    await callback.message.answer(QUESTIONS[5], parse_mode="HTML")
    await callback.answer()

async def finish_order(message_obj: Message, state: FSMContext, answers: dict, user):
    await state.clear()
    username = f"@{user.username}" if user.username else "Скрыт"
    
    admin_tz = (
        f"{E_FIRE} <b>НОВАЯ ЗАЯВКА НА РАЗРАБОТКУ БОТА!</b> {E_FIRE}\n"
        f"· · · · · · · · · · · · · · · · · · · · ·\n"
        f"{E_USER} <b>Клиент:</b> {html.escape(user.first_name)} ({username})\n"
        f"🆔 <b>ID клиента:</b> <code>{user.id}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>1. Цель:</b> {answers.get('q1')}\n\n"
        f"<b>2. Аудитория:</b> {answers.get('q2')}\n\n"
        f"<b>3. Функционал:</b> {answers.get('q3')}\n\n"
        f"<b>4. Админка:</b> {answers.get('q4')}\n\n"
        f"<b>5. Интеграция:</b> {answers.get('integration')}\n\n"
        f"<b>6. База данных:</b> {answers.get('q6')}\n\n"
        f"<b>7. Монетизация:</b> {answers.get('q7')}\n\n"
        f"<b>8. Интерфейс:</b> {answers.get('q8')}\n\n"
        f"<b>9. Сроки и бюджет:</b> {answers.get('q9')}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>Свяжитесь с клиентом для обсуждения.</i>"
    )
    try:
        await message_obj.bot.send_message(ADMIN_ID, admin_tz, parse_mode="HTML")
    except Exception as e:
        logging.error(f"Ошибка отправки ТЗ: {e}")

    client_text = (
        f"{E_CHECK} <b>Ваша заявка успешно сформирована!</b>\n\n"
        f"Мы изучим ваши ответы и свяжемся с вами в ближайшее время.\n\n"
        f"{E_CHAT} Чтобы ускорить процесс или задать вопросы, напишите нашему менеджеру:"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Написать менеджеру", url=f"https://t.me/{DEPUTY_USERNAME}", style="success")]
    ])
    await message_obj.answer(client_text, reply_markup=kb, parse_mode="HTML")

@router.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: PreCheckoutQuery):
    await pre_checkout_query.answer(ok=True)

@router.message(F.successful_payment)
async def process_successful_payment(message: Message):
    set_vip(message.from_user.id, days=30)
    await message.answer(
        f"{E_CHECK} <b>Оплата прошла успешно!</b>\n\n"
        f"Реклама убрана на <b>30 дней</b>. Спасибо за поддержку проекта! {E_DIAMOND}",
        parse_mode="HTML"
    )

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

@router.message()
async def handle_any_message(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is not None:
        return
    
    if message.successful_payment:
        return

    user_id = message.from_user.id
    is_user_vip = is_vip(user_id)

    if message.text:
        chat_target = extract_chat_target(message.text)
        if chat_target == "PRIVATE_LINK":
            await message.answer("⚠️ Вы отправили приватную ссылку. Я не могу получить ID закрытого чата, если меня в него не добавили. Отправьте публичную ссылку (t.me/username).", parse_mode="HTML")
            return
        elif chat_target:
            try:
                chat = await bot.get_chat(chat_target)
                title = html.escape(chat.title) if chat.title else "Без названия"
                chat_info = (
                    f"📢 <b>Информация о чате/канале:</b>\n"
                    f"📝 Название: <b>{title}</b>\n"
                    f"📁 Тип: <b>{chat.type}</b>\n"
                    f"👤 Юзернейм: @{chat.username if chat.username else 'Скрыт'}\n"
                    f"🆔 ID чата:\n<code>{chat.id}</code>"
                )
                await message.answer(chat_info, parse_mode="HTML")
                return
            except TelegramBadRequest:
                await message.answer("⚠️ Не удалось получить данные. Убедитесь, что бот добавлен в чат или ссылка верна.", parse_mode="HTML")
                return
            except Exception as e:
                logging.error(f"Ошибка парсинга чата: {e}")
                await message.answer("⚠️ Произошла ошибка при получении данных.", parse_mode="HTML")
                return

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

    if message.entities and message.text:
        for entity in message.entities:
            if entity.type == "custom_emoji":
                emoji_char = message.text[entity.offset:entity.offset + entity.length]
                ready_code = f'<tg-emoji emoji-id="{entity.custom_emoji_id}">{emoji_char}</tg-emoji>'
                await message.answer(
                    f"✨ <b>Готовый HTML-код для вставки:</b>\n<code>{html.escape(ready_code)}</code>", 
                    parse_mode="HTML"
                )

    try:
        msg_dict = message.model_dump(exclude_none=True, mode='json')
        json_str = json.dumps(msg_dict, indent=2, ensure_ascii=False)
        chat_id = message.chat.id

        if not is_user_vip:
            ad_comment = f'\n\n// 🤖 Сгенерировано в @{BOT_USERNAME}\n// 💎 Убрать рекламу на 30 дней (1 ⭐️) -> нажми кнопку ниже'
            json_str += ad_comment

        if len(json_str) > 3500:
            file_data = json_str.encode('utf-8')
            input_file = BufferedInputFile(file_data, filename=f"message_{message.message_id}.json")
            await message.reply_document(input_file, caption="📁 JSON слишком большой, отправляю файлом.")
        else:
            safe_json_str = html.escape(json_str)
            json_block = f"<pre><code class=\"language-json\">{safe_json_str}</code></pre>"
            await message.reply(json_block, parse_mode="HTML")

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

async def main():
    init_db()
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    print(f"🚀 @{BOT_USERNAME} запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
