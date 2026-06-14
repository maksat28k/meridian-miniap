import asyncio, httpx, json, os
from telegram import Update, WebAppInfo, KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

BOT_TOKEN  = "8848225555:AAGZPzD0dvdCYTfCkZY8OCXZzQvBlFBVHdo"
WEBAPP_URL = "https://maksat28k.github.io/meridian-miniap"
API_URL    = os.environ.get("API_URL", "http://localhost:8000")

def main_keyboard():
    return ReplyKeyboardMarkup(
        [[KeyboardButton("🩺 Открыть Meridian", web_app=WebAppInfo(url=WEBAPP_URL))]],
        resize_keyboard=True
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name
    await update.message.reply_text(
        f"Привет, {name}! 👋\n\n"
        "Meridian — персональный разбор твоих анализов крови на основе доказательной медицины.\n\n"
        "📎 *Отправь PDF своих анализов* из Инвитро, Гемотест или Хеликс — "
        "я извлеку все показатели и дам системный разбор: что происходит в теле, "
        "какие риски есть прямо сейчас и что делать конкретно.\n\n"
        "Или открой приложение:",
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc or doc.mime_type != "application/pdf":
        await update.message.reply_text("Пожалуйста, отправь PDF файл анализов.")
        return

    user_id = str(update.effective_user.id)
    name    = update.effective_user.first_name or "Пользователь"

    msg = await update.message.reply_text("⏳ Загружаю и анализирую PDF...")

    try:
        # Скачиваем PDF
        file = await doc.get_file()
        pdf_bytes = await file.download_as_bytearray()

        # Получаем профиль из БД или используем дефолт
        async with httpx.AsyncClient(timeout=60) as client:
            try:
                user_resp = await client.get(f"{API_URL}/api/user/{user_id}")
                user_data = user_resp.json() if user_resp.status_code == 200 else {}
            except:
                user_data = {}

            gender = user_data.get('gender', 'm')
            age    = user_data.get('age', 30)

            # Отправляем PDF на анализ
            resp = await client.post(
                f"{API_URL}/api/analyze",
                data={
                    'telegram_id': user_id,
                    'name': name,
                    'gender': gender,
                    'age': str(age),
                },
                files={'file': ('analysis.pdf', bytes(pdf_bytes), 'application/pdf')},
                timeout=120
            )
            result = resp.json()

        if not result.get('success'):
            await msg.edit_text(
                "❌ " + result.get('message', 'Не удалось прочитать PDF.\n\nУбедись что это PDF из Инвитро, Гемотест или Хеликс.')
            )
            return

        ai = result['result']
        found = result['found']
        attention = ai.get('attention_count', 0)
        ok_count  = ai.get('ok_count', 0)
        summary   = ai.get('summary', '')

        # Формируем ответ
        status_emoji = "⚠️" if attention > 0 else "✅"
        text = (
            f"{status_emoji} *Анализ готов*\n\n"
            f"Найдено показателей: {found}\n"
            f"✅ В норме: {ok_count}\n"
            f"⚠️ Требуют внимания: {attention}\n\n"
            f"_{summary}_\n\n"
            f"Открой приложение для полного разбора 👇"
        )

        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔬 Открыть разбор", web_app=WebAppInfo(url=WEBAPP_URL))
        ]])

        await msg.edit_text(text, parse_mode="Markdown", reply_markup=kb)

    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}\n\nПопробуй ещё раз.")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Отправь PDF файл анализов — я его разберу. "
        "Или открой приложение кнопкой ниже.",
        reply_markup=main_keyboard()
    )

if __name__ == "__main__":
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    print("Meridian bot started...")
    app.run_polling(drop_pending_updates=True)
