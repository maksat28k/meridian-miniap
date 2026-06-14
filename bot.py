from telegram import Update, WebAppInfo, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes

BOT_TOKEN = "8848225555:AAGZPzD0dvdCYTfCkZY8OCXZzQvBlFBVHdo"
WEBAPP_URL = "https://maksat28k.github.io/meridian-miniap"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name
    kb = [[KeyboardButton("🩺 Открыть Meridian", web_app=WebAppInfo(url=WEBAPP_URL))]]
    await update.message.reply_text(
        f"Привет, {name}! 👋\n\n"
        "Meridian — твой персональный разбор анализов крови.\n\n"
        "Загрузи показатели и узнай:\n"
        "• Что происходит в твоём теле прямо сейчас\n"
        "• Какие риски есть до того как стало болезнью\n"
        "• Что делать конкретно для тебя\n\n"
        "Нажми кнопку ниже ↓",
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
    )

if __name__ == "__main__":
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    print("Meridian bot running...")
    app.run_polling(drop_pending_updates=True)
