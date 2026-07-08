import os
import logging
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# ===== НАСТРОЙКИ =====
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "123456789"))
PORT = int(os.environ.get("PORT", 10000))

# ===== ЛОГИРОВАНИЕ =====
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ===== HTTP СЕРВЕР ДЛЯ KEEP-ALIVE =====
class KeepAliveHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'Bot is alive!')
    
    def log_message(self, format, *args):
        pass  # Отключаем логи HTTP

def run_keep_alive():
    """Запускает HTTP сервер для пингов"""
    server = HTTPServer(('0.0.0.0', PORT), KeepAliveHandler)
    logger.info(f"🌐 Keep-alive server running on port {PORT}")
    server.serve_forever()

# ===== ФУНКЦИЯ ДЛЯ САМОПИНГА =====
def self_ping():
    """Пингует себя каждые 5 минут"""
    import requests
    url = f"https://{os.environ.get('RENDER_EXTERNAL_HOSTNAME', 'localhost')}"
    while True:
        try:
            response = requests.get(url, timeout=5)
            logger.info(f"📡 Self-ping: {response.status_code}")
        except Exception as e:
            logger.error(f"❌ Self-ping failed: {e}")
        time.sleep(300)  # 5 минут

# ===== ОБРАБОТЧИКИ БОТА =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Это бот для анонимных сообщений Матвею.\n\n"
        "📩 Напиши любое сообщение, и оно уйдет ему."
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = update.message
    
    if user.id == ADMIN_ID:
        if context.user_data.get('reply_to_user'):
            await handle_admin_reply(update, context)
        else:
            await message.reply_text("❌ Нажми 'Ответить' под сообщением.")
        return
    
    user_info = f"🆔 ID: {user.id}"
    if user.username:
        user_info += f"\n👤 @{user.username}"
    if user.first_name:
        user_info += f"\n📛 {user.first_name}"
    if user.last_name:
        user_info += f" {user.last_name}"
    
    keyboard = [[InlineKeyboardButton("✍️ Ответить", callback_data=f"reply_{user.id}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=f"📨 Новое сообщение\n\n{user_info}\n",
        reply_markup=reply_markup
    )
    
    await message.copy(chat_id=ADMIN_ID)
    await message.reply_text("✅ Отправлено!")

async def handle_admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    
    if not message.text or not message.text.strip():
        await message.reply_text("❌ Нельзя отправить пустое сообщение.")
        return
    
    if not context.user_data.get('reply_to_user'):
        await message.reply_text("❌ Нажми 'Ответить' под сообщением.")
        return
    
    user_id = context.user_data['reply_to_user']
    
    try:
        await message.copy(chat_id=user_id)
        await message.reply_text(f"✅ Отправлено пользователю {user_id}")
        context.user_data['reply_to_user'] = None
    except Exception as e:
        await message.reply_text(f"❌ Ошибка: {e}")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id != ADMIN_ID:
        await query.edit_message_text("⛔ Нет доступа.")
        return
    
    user_id = int(query.data.split('_')[1])
    if user_id == ADMIN_ID:
        await query.edit_message_text("❌ Нельзя ответить самому себе.")
        return
    
    context.user_data['reply_to_user'] = user_id
    
    await query.edit_message_text(
        f"✍️ Напиши ответ для {user_id}.\n"
        f"/cancel - отмена"
    )

async def reply_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Нет доступа.")
        return
    
    if not context.args:
        await update.message.reply_text("❗ Использование: /reply ID текст")
        return
    
    try:
        user_id = int(context.args[0])
        if len(context.args) < 2:
            await update.message.reply_text("❗ Использование: /reply ID текст")
            return
        
        reply_text = ' '.join(context.args[1:])
        
        await context.bot.send_message(chat_id=user_id, text=reply_text)
        await update.message.reply_text(f"✅ Отправлено {user_id}")
    except ValueError:
        await update.message.reply_text("❌ ID должен быть числом.")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Нет доступа.")
        return
    
    context.user_data['reply_to_user'] = None
    await update.message.reply_text("✅ Отменено.")

# ===== ЗАПУСК =====
def main():
    # 1. Запускаем HTTP сервер
    thread_http = threading.Thread(target=run_keep_alive, daemon=True)
    thread_http.start()
    
    # 2. Запускаем самопинг (каждые 5 минут)
    thread_ping = threading.Thread(target=self_ping, daemon=True)
    thread_ping.start()
    
    # 3. Запускаем бота
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reply", reply_command))
    app.add_handler(CommandHandler("cancel", cancel_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))
    
    logger.info("🤖 Бот запущен и будет работать 24/7!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()