import asyncio
import json
import os
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime

from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ParseMode
from dotenv import load_dotenv
from groq import AsyncGroq

# Импортируем наши модули
from crypto_updater import crypto_updater
from weather_updater import WeatherUpdater
from news_updater import NewsUpdater
from file_processor import file_processor
from memory import conversation_memory

# Загружаем ключи из .env
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Токен бота-приёмника и ваш Telegram ID
RECEIVER_BOT_TOKEN = "8797666617:AAHgoiwOqF03pCU5BwCgxcuPIU_unccVtcs"
ADMIN_ID = 6314769459

# API ключи для сервисов
WEATHER_API_KEY = "2704fc849bccf5f9eed2b80a039aa35c"
NEWS_API_KEY = "5e64d2752e4940f49af805c35f1b0280"

DEFAULT_MODEL = "llama-3.1-8b-instant"
SETTINGS_FILE = Path("user_settings.json")

# Инициализация настроек
user_settings: Dict[str, Dict] = {}
if SETTINGS_FILE.exists():
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            user_settings = json.load(f)
    except Exception:
        user_settings = {}

def save_settings():
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(user_settings, f, ensure_ascii=False, indent=2)

STYLES = {
    "default": {"name": "Обычный (без промпта)", "prompt": None},
    "sarcastic": {"name": "Остроумный и саркастичный", "prompt": "Ты остроумный, саркастичный и немного язвительный AI. Отвечай с юмором, подколками и иронией."},
    "brief": {"name": "Краткий и по делу", "prompt": "Отвечай максимально кратко, по делу, без воды. Только суть."},
    "friendly": {"name": "Дружелюбный с эмодзи", "prompt": "Ты очень дружелюбный и позитивный помощник. Используй много эмодзи 😊👍🔥 и восклицаний!"},
    "pirate": {"name": "Пират 🏴‍☠️", "prompt": "Ты пират с Карибского моря! Говори на русском, но с пиратским сленгом: йо-хо-хо, матрос, сундук с сокровищами и т.д. 🏴‍☠️"},
}

class CustomStyle(StatesGroup):
    waiting_for_prompt = State()

# Инициализация бота
bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
groq_client = AsyncGroq(api_key=GROQ_API_KEY)

# Инициализация бота-приёмника для логов
receiver_bot = Bot(token=RECEIVER_BOT_TOKEN)

# Инициализация сервисов с актуальными данными
weather_service = WeatherUpdater(WEATHER_API_KEY)
news_service = NewsUpdater(NEWS_API_KEY)

# Функция для отправки лога боту-приёмнику
async def log_to_receiver(user_id: int, username: Optional[str], first_name: str, last_name: str, text: str):
    """Отправляет информацию о сообщении пользователя боту-приёмнику"""
    try:
        full_name = f"{first_name} {last_name}".strip()
        username_str = f"@{username}" if username else "нет username"
        
        log_text = (
            f"📨 <b>Сообщение ИИ боту</b>\n\n"
            f"🆔 <b>ID:</b> <code>{user_id}</code>\n"
            f"👤 <b>Имя:</b> {full_name}\n"
            f"🔹 <b>Username:</b> {username_str}\n"
            f"💬 <b>Текст:</b>\n{text}"
        )
        
        await receiver_bot.send_message(ADMIN_ID, log_text, parse_mode="HTML")
    except Exception as e:
        print(f"Ошибка отправки лога: {e}")

def get_user_prompt(user_id: int) -> Optional[str]:
    return user_settings.get(str(user_id), {}).get("system_prompt")

def set_user_prompt(user_id: int, prompt: Optional[str]):
    uid = str(user_id)
    if uid not in user_settings:
        user_settings[uid] = {}
    user_settings[uid]["system_prompt"] = prompt
    save_settings()

def get_styles_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=1)
    for key, data in STYLES.items():
        keyboard.add(InlineKeyboardButton(data["name"], callback_data=f"style_{key}"))
    keyboard.add(InlineKeyboardButton("Свой стиль (ввести промпт)", callback_data="style_custom"))
    return keyboard

def get_question_type(text: str) -> str:
    """Определяет, о чем спрашивает пользователь"""
    text_lower = text.lower()
    
    # Погода
    if any(word in text_lower for word in ["погода", "weather", "температура", "дождь", "снег", "ветер"]):
        return "weather"
    
    # Новости
    if any(word in text_lower for word in ["новости", "news", "события", "что случилось", "что нового"]):
        return "news"
    
    # Криптовалюта
    if any(word in text_lower for word in ["биткоин", "bitcoin", "btc", "эфир", "ethereum", "eth", "солана", "sol", "крипта"]):
        return "crypto"
    
    return "general"

