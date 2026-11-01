import os
from dotenv import load_dotenv

load_dotenv()

# Токен бота из Telegram @BotFather
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

# ID общего чата для задач "ВСЕ" (можно задать в .env или настроить прямо из бота командой /set_group в группе)
GENERAL_CHAT_ID = os.getenv("GENERAL_CHAT_ID")
if GENERAL_CHAT_ID:
    try:
        GENERAL_CHAT_ID = int(GENERAL_CHAT_ID.strip())
    except ValueError:
        pass

# Путь к базе данных SQLite
DATABASE_PATH = os.getenv("DATABASE_PATH", "bot_database.db")

# Список из 11 официальных должностей
ROLES = [
    "Председатель",
    "1-й заместитель",
    "2-й заместитель",
    "Руковод медиа",
    "Руковод ивента",
    "Руковод админки",
    "Руковод партнерки",
    "Зам по проектам",
    "Завхоз",
    "Секретарь",
    "Руковод адаптеров"
]

# Должности с правами управления задачами (только Председатель)
ADMIN_ROLES = ["Председатель"]

# Должности с правами управления графиком уборки (Председатель и Завхоз)
CLEANING_ROLES = ["Председатель", "Завхоз"]
