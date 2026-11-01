import logging
import signal
import sys
import threading
import uvicorn

from config import BOT_TOKEN, WEBAPP_HOST, WEBAPP_PORT, WEBAPP_URL
import database as db
from scheduler import start_scheduler_thread
from bot import bot
from api import app

logger = logging.getLogger("proftools_runner")

def handle_shutdown(signum, frame):
    logger.info(f"Получен сигнал завершения ({signum}). Корректная остановка сервисов...")
    try:
        bot.stop_polling()
    except Exception:
        pass
    sys.exit(0)

signal.signal(signal.SIGINT, handle_shutdown)
signal.signal(signal.SIGTERM, handle_shutdown)

def run_bot_polling():
    """Запуск long polling Telegram бота в отдельном потоке"""
    logger.info("Запуск Telegram Bot Polling потока...")
    try:
        bot.infinity_polling(timeout=20, long_polling_timeout=20)
    except Exception as e:
        logger.error(f"Ошибка в цикле polling бота: {e}", exc_info=True)

if __name__ == "__main__":
    logger.info("========================================================")
    logger.info("    Запуск Telegram Bot + Telegram Mini App (TMA)      ")
    logger.info("========================================================")
    
    # 1. Инициализация базы данных SQLite
    db.init_db()

    # 2. Настройка команд бота и кнопки WebApp
    try:
        from telebot import types
        bot.delete_my_commands(scope=types.BotCommandScopeAllGroupChats())
        bot.set_my_commands(
            commands=[
                types.BotCommand("start", "Главное меню"),
                types.BotCommand("app", "Открыть Mini App"),
                types.BotCommand("my_tasks", "Мои задачи"),
                types.BotCommand("tasks", "Список задач (Председатель)"),
                types.BotCommand("new_task", "Новая задача (Председатель)"),
                types.BotCommand("topics", "Тема в группе (Председатель)"),
                types.BotCommand("cleaning", "График уборки"),
                types.BotCommand("workplan", "План работы профбюро"),
                types.BotCommand("profile", "Мой профиль"),
                types.BotCommand("team", "Список команды"),
                types.BotCommand("help", "Справка")
            ],
            scope=types.BotCommandScopeAllPrivateChats()
        )
        if WEBAPP_URL:
            bot.set_chat_menu_button(
                menu_button=types.MenuButtonWebApp(
                    text="📱 Приложение",
                    web_app=types.WebAppInfo(url=WEBAPP_URL)
                )
            )
            logger.info(f"Кнопка MenuButtonWebApp настроена на URL: {WEBAPP_URL}")
    except Exception as e:
        logger.warning(f"Ошибка настройки команд бота: {e}")

    # 3. Запуск фонового планировщика контроля дедлайнов (каждые 45 сек)
    start_scheduler_thread(bot)

    # 4. Запуск бота в фоновом потоке
    bot_thread = threading.Thread(target=run_bot_polling, daemon=True)
    bot_thread.start()

    # 5. Запуск веб-сервера FastAPI / Uvicorn (обслуживает Mini App)
    logger.info(f"Запуск веб-сервера Mini App на http://{WEBAPP_HOST}:{WEBAPP_PORT}...")
    uvicorn.run(app, host=WEBAPP_HOST, port=WEBAPP_PORT, log_level="info")