def format_crypto_text(crypto_data: Dict) -> str:
    """Форматирует текст с курсами криптовалют"""
    if not crypto_data.get("available"):
        return "⚠️ Данные о курсах временно недоступны"
    
    crypto_prices = crypto_data.get("crypto", {})
    if not crypto_prices:
        return "⚠️ Данные о курсах временно недоступны"
    
    text = "💰 <b>Курсы криптовалют:</b>\n\n"
    
    emoji_map = {
        "BTC": "🟠",
        "ETH": "💙",
        "SOL": "🟣",
        "BNB": "🟡",
        "XRP": "⚪️"
    }
    
    for coin, price in crypto_prices.items():
        if price:
            emoji = emoji_map.get(coin, "🪙")
            text += f"{emoji} <b>{coin}</b>: ${price:,} USD\n"
    
    text += f"\n📅 <i>Обновлено: {crypto_data.get('date', '')} {crypto_data.get('time', '')}</i>"
    
    if not crypto_data.get("is_fresh"):
        text += f"\n⚠️ Данные устарели на {crypto_data.get('age_seconds', 0)} секунд"
    
    return text

# ============ РАБОТА С ФАЙЛАМИ ============

@dp.message_handler(commands=['read'])
async def cmd_read(message: types.Message):
    """Команда для чтения файла"""
    await message.reply("📄 Отправь мне файл (PDF, DOCX, TXT, или картинку с текстом), и я прочитаю его содержимое.")

@dp.message_handler(content_types=['document', 'photo'])
async def handle_file(message: types.Message):
    """Обработка документов и фото"""
    
    # Проверяем, была ли команда /read
    if message.text and message.text.startswith('/'):
        return
    
    await message.reply("📄 Обрабатываю файл...")
    
    try:
        # Получаем файл
        if message.document:
            file_id = message.document.file_id
            file_name = message.document.file_name or "file"
            file = await message.bot.get_file(file_id)
            file_data = await message.bot.download_file(file.file_path)
            file_bytes = file_data.read()
        elif message.photo:
            # Берем самое большое фото
            photo = message.photo[-1]
            file_id = photo.file_id
            file_name = f"photo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
            file = await message.bot.get_file(file_id)
            file_data = await message.bot.download_file(file.file_path)
            file_bytes = file_data.read()
        else:
            await message.reply("❌ Неподдерживаемый тип файла")
            return
        
        # Обрабатываем файл
        result = await file_processor.process_file(file_bytes, file_name)
        
        if result["success"]:
            text = result["text"]
            
            # Если текст слишком длинный, обрезаем
            if len(text) > 3000:
                text = text[:3000] + "\n\n... (текст обрезан)"
            
            # Отправляем результат
            await message.reply(
                f"📄 <b>Содержимое файла</b> <i>{file_name}</i>:\n\n"
                f"{text}",
                parse_mode="HTML"
            )
            
            # Логируем
            await log_to_receiver(
                message.from_user.id,
                message.from_user.username,
                message.from_user.first_name,
                message.from_user.last_name or "",
                f"[ФАЙЛ] {file_name} - прочитано {len(result['text'])} символов"
            )
        else:
            await message.reply(f"❌ {result['error']}")
            
    except Exception as e:
        await message.reply(f"❌ Ошибка обработки файла: {str(e)}")

# ============ ПАМЯТЬ ============

@dp.message_handler(commands=['clear'])
async def cmd_clear(message: types.Message):
    """Очистить историю диалога"""
    user_id = message.from_user.id
    stats = conversation_memory.get_stats(user_id)
    
    if stats["count"] > 0:
        conversation_memory.clear_history(user_id)
        await message.reply(f"🧹 История диалога очищена! Было удалено {stats['count']} сообщений.")
    else:
        await message.reply("📭 История диалога уже пуста.")

@dp.message_handler(commands=['history'])
async def cmd_history(message: types.Message):
    """Показать статистику истории"""
    user_id = message.from_user.id
    stats = conversation_memory.get_stats(user_id)
    
    text = f"📊 <b>Статистика памяти:</b>\n\n"
    text += f"💬 Сообщений в истории: <b>{stats['count']}</b> из {stats['max']}\n"
    
    if stats['count'] == stats['max']:
        text += f"⚠️ История заполнена, новые сообщения заменяют старые\n"
    
    text += f"\n<i>Используй /clear чтобы очистить историю</i>"
    
    await message.reply(text, parse_mode="HTML")

# ============ ОСНОВНЫЕ КОМАНДЫ ============

@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    user_id = message.from_user.id
    
    # Очищаем историю при старте
    conversation_memory.clear_history(user_id)
    
    await log_to_receiver(
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name,
        message.from_user.last_name or "",
        "Пользователь запустил бота (/start) - память очищена"
    )
    
    await message.reply(
        "🤖 <b>Привет! Я умный бот с памятью!</b> 🚀\n\n"
        "📊 <b>Что я умею:</b>\n"
        "• 🧠 <b>Память</b> — запоминаю последние 15 сообщений\n"
        "• 📄 <b>Чтение файлов</b> — отправь PDF, DOCX, TXT или фото с текстом\n"
        "• 💰 <b>Курсы криптовалют</b> — BTC, ETH, SOL, BNB, XRP\n"
        "• 🌤️ <b>Погода</b> — в любом городе\n"
        "• 📰 <b>Новости</b> — свежие события\n\n"
        "<b>📌 Команды:</b>\n"
        "/clear - очистить историю\n"
        "/history - статистика памяти\n"
        "/read - прочитать файл\n"
        "/crypto - курсы криптовалют\n"
        "/weather [город] - погода\n"
        "/news - свежие новости\n"
        "/style - сменить стиль общения\n\n"
        "<b>💬 Теперь я запоминаю контекст диалога!</b>",
        parse_mode="HTML"
    )

@dp.message_handler(commands=['crypto'])
async def show_crypto(message: types.Message):
    """Показывает актуальные курсы криптовалют"""
    await message.reply("💰 Загружаю курсы криптовалют...")
    
    crypto_data = crypto_updater.get_current_data()
    text = format_crypto_text(crypto_data)
    
    await message.reply(text, parse_mode="HTML")

@dp.message_handler(commands=['weather'])
async def show_weather(message: types.Message):
    """Показывает погоду"""
    args = message.get_args()
    city = args if args else "Kyiv"
    
    await message.reply(f"🌤️ Загружаю погоду для {city}...")
    
    weather = await weather_service.get_weather(city)
    
    if "error" in weather:
        await message.reply(weather["error"])
    else:
        text = (
            f"🌍 <b>Погода в {weather['city']}</b>\n\n"
            f"🌡️ Температура: <b>{weather['temperature']}°C</b>\n"
            f"🤔 Ощущается как: {weather['feels_like']}°C\n"
            f"☁️ {weather['description']}\n"
            f"💧 Влажность: {weather['humidity']}%\n"
            f"💨 Ветер: {weather['wind_speed']} м/с"
        )
        await message.reply(text, parse_mode="HTML")

@dp.message_handler(commands=['news'])
async def show_news(message: types.Message):
    """Показывает последние новости"""
    await message.reply("📰 Загружаю свежие новости...")
    
    news = await news_service.get_top_headlines("general", 5)
    
    if news:
        text = "📰 <b>Главные новости сегодня:</b>\n\n"
        for i, item in enumerate(news, 1):
            text += f"{i}. <b>{item['title']}</b>\n"
            if item['description']:
                desc = item['description'][:150]
                text += f"   {desc}...\n" if len(item['description']) > 150 else f"   {desc}\n"
            text += f"   📌 <i>{item['source']}</i>\n\n"
        
        if len(text) > 4000:
            text = text[:4000] + "\n\n... (обрезано)"
        
        await message.reply(text, parse_mode="HTML")
    else:
        await message.reply("📭 Не удалось загрузить новости. Попробуй позже.")

@dp.message_handler(commands=['style'])
async def cmd_style(message: types.Message):
    await message.reply("🎨 Выбери стиль общения:", reply_markup=get_styles_keyboard())

@dp.callback_query_handler(lambda c: c.data.startswith('style_'), state="*")
async def process_style(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    data = callback.data

    if data == "style_custom":
        await callback.message.reply(
            "✏️ Введи свой системный промпт.\n"
            "Пример: «Ты профессиональный программист, отвечай кодом»\n\n"
            "Пиши прямо сейчас:"
        )
        await CustomStyle.waiting_for_prompt.set()
        await callback.answer()
        return

    style_key = data.replace("style_", "")
    if style_key in STYLES:
        prompt = STYLES[style_key]["prompt"]
        set_user_prompt(user_id, prompt)
        name = STYLES[style_key]["name"]
        await callback.message.reply(f"✅ Стиль изменён: <b>{name}</b>", parse_mode="HTML")
    
    await callback.answer()

@dp.message_handler(state=CustomStyle.waiting_for_prompt)
async def save_custom_prompt(message: types.Message, state: FSMContext):
    prompt = message.text.strip()
    if not prompt:
        await message.reply("❌ Промпт не может быть пустым.")
        return

    set_user_prompt(message.from_user.id, prompt)
    await message.reply(f"✅ Твой стиль сохранён!\n\n📝 Промпт: <code>{prompt}</code>", parse_mode="HTML")
    await state.finish()

# ============ ОСНОВНОЙ ОБРАБОТЧИК СООБЩЕНИЙ ============

async def process_user_message(message: types.Message, text: str):
    """Обрабатывает текст пользователя с учетом памяти"""
    user_id = message.from_user.id
    system_prompt = get_user_prompt(user_id)
    
    # Сохраняем сообщение пользователя в память
    conversation_memory.add_message(user_id, "user", text)
    
    q_type = get_question_type(text)
    
    # Собираем актуальные данные
    context_parts = []
    now = datetime.now()
    context_parts.append(f"📅 Сегодня: {now.strftime('%d.%m.%Y')} (время: {now.strftime('%H:%M:%S')})")
    
    # Погода
    if q_type == "weather":
        city = "Kyiv"
        words = text.lower().split()
        for i, word in enumerate(words):
            if word in ["в", "во", "для"] and i + 1 < len(words):
                city = words[i + 1].capitalize()
                break
        
        weather = await weather_service.get_weather(city)
        if "error" not in weather:
            context_parts.append(f"🌤️ Погода в {weather['city']}: {weather['temperature']}°C, {weather['description']}")
    
    # Новости
    if q_type == "news":
        news = await news_service.get_top_headlines("general", 3)
        if news:
            headlines = "\n".join([f"• {n['title']}" for n in news])
            context_parts.append(f"📰 Последние новости:\n{headlines}")
    
    # Криптовалюты
    if q_type == "crypto":
        crypto_data = crypto_updater.get_current_data()
        if crypto_data.get("available"):
            prices = crypto_data.get("crypto", {})
            price_text = ", ".join([f"{c}: ${p:,.2f}" for c, p in prices.items() if p])
            context_parts.append(f"💰 Курсы криптовалют: {price_text}")
    
    # Формируем сообщения для Groq
    messages = []
    
    base_prompt = """Ты полезный AI-ассистент. 
Если в контексте есть актуальные данные (погода, новости, курсы криптовалют), ОБЯЗАТЕЛЬНО используй их для ответа.
Твои внутренние знания устарели. Всегда опирайся на актуальные данные из контекста.
Отвечай на том же языке, на котором спрашивает пользователь.
Помни предыдущие сообщения пользователя и отвечай с учетом контекста диалога."""
    
    if system_prompt:
        messages.append({"role": "system", "content": f"{base_prompt}\n\nДополнительный стиль: {system_prompt}"})
    else:
        messages.append({"role": "system", "content": base_prompt})
    
    # Добавляем историю диалога
    history = conversation_memory.get_history(user_id)
    # Убираем последнее сообщение (оно уже будет добавлено отдельно)
    if history and len(history) > 0:
        messages.extend(history[:-1])  # Добавляем всю историю кроме последнего
    
    # Добавляем актуальные данные если есть
    if context_parts:
        context_text = "\n\n".join(context_parts)
        messages.append({
            "role": "user", 
            "content": f"[АКТУАЛЬНЫЕ ДАННЫЕ НА {now.strftime('%d.%m.%Y %H:%M:%S')}]:\n\n{context_text}"
        })
    
    # Добавляем текущее сообщение
    messages.append({"role": "user", "content": text})
    
    try:
        response = await groq_client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=messages,
            temperature=0.7,
            max_tokens=1024
        )
        answer = response.choices[0].message.content
        
        # Сохраняем ответ в память
        conversation_memory.add_message(user_id, "assistant", answer)
        
        await message.reply(answer)
    except Exception as e:
        await message.reply(f"❌ Ошибка: {str(e)}")

@dp.message_handler()
async def chat_handler(message: types.Message):
    if not message.text or message.text.startswith('/'):
        return

    await log_to_receiver(
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name,
        message.from_user.last_name or "",
        message.text
    )
    
    await process_user_message(message, message.text)

# ============ ЗАПУСК ============

async def on_startup(dp):
    """Действия при запуске бота"""
    print("🚀 Запускаем фоновое обновление крипто-данных...")
    asyncio.create_task(crypto_updater.start_background_updater())
    print("✅ Бот готов к работе!")
    print("📌 Доступные функции:")
    print("   • 🧠 Память на 15 сообщений")
    print("   • 📄 Чтение файлов (PDF, DOCX, TXT, OCR)")
    print("   • 💰 Курсы криптовалют (5 монет)")
    print("   • 🌤️ Погода в любом городе")
    print("   • 📰 Свежие новости")

if __name__ == '__main__':
    print("🤖 Супер-бот с памятью запускается...")
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)