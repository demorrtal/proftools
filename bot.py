import logging
from logging.handlers import RotatingFileHandler
import os
import signal
import sys
from datetime import datetime, timedelta
import telebot
from telebot import types

from config import BOT_TOKEN, ROLES, ADMIN_ROLES, CLEANING_ROLES, GENERAL_CHAT_ID, WEBAPP_URL
import database as db
import keyboards
from scheduler import start_scheduler_thread, send_notification

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        RotatingFileHandler("bot.log", maxBytes=10 * 1024 * 1024, backupCount=3, encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)

if not BOT_TOKEN:
    logger.error("ОШИБКА: BOT_TOKEN не указан в файле .env!")
    sys.exit(1)

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

def handle_shutdown_signal(signum, frame):
    """Корректная остановка бота при получении сигналов от systemd / Docker"""
    sig_name = signal.Signals(signum).name if hasattr(signal, "Signals") else str(signum)
    logger.info(f"Получен сигнал {sig_name}. Завершение работы бота...")
    try:
        bot.stop_polling()
    except Exception as e:
        logger.warning(f"Ошибка при вызове stop_polling: {e}")
    sys.exit(0)

signal.signal(signal.SIGINT, handle_shutdown_signal)
signal.signal(signal.SIGTERM, handle_shutdown_signal)

# Словарь состояний пользователей для пошагового ввода: {user_id: {"step": ..., "data": ...}}
user_states = {}

def parse_deadline(text: str) -> datetime | None:
    """Парсинг различных форматов даты и времени"""
    text = text.strip()
    now = datetime.now()
    formats = [
        ("%d.%m.%Y %H:%M", False),
        ("%d.%m.%Y %H.%M", False),
        ("%d.%m.%Y", True),
        ("%d.%m %H:%M", False),
        ("%d.%m", True),
        ("%Y-%m-%d %H:%M", False),
        ("%Y-%m-%d", True)
    ]
    for fmt, is_date_only in formats:
        try:
            dt = datetime.strptime(text, fmt)
            if "%Y" not in fmt:
                dt = dt.replace(year=now.year)
                if dt < now:
                    dt = dt.replace(year=now.year + 1)
            if is_date_only:
                dt = dt.replace(hour=23, minute=59, second=0)
            return dt
        except ValueError:
            continue
    return None

# ==========================================
# 1. СТАРТ И РЕГИСТРАЦИЯ
# ==========================================

@bot.message_handler(commands=["clear_menu", "hide_menu"])
def handle_clear_menu(message: types.Message):
    """Скрытие кнопок меню в группе для всех участников"""
    bot.send_message(
        message.chat.id,
        "🧹 <b>Меню и кнопки бота скрыты для всех участников этого чата.</b>\n"
        "Для работы с задачами перейдите в личные сообщения с ботом.",
        reply_markup=types.ReplyKeyboardRemove()
    )

@bot.message_handler(commands=["start"])
def handle_start(message: types.Message):
    if message.chat.type in ["group", "supergroup"]:
        bot_username = ""
        try:
            bot_username = f"@{bot.get_me().username}"
        except Exception:
            pass
        bot.send_message(
            message.chat.id,
            f"👋 Бот в группе используется только для оповещений по общим задачам.\n\n"
            f"Чтобы открыть личное меню и управлять задачами, "
            f"перейдите в личные сообщения с ботом: {bot_username}",
            reply_markup=types.ReplyKeyboardRemove()
        )
        return

    user_id = message.from_user.id
    user = db.get_user(user_id)

    if user:
        is_admin = user["role"] in ADMIN_ROLES
        admin_note = "\n👑 У вас права Председателя по созданию и контролю задач." if is_admin else ""
        grp_note = f"\n🎓 Группа: <b>{user.get('group_number') or 'не указана'}</b>"
        bot.send_message(
            message.chat.id,
            f"👋 С возвращением, <b>{user['first_name']} {user['last_name']}</b>!\n"
            f"💼 Ваша должность: <b>{user['role']}</b>{grp_note}\n"
            f"🔗 Telegram: @{user['username'] or 'не указан'}{admin_note}\n\n"
            f"Используйте кнопки меню внизу для работы.",
            reply_markup=keyboards.get_main_menu(is_admin)
        )
        return

    # Начинаем регистрацию
    user_states[user_id] = {"step": "waiting_first_name", "data": {}}
    bot.send_message(
        message.chat.id,
        "👋 <b>Добро пожаловать в систему управления задачами!</b>\n\n"
        "Для начала работы необходимо зарегистрироваться в базе команды.\n"
        "Пожалуйста, введите ваше <b>имя</b>:",
        reply_markup=keyboards.get_cancel_keyboard()
    )

@bot.message_handler(commands=["reregister"])
def handle_reregister(message: types.Message):
    user_id = message.from_user.id
    user_states[user_id] = {"step": "waiting_first_name", "data": {}}
    bot.send_message(
        message.chat.id,
        "🔄 <b>Перерегистрация профиля</b>\n\nВведите ваше <b>имя</b>:",
        reply_markup=keyboards.get_cancel_keyboard()
    )

# ==========================================
# 2. ОСНОВНЫЕ КОМАНДЫ И МЕНЮ
# ==========================================

@bot.message_handler(func=lambda msg: msg.text == "📌 Мои задачи" or msg.text == "/my_tasks")
def handle_my_tasks(message: types.Message):
    user = db.get_user(message.from_user.id)
    if not user:
        bot.send_message(message.chat.id, "Вы еще не зарегистрированы. Отправьте /start для регистрации.")
        return

    tasks = db.get_user_tasks(user["role"])
    if not tasks:
        bot.send_message(
            message.chat.id,
            f"🎉 <b>У вас нет активных задач!</b>\nВсе задачи по вашей должности (<b>{user['role']}</b>) выполнены."
        )
        return

    bot.send_message(
        message.chat.id,
        f"📌 <b>Ваши активные задачи ({len(tasks)}):</b>"
    )
    now = datetime.now()
    for t in tasks:
        try:
            dt = datetime.fromisoformat(t["deadline"])
            deadline_str = dt.strftime("%d.%m.%Y в %H:%M")
            is_overdue = dt < now
        except Exception:
            deadline_str = t["deadline"]
            is_overdue = False

        status_icon = "🔴 ПРОСРОЧЕНА" if is_overdue else "🟡 В работе"
        target_display = "ВСЕ" if (t["target_roles"] == "ALL" or "ALL" in t["target_roles"]) else ", ".join(t["target_roles"])

        msg_text = (
            f"📌 <b>Задача #{t['id']}</b> [{status_icon}]\n\n"
            f"📝 <b>Суть:</b> {t['title']}\n"
            f"👥 <b>Назначено:</b> {target_display}\n"
            f"⏰ <b>Дедлайн:</b> {deadline_str}\n"
            f"👤 <b>Поставил:</b> {t['creator_name']}"
        )
        bot.send_message(message.chat.id, msg_text)

@bot.message_handler(func=lambda msg: msg.text == "✅ Выполненные задачи" or msg.text == "/completed_tasks")
def handle_completed_tasks(message: types.Message):
    user = db.get_user(message.from_user.id)
    if not user or user["role"] not in ADMIN_ROLES:
        bot.send_message(message.chat.id, "⛔ Просматривать архив выполненных задач может только Председатель.")
        return

    tasks = db.get_completed_tasks(limit=30)
    if not tasks:
        bot.send_message(message.chat.id, "Пока нет выполненных задач.")
        return

    bot.send_message(message.chat.id, f"✅ <b>Архив выполненных задач (последние {len(tasks)}):</b>")
    for t in tasks:
        try:
            dt = datetime.fromisoformat(t["deadline"])
            deadline_str = dt.strftime("%d.%m.%Y в %H:%M")
        except Exception:
            deadline_str = t["deadline"]

        target_display = "ВСЕ" if (t["target_roles"] == "ALL" or "ALL" in t["target_roles"]) else ", ".join(t["target_roles"])

        msg_text = (
            f"✅ <b>Задача #{t['id']} (ВЫПОЛНЕНА)</b>\n\n"
            f"📝 <b>Суть:</b> {t['title']}\n"
            f"👥 <b>Было назначено:</b> {target_display}\n"
            f"⏰ <b>Дедлайн был:</b> {deadline_str}\n"
            f"👤 <b>Создал:</b> {t['creator_name']}"
        )
        bot.send_message(message.chat.id, msg_text)

@bot.message_handler(func=lambda msg: msg.text == "🗑️ Снять с должности" or msg.text == "/remove_user")
def handle_remove_user_menu(message: types.Message):
    user = db.get_user(message.from_user.id)
    if not user or user["role"] not in ADMIN_ROLES:
        bot.send_message(message.chat.id, "⛔ Снимать сотрудников с должности может только Председатель.")
        return

    users = db.get_all_users()
    other_users = [u for u in users if u["user_id"] != message.from_user.id]

    if not other_users:
        bot.send_message(message.chat.id, "В базе пока нет других зарегистрированных сотрудников.")
        return

    bot.send_message(
        message.chat.id,
        "🗑️ <b>Снятие сотрудника с должности</b>\n\n"
        "Выберите человека из списка ниже, которого нужно снять с должности:\n"
        "<i>(Его профиль будет удален, а доступ сброшен)</i>",
        reply_markup=keyboards.get_remove_user_keyboard(users, message.from_user.id)
    )

@bot.message_handler(func=lambda msg: msg.text == "➕ Добавить в группу" or msg.text == "/add_to_group")
def handle_add_to_group(message: types.Message):
    user = db.get_user(message.from_user.id)
    if not user or user["role"] not in ADMIN_ROLES:
        bot.send_message(message.chat.id, "⛔ Добавлять бота в группу разрешено только Председателю.")
        return

    try:
        me = bot.get_me()
        bot_username = me.username
    except Exception:
        bot_username = ""

    bot.send_message(
        message.chat.id,
        "👥 <b>Добавление бота в общий рабочий чат команды</b>\n\n"
        "1. Нажмите кнопку ниже и выберите группу команды.\n"
        "2. Назначьте бота <b>администратором</b> группы (чтобы он мог свободно отправлять сообщения).\n"
        "3. Отправьте в эту группу команду:\n"
        "👉 <code>/set_group</code>\n\n"
        "После этого все задачи и напоминания с назначением <b>'ВСЕ'</b> будут автоматически приходить в эту группу!",
        reply_markup=keyboards.get_add_to_group_keyboard(bot_username)
    )

@bot.message_handler(func=lambda msg: msg.text == "🧹 График уборки" or msg.text == "/cleaning")
def handle_cleaning_schedule(message: types.Message):
    user = db.get_user(message.from_user.id)
    can_manage = bool(user and user["role"] in CLEANING_ROLES)
    dates = db.get_cleaning_schedule()

    if not dates:
        text = "🧹 <b>График уборки кабинета:</b>\n\nНа данный момент даты уборки не запланированы."
    else:
        text = "🧹 <b>График уборки кабинета:</b>\n\n"
        for idx, d in enumerate(dates, 1):
            comment = f" — {d['comment']}" if d.get("comment") else ""
            text += f"{idx}. 📅 <b>{d['cleaning_date']}</b>{comment}\n"

    bot.send_message(
        message.chat.id,
        text,
        reply_markup=keyboards.get_cleaning_menu_keyboard(can_manage, bool(dates))
    )

@bot.message_handler(func=lambda msg: msg.text == "📊 План работы профбюро" or msg.text == "/workplan")
def handle_workplan(message: types.Message):
    bot.send_message(
        message.chat.id,
        "📊 <b>План работы профбюро</b>\n\n"
        "Нажмите на кнопку ниже, чтобы перейти к Google Таблице с актуальным планом работы:",
        reply_markup=keyboards.get_workplan_keyboard()
    )

@bot.message_handler(content_types=["new_chat_members"])
def handle_new_chat_member(message: types.Message):
    try:
        bot_id = bot.get_me().id
        for member in message.new_chat_members:
            if member.id == bot_id:
                adder = db.get_user(message.from_user.id)
                if not adder or adder["role"] not in ADMIN_ROLES:
                    bot.send_message(
                        message.chat.id,
                        "⛔ <b>Ошибка доступа!</b>\n\n"
                        "Добавлять бота в групповые чаты разрешено только <b>Председателю</b>.\n"
                        "Бот автоматически покидает этот чат."
                    )
                    bot.leave_chat(message.chat.id)
                    return

                bot.send_message(
                    message.chat.id,
                    "👋 <b>Всем привет!</b> Я бот для управления задачами и контроля дедлайнов команды.\n\n"
                    "Чтобы привязать этот чат как рабочий для оповещений по задачам <b>'ВСЕ'</b>, "
                    "<b>Председатель</b> должен отправить в этот чат команду:\n"
                    "👉 <code>/set_group</code>"
                )
                break
    except Exception as e:
        logger.error(f"Ошибка при обработке добавления в чат: {e}")

@bot.message_handler(func=lambda msg: msg.text == "👤 Мой профиль" or msg.text == "/profile")
def handle_profile(message: types.Message):
    user = db.get_user(message.from_user.id)
    if not user:
        bot.send_message(message.chat.id, "Вы еще не зарегистрированы. Отправьте /start для регистрации.")
        return

    is_admin = user["role"] in ADMIN_ROLES
    role_note = " (Права Председателя)" if is_admin else ""
    grp = user.get("group_number") or "не указана"
    bot.send_message(
        message.chat.id,
        f"👤 <b>Ваш рабочий профиль</b>\n\n"
        f"🔹 <b>ФИО:</b> {user['first_name']} {user['last_name']}\n"
        f"🎓 <b>Группа:</b> {grp}\n"
        f"💼 <b>Должность:</b> {user['role']}{role_note}\n"
        f"🔗 <b>Telegram:</b> @{user['username'] or 'не указан'}\n"
        f"🆔 <b>ID пользователя:</b> <code>{user['user_id']}</code>\n\n"
        f"<i>Для изменения данных введите /reregister</i>",
        reply_markup=keyboards.get_main_menu(is_admin)
    )

@bot.message_handler(func=lambda msg: msg.text == "👥 Список команды" or msg.text == "/team")
def handle_team(message: types.Message):
    users = db.get_all_users()
    if not users:
        bot.send_message(message.chat.id, "В базе пока нет зарегистрированных участников.")
        return

    lines = ["👥 <b>Зарегистрированная команда:</b>\n"]
    for idx, u in enumerate(users, 1):
        uname = f"(@{u['username']})" if u.get("username") else ""
        grp = f" [Гр. {u['group_number']}]" if u.get("group_number") else ""
        lines.append(f"{idx}. <b>{u['role']}</b>: {u['first_name']} {u['last_name']}{grp} {uname}")

    bot.send_message(message.chat.id, "\n".join(lines))

@bot.message_handler(commands=["set_group"])
def handle_set_group(message: types.Message):
    if message.chat.type not in ["group", "supergroup"]:
        bot.send_message(
            message.chat.id,
            "⚠️ Команду <code>/set_group</code> нужно отправлять <b>внутри общего чата вашей команды</b>, "
            "куда добавлен бот."
        )
        return

    user = db.get_user(message.from_user.id)
    if not user or user["role"] not in ADMIN_ROLES:
        bot.send_message(message.chat.id, "⛔ Привязать общий чат может только Председатель.", reply_markup=types.ReplyKeyboardRemove())
        return

    chat_id = str(message.chat.id)
    chat_title = message.chat.title or "Общий чат"
    db.set_setting("general_chat_id", chat_id)

    thread_id = getattr(message, "message_thread_id", None)
    if thread_id:
        db.set_setting("general_topic_id", str(thread_id))
        db.save_forum_topic(thread_id, "Основная тема", chat_id)
        topic_info = f"\n📌 <b>Тема форума:</b> ID <code>{thread_id}</code> (задачи будут отправляться прямо сюда!)"
    else:
        topic_info = "\n📌 <b>Тема форума:</b> Основной раздел (без темы)."

    bot.send_message(
        message.chat.id,
        f"✅ <b>Группа успешно привязана!</b>\n\n"
        f"👥 Чат: <b>{chat_title}</b> (ID: <code>{chat_id}</code>){topic_info}\n\n"
        f"Теперь все задачи и дедлайны с назначением <b>'ВСЕ'</b> будут автоматически приходить сюда.\n"
        f"<i>💡 Чтобы назначить конкретную тему форума, отправьте <code>/set_topic [Название]</code> внутри нужной ветки.</i>",
        message_thread_id=thread_id,
        reply_markup=types.ReplyKeyboardRemove()
    )

@bot.message_handler(commands=["set_topic"])
def handle_set_topic(message: types.Message):
    """Привязка конкретной темы форума для задач 'ВСЕ'"""
    if message.chat.type not in ["group", "supergroup"]:
        bot.send_message(
            message.chat.id,
            "⚠️ Команду <code>/set_topic</code> нужно отправлять <b>внутри группы команды (в нужной теме форума)</b>."
        )
        return

    user = db.get_user(message.from_user.id)
    if not user or user["role"] not in ADMIN_ROLES:
        bot.send_message(message.chat.id, "⛔ Настраивать тему задач может только Председатель.", reply_markup=types.ReplyKeyboardRemove())
        return

    chat_id = str(message.chat.id)
    chat_title = message.chat.title or "Общий чат"
    db.set_setting("general_chat_id", chat_id)

    thread_id = getattr(message, "message_thread_id", None)

    # Извлекаем кастомное название темы (если введено /set_topic Задачи)
    parts = message.text.split(maxsplit=1)
    custom_title = parts[1].strip() if len(parts) > 1 else ""

    if thread_id:
        topic_title = custom_title if custom_title else f"Тема #{thread_id}"
        db.save_forum_topic(thread_id, topic_title, chat_id)
        db.set_setting("general_topic_id", str(thread_id))

        bot.send_message(
            message.chat.id,
            f"✅ <b>Тема для задач 'ВСЕ' успешно установлена!</b>\n\n"
            f"📌 Название темы: <b>{topic_title}</b>\n"
            f"🔢 ID темы: <code>{thread_id}</code>\n"
            f"👥 Группа: <b>{chat_title}</b>\n\n"
            f"Теперь все задачи для всей команды (<b>'ВСЕ'</b>) и напоминания по ним будут публиковаться прямо в эту ветку форума.\n\n"
            f"<i>Для сброса привязки отправьте команду /reset_topic</i>",
            message_thread_id=thread_id,
            reply_markup=types.ReplyKeyboardRemove()
        )
    else:
        db.set_setting("general_topic_id", "")
        bot.send_message(
            message.chat.id,
            f"ℹ️ Команда вызвана в основном разделе группы <b>{chat_title}</b> (без темы).\n\n"
            f"Задачи для <b>'ВСЕ'</b> будут отправляться в общий раздел группы.\n"
            f"Если в группе включены темы, зайдите в нужный топик (ветку) и отправьте команду <code>/set_topic [Название]</code> там.",
            reply_markup=types.ReplyKeyboardRemove()
        )

@bot.message_handler(commands=["reset_topic"])
def handle_reset_topic(message: types.Message):
    """Сброс темы форума для задач 'ВСЕ'"""
    user = db.get_user(message.from_user.id)
    if not user or user["role"] not in ADMIN_ROLES:
        bot.send_message(message.chat.id, "⛔ Сбросить тему может только Председатель.")
        return

    db.set_setting("general_topic_id", "")
    bot.send_message(
        message.chat.id,
        "🔄 <b>Привязка к теме форума сброшена.</b>\n"
        "Задачи для всей команды ('ВСЕ') теперь будут приходить в общий чат группы (без выбора конкретной темы).",
        reply_markup=types.ReplyKeyboardRemove()
    )

@bot.message_handler(func=lambda msg: msg.text == "📌 Тема в группе (ВСЕ)" or msg.text == "/topics")
def handle_topics_menu(message: types.Message):
    """Меню выбора активной темы для Председателя"""
    user = db.get_user(message.from_user.id)
    if not user or user["role"] not in ADMIN_ROLES:
        bot.send_message(message.chat.id, "⛔ Управление темами группы доступно только Председателю.")
        return

    chat_id = db.get_setting("general_chat_id")
    current_topic_id = db.get_setting("general_topic_id")
    topics = db.get_forum_topics()

    active_title = "Основной чат (без темы)"
    if current_topic_id and str(current_topic_id).strip() != "":
        current_obj = db.get_forum_topic(int(current_topic_id)) if str(current_topic_id).isdigit() else None
        active_title = f"{current_obj['title']} (ID: {current_topic_id})" if current_obj else f"ID {current_topic_id}"

    chat_info = f"<code>{chat_id}</code>" if chat_id else "<i>не привязана (используйте /set_group в группе)</i>"

    bot.send_message(
        message.chat.id,
        f"📌 <b>Выбор темы в группе для задач 'ВСЕ'</b>\n\n"
        f"👥 <b>Привязанная группа:</b> {chat_info}\n"
        f"🎯 <b>Текущая активная тема:</b> <b>{active_title}</b>\n\n"
        f"Выберите тему из списка ниже нажатием кнопки (отмечена галочкой ✅), либо добавьте новую прямо из группы:",
        reply_markup=keyboards.get_topics_keyboard(topics, current_topic_id)
    )

@bot.message_handler(func=lambda msg: msg.text == "❓ Помощь" or msg.text == "/help")
def handle_help(message: types.Message):
    user = db.get_user(message.from_user.id)
    is_admin = user["role"] in ADMIN_ROLES if user else False
    admin_help = ""
    if is_admin:
        admin_help = (
            "\n<b>Команды Председателя:</b>\n"
            "➕ <code>/new_task</code> — создать задачу с выбором должностей и дедлайна\n"
            "📋 <code>/tasks</code> — список активных задач (кнопки 'Выполнено' и 'Продлить')\n"
            "✅ <code>/completed_tasks</code> — архив выполненных задач\n"
            "🧹 <code>/cleaning</code> — график уборки кабинета (добавление/удаление дат)\n"
            "🗑️ <code>/remove_user</code> — снять человека с должности\n"
            "👥 <code>/set_group</code> — привязать группу (отправьте в чате группы)\n"
            "📌 <code>/set_topic [Название]</code> — привязать тему форума (отправьте в топике)\n"
            "🔄 <code>/reset_topic</code> — сбросить тему (слать в общий чат)\n"
            "⚙️ <code>/topics</code> — выбор активной темы форума для задач ВСЕ\n"
        )
    bot.send_message(
        message.chat.id,
        "🤖 <b>Справка по боту управления задачами</b>\n\n"
        "<b>Как работает бот:</b>\n"
        "1. Каждый участник при первом входе выбирает свою должность из 11 доступных.\n"
        "2. Председатель ставит задачи конкретным должностям или ВСЕМ.\n"
        "3. Бот автоматически напоминает о дедлайнах за 5, 3 и 1 день, а при просрочке срочно оповещает исполнителя и Председателя.\n"
        f"{admin_help}\n"
        "<b>Общие команды:</b>\n"
        "📌 <code>/my_tasks</code> — просмотр ваших личных задач\n"
        "🧹 <code>/cleaning</code> — график уборки кабинета\n"
        "📊 <code>/workplan</code> — ссылка на план работы профбюро (Google Таблица)\n"
        "👤 <code>/profile</code> — ваш профиль и должность\n"
        "👥 <code>/team</code> — список всей команды\n"
        "➕ <code>/add_to_group</code> — ссылка для добавления бота в группу\n"
        "🔄 <code>/reregister</code> — сменить имя/должность\n"
        "❓ <code>/help</code> — эта справка",
        reply_markup=keyboards.get_main_menu(is_admin)
    )

# ==========================================
# 3. ДОБАВЛЕНИЕ ЗАДАЧИ (Только Председатель)
# ==========================================

@bot.message_handler(func=lambda msg: msg.text == "➕ Новая задача" or msg.text == "/new_task")
def handle_new_task(message: types.Message):
    user = db.get_user(message.from_user.id)
    if not user or user["role"] not in ADMIN_ROLES:
        bot.send_message(
            message.chat.id,
            "⛔ <b>Доступ запрещен.</b>\nДобавлять задачи может только Председатель."
        )
        return

    user_states[message.from_user.id] = {
        "step": "waiting_task_text",
        "data": {"selected_roles": []}
    }
    bot.send_message(
        message.chat.id,
        "📝 <b>Шаг 1 из 3: Текст задачи</b>\n\n"
        "Опишите суть задачи, что именно необходимо сделать:",
        reply_markup=keyboards.get_cancel_keyboard()
    )

# ==========================================
# 4. СПИСОК ЗАДАЧ И УПРАВЛЕНИЕ
# ==========================================

@bot.message_handler(func=lambda msg: msg.text == "📋 Список задач" or msg.text == "/tasks")
def handle_tasks_list(message: types.Message):
    user = db.get_user(message.from_user.id)
    if not user or user["role"] not in ADMIN_ROLES:
        bot.send_message(
            message.chat.id,
            "⛔ <b>Доступ ограничен.</b>\nПросматривать общий список задач и управлять ими может только Председатель."
        )
        return

    tasks = db.get_active_tasks()
    if not tasks:
        bot.send_message(message.chat.id, "🎉 <b>Активных задач нет!</b> Все задачи выполнены.")
        return

    bot.send_message(
        message.chat.id,
        f"📋 <b>Список активных задач ({len(tasks)}):</b>\n"
        "Под каждой задачей есть кнопки отметки о выполнении или продления дедлайна."
    )

    now = datetime.now()
    for task in tasks:
        task_id = task["id"]
        title = task["title"]
        target = task["target_roles"]
        target_display = "ВСЕ" if ("ALL" in target or target == "ALL") else ", ".join(target)

        try:
            dt = datetime.fromisoformat(task["deadline"])
            deadline_str = dt.strftime("%d.%m.%Y в %H:%M")
            is_overdue = dt < now
        except Exception:
            deadline_str = task["deadline"]
            is_overdue = False

        status_icon = "🔴 ПРОСРОЧЕНА" if is_overdue else "🟡 В работе"

        msg_text = (
            f"📌 <b>Задача #{task_id}</b> [{status_icon}]\n\n"
            f"📝 <b>Суть:</b> {title}\n"
            f"👥 <b>Назначено:</b> {target_display}\n"
            f"⏰ <b>Дедлайн:</b> {deadline_str}\n"
            f"👤 <b>Поставил:</b> {task['creator_name']}"
        )

        bot.send_message(
            message.chat.id,
            msg_text,
            reply_markup=keyboards.get_task_actions_keyboard(task_id)
        )

# ==========================================
# 5. ОБРАБОТКА ТЕКСТОВЫХ СОСТОЯНИЙ (FSM)
# ==========================================

@bot.message_handler(content_types=["text"])
def handle_text_messages(message: types.Message):
    if message.chat.type in ["group", "supergroup"]:
        # В группах игнорируем обычный текстовый чат, не шлем меню
        return

    user_id = message.from_user.id
    text = message.text.strip()

    # Проверка на отмену
    if text == "❌ Отмена":
        user_states.pop(user_id, None)
        user = db.get_user(user_id)
        is_admin = user["role"] in ADMIN_ROLES if user else False
        bot.send_message(message.chat.id, "Действие отменено.", reply_markup=keyboards.get_main_menu(is_admin))
        return

    state_info = user_states.get(user_id)
    if not state_info:
        return

    step = state_info.get("step")
    data = state_info.get("data", {})

    # Шаг регистрации: Имя
    if step == "waiting_first_name":
        if len(text) < 2 or len(text) > 40:
            bot.send_message(message.chat.id, "⚠️ Имя должно содержать от 2 до 40 символов. Попробуйте еще раз:")
            return
        data["first_name"] = text
        user_states[user_id] = {"step": "waiting_last_name", "data": data}
        bot.send_message(
            message.chat.id,
            f"Принято, {text}!\nТеперь введите вашу <b>фамилию</b>:",
            reply_markup=keyboards.get_cancel_keyboard()
        )
        return

    # Шаг регистрации: Фамилия
    elif step == "waiting_last_name":
        if len(text) < 2 or len(text) > 40:
            bot.send_message(message.chat.id, "⚠️ Фамилия должна содержать от 2 до 40 символов. Попробуйте еще раз:")
            return
        data["last_name"] = text
        user_states[user_id] = {"step": "waiting_group_number", "data": data}
        bot.send_message(
            message.chat.id,
            "Отлично!\nТеперь введите номер вашей <b>учебной группы</b> (например: <code>ИУ9-51Б</code> или <code>211-321</code>):",
            reply_markup=keyboards.get_cancel_keyboard()
        )
        return

    # Шаг регистрации: Номер группы
    elif step == "waiting_group_number":
        if len(text) < 1 or len(text) > 30:
            bot.send_message(message.chat.id, "⚠️ Номер группы должен содержать от 1 до 30 символов. Попробуйте еще раз:")
            return
        data["group_number"] = text
        user_states[user_id] = {"step": "waiting_role", "data": data}

        taken_roles = db.get_taken_roles(exclude_user_id=user_id)
        role_kb = keyboards.get_registration_roles_keyboard(taken_roles)

        if not role_kb.keyboard:
            bot.send_message(
                message.chat.id,
                "⚠️ <b>Внимание!</b>\nВсе доступные должности в команде на данный момент уже заняты.\n"
                "Обратитесь к Председателю для освобождения нужной должности."
            )
            return

        bot.send_message(
            message.chat.id,
            "Отлично! Теперь выберите вашу <b>должность</b> из свободных вакансий ниже:\n"
            "<i>(Занятые должности автоматически скрыты из списка)</i>",
            reply_markup=role_kb
        )
        return

    # Шаг создания задачи: Текст задачи
    elif step == "waiting_task_text":
        if len(text) < 3:
            bot.send_message(message.chat.id, "⚠️ Описание задачи слишком короткое. Опишите подробнее:")
            return
        data["task_text"] = text
        data["selected_roles"] = []
        user_states[user_id] = {"step": "waiting_roles", "data": data}
        bot.send_message(
            message.chat.id,
            "👥 <b>Шаг 2 из 3: Для кого эта задача?</b>\n\n"
            "Отметьте нужные должности кнопками ниже (можно выбрать несколько).\n"
            "Или нажмите <b>'ВСЕ'</b> для всей команды.\n\n"
            "После выбора нажмите зеленую кнопку <b>'Готово / Далее'</b>:",
            reply_markup=keyboards.get_target_roles_keyboard([])
        )
        return

    # Шаг создания задачи: Дедлайн
    elif step == "waiting_deadline":
        dt = parse_deadline(text)
        if not dt:
            bot.send_message(
                message.chat.id,
                "⚠️ <b>Неверный формат даты.</b>\n"
                "Введите дату в формате <code>ДД.ММ.ГГГГ ЧЧ:ММ</code> (например: <code>25.11.2026 18:00</code>):"
            )
            return

        now = datetime.now()
        if dt <= now:
            bot.send_message(message.chat.id, "⚠️ <b>Дедлайн не может быть в прошлом!</b> Укажите будущую дату:")
            return

        task_text = data.get("task_text")
        selected_roles = data.get("selected_roles", [])
        creator = db.get_user(user_id)
        creator_name = f"{creator['first_name']} {creator['last_name']}" if creator else message.from_user.full_name
        creator_role = creator["role"] if creator else "Руководитель"

        deadline_iso = dt.strftime("%Y-%m-%d %H:%M:%S")
        deadline_display = dt.strftime("%d.%m.%Y в %H:%M")

        task_id = db.create_task(
            title=task_text,
            creator_id=user_id,
            creator_name=f"{creator_name} ({creator_role})",
            target_roles=selected_roles,
            deadline_iso=deadline_iso
        )

        user_states.pop(user_id, None)
        is_admin = creator["role"] in ADMIN_ROLES if creator else True
        target_display = "ВСЕ" if ("ALL" in selected_roles or selected_roles == "ALL") else ", ".join(selected_roles)
        target_confirm = target_display
        if "ALL" in selected_roles or selected_roles == "ALL":
            topic_id = db.get_setting("general_topic_id")
            topic_obj = db.get_forum_topic(int(topic_id)) if (topic_id and str(topic_id).isdigit()) else None
            top_name = f"<b>{topic_obj['title']}</b>" if topic_obj else (f"ID <code>{topic_id}</code>" if topic_id else "Основной чат")
            target_confirm = f"ВСЕ <i>(опубликовано в: {top_name})</i>"

        bot.send_message(
            message.chat.id,
            f"✅ <b>Задача успешно создана!</b>\n\n"
            f"📝 <b>Задача:</b> {task_text}\n"
            f"👥 <b>Кому:</b> {target_confirm}\n"
            f"⏰ <b>Дедлайн:</b> {deadline_display}",
            reply_markup=keyboards.get_main_menu(is_admin)
        )

        # Рассылка оповещения о новой задаче
        notify_msg = (
            f"🆕 <b>НОВАЯ ЗАДАЧА</b>\n\n"
            f"📝 {task_text}\n\n"
            f"👥 <b>Кому:</b> {target_display}\n"
            f"⏰ <b>Дедлайн:</b> {deadline_display}\n"
            f"👤 <b>Поставил:</b> {creator_name} ({creator_role})"
        )
        send_notification(bot, selected_roles, notify_msg)
        return

    # Шаг добавления даты уборки
    elif step == "waiting_cleaning_date":
        raw_text = text
        if "-" in raw_text:
            parts = [p.strip() for p in raw_text.split("-", 1)]
            date_part = parts[0]
            comment_part = parts[1]
        else:
            date_part = raw_text
            comment_part = ""

        db.add_cleaning_date(date_part, comment_part)
        user_states.pop(user_id, None)

        user = db.get_user(user_id)
        is_admin = bool(user and user["role"] in ADMIN_ROLES)
        comment_display = f" ({comment_part})" if comment_part else ""
        bot.send_message(
            message.chat.id,
            f"✅ Дата уборки <b>{date_part}</b>{comment_display} успешно добавлена в график!",
            reply_markup=keyboards.get_main_menu(is_admin=is_admin)
        )
        return

    # Шаг продления дедлайна
    elif step == "waiting_new_deadline":
        dt = parse_deadline(text)
        if not dt:
            bot.send_message(
                message.chat.id,
                "⚠️ <b>Неверный формат даты.</b>\nВведите дату в формате <code>ДД.ММ.ГГГГ ЧЧ:ММ</code>:"
            )
            return

        now = datetime.now()
        if dt <= now:
            bot.send_message(message.chat.id, "⚠️ Новый дедлайн должен быть в будущем! Попробуйте снова:")
            return

        task_id = data.get("task_id")
        task = db.get_task(task_id)
        if not task:
            user_states.pop(user_id, None)
            bot.send_message(message.chat.id, "Ошибка: задача не найдена.")
            return

        delta = dt - now
        reset_flags = {
            "reminded_overdue": 0,
            "reminded_1d": 1 if delta <= timedelta(days=1) else 0,
            "reminded_3d": 1 if delta <= timedelta(days=3) else 0,
            "reminded_5d": 1 if delta <= timedelta(days=5) else 0,
        }

        new_deadline_iso = dt.strftime("%Y-%m-%d %H:%M:%S")
        new_deadline_display = dt.strftime("%d.%m.%Y в %H:%M")

        db.extend_task_deadline(task_id, new_deadline_iso, reset_flags)
        user_states.pop(user_id, None)

        user = db.get_user(user_id)
        is_admin = user["role"] in ADMIN_ROLES if user else True
        admin_name = f"{user['first_name']} {user['last_name']}" if user else message.from_user.full_name
        admin_role = user["role"] if user else "Руководитель"

        bot.send_message(
            message.chat.id,
            f"✅ <b>Дедлайн по задаче #{task_id} успешно продлен!</b>\n\n"
            f"⏰ Новый дедлайн: <b>{new_deadline_display}</b>",
            reply_markup=keyboards.get_main_menu(is_admin)
        )

        extend_msg = (
            f"⏳ <b>ПРОДЛЕНИЕ ДЕДЛАЙНА ПО ЗАДАЧЕ #{task_id}</b>\n\n"
            f"📝 <b>Задача:</b> {task['title']}\n"
            f"⏰ <b>Новый дедлайн:</b> {new_deadline_display}\n"
            f"👤 <b>Продлил:</b> {admin_name} ({admin_role})"
        )
        send_notification(bot, task["target_roles"], extend_msg)
        return

# ==========================================
# 6. ИНЛАЙН КНОПКИ (CALLBACKS)
# ==========================================

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call: types.CallbackQuery):
    user_id = call.from_user.id
    data_str = call.data

    # Выбор должности при регистрации
    if data_str.startswith("reg_role:"):
        role_idx = int(data_str.split(":")[1])
        selected_role = ROLES[role_idx]

        # Проверка: не занята ли должность другим участником
        taken_roles = db.get_taken_roles(exclude_user_id=user_id)
        if selected_role in taken_roles:
            bot.answer_callback_query(call.id, "⚠️ Эта должность уже занята! Пожалуйста, выберите другую.", show_alert=True)
            try:
                bot.edit_message_reply_markup(
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=keyboards.get_registration_roles_keyboard(taken_roles)
                )
            except Exception:
                pass
            return

        state_info = user_states.get(user_id, {})
        u_data = state_info.get("data", {})
        first_name = u_data.get("first_name", call.from_user.first_name)
        last_name = u_data.get("last_name", call.from_user.last_name or "")
        group_number = u_data.get("group_number", "не указана")
        username = call.from_user.username

        db.save_user(
            user_id=user_id,
            first_name=first_name,
            last_name=last_name,
            group_number=group_number,
            username=username,
            role=selected_role
        )

        user_states.pop(user_id, None)
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except Exception:
            pass

        is_admin = selected_role in ADMIN_ROLES
        perks = "\n👑 <b>Вам доступны функции Председателя по созданию и контролю задач!</b>" if is_admin else ""

        bot.send_message(
            call.message.chat.id,
            f"🎉 <b>Регистрация успешно завершена!</b>\n\n"
            f"👤 <b>ФИО:</b> {first_name} {last_name}\n"
            f"🎓 <b>Группа:</b> {group_number}\n"
            f"💼 <b>Должность:</b> {selected_role}\n"
            f"🔗 <b>Telegram:</b> @{username or 'нет'}\n"
            f"{perks}\n\n"
            f"Бот будет напоминать вам о дедлайнах за 5, 3 и 1 день, а также в случае просрочки.",
            reply_markup=keyboards.get_main_menu(is_admin)
        )
        bot.answer_callback_query(call.id, "Регистрация завершена!")
        return

    # Выбор ролей при создании задачи
    if data_str.startswith("target:"):
        action = data_str.split(":")[1]
        state_info = user_states.get(user_id)
        if not state_info or state_info.get("step") != "waiting_roles":
            bot.answer_callback_query(call.id, "Создание задачи не активно.")
            return

        selected_roles = state_info["data"].get("selected_roles", [])

        if action == "CANCEL":
            user_states.pop(user_id, None)
            try:
                bot.delete_message(call.message.chat.id, call.message.message_id)
            except Exception:
                pass
            user = db.get_user(user_id)
            is_admin = user["role"] in ADMIN_ROLES if user else True
            bot.send_message(call.message.chat.id, "Создание задачи отменено.", reply_markup=keyboards.get_main_menu(is_admin))
            bot.answer_callback_query(call.id)
            return

        elif action == "DONE":
            if not selected_roles:
                bot.answer_callback_query(call.id, "⚠️ Выберите хотя бы одну должность или вариант 'ВСЕ'!", show_alert=True)
                return

            state_info["step"] = "waiting_deadline"
            try:
                bot.delete_message(call.message.chat.id, call.message.message_id)
            except Exception:
                pass

            if "ALL" in selected_roles or selected_roles == "ALL":
                topic_id = db.get_setting("general_topic_id")
                topic_obj = db.get_forum_topic(int(topic_id)) if (topic_id and str(topic_id).isdigit()) else None
                top_name = f"<b>{topic_obj['title']}</b>" if topic_obj else (f"ID <code>{topic_id}</code>" if topic_id else "Основной раздел (без темы)")
                roles_display = f"ВСЕ <i>(будет опубликовано в: {top_name})</i>"
            else:
                roles_display = ", ".join(selected_roles)

            bot.send_message(
                call.message.chat.id,
                f"🎯 Выбрано: {roles_display}\n\n"
                "⏰ <b>Шаг 3 из 3: Дедлайн задачи</b>\n\n"
                "Введите дату и время дедлайна в формате:\n"
                "• <code>25.11.2026 18:00</code> (дата и время)\n"
                "• <code>25.11.2026</code> (дедлайн до конца дня 23:59)\n"
                "• <code>25.11 15:00</code> (текущий год)",
                reply_markup=keyboards.get_cancel_keyboard()
            )
            bot.answer_callback_query(call.id)
            return

        elif action == "ALL":
            if "ALL" in selected_roles:
                selected_roles = []
            else:
                selected_roles = ["ALL"]
        else:
            if "ALL" in selected_roles:
                selected_roles = []
            try:
                role_idx = int(action)
                role_name = ROLES[role_idx]
                if role_name in selected_roles:
                    selected_roles.remove(role_name)
                else:
                    selected_roles.append(role_name)
            except Exception:
                pass

        state_info["data"]["selected_roles"] = selected_roles
        try:
            bot.edit_message_reply_markup(
                call.message.chat.id,
                call.message.message_id,
                reply_markup=keyboards.get_target_roles_keyboard(selected_roles)
            )
        except Exception:
            pass
        bot.answer_callback_query(call.id)
        return

    # Завершение задачи
    if data_str.startswith("done:"):
        user = db.get_user(user_id)
        if not user or user["role"] not in ADMIN_ROLES:
            bot.answer_callback_query(call.id, "⛔ Только Председатель может закрывать задачи.", show_alert=True)
            return

        task_id = int(data_str.split(":")[1])
        task = db.get_task(task_id)
        if not task:
            bot.answer_callback_query(call.id, "Задача не найдена.")
            return

        db.complete_task(task_id)
        done_time = datetime.now().strftime("%d.%m.%Y %H:%M")
        try:
            new_text = call.message.html_text + f"\n\n✅ <b>ВЫПОЛНЕНО ({done_time})</b>"
            bot.edit_message_text(new_text, call.message.chat.id, call.message.message_id, reply_markup=None)
        except Exception:
            pass

        bot.answer_callback_query(call.id, f"Задача #{task_id} отмечена как выполненная!")

        # Оповещаем исполнителей
        done_msg = (
            f"✅ <b>ЗАДАЧА #{task_id} ВЫПОЛНЕНА!</b>\n\n"
            f"📝 {task['title']}\n\n"
            f"🎉 Председатель отметил задачу как успешно закрытую."
        )
        send_notification(bot, task["target_roles"], done_msg)
        return

    # Продление дедлайна
    if data_str.startswith("extend:"):
        user = db.get_user(user_id)
        if not user or user["role"] not in ADMIN_ROLES:
            bot.answer_callback_query(call.id, "⛔ Только Председатель может продлевать дедлайн.", show_alert=True)
            return

        task_id = int(data_str.split(":")[1])
        task = db.get_task(task_id)
        if not task:
            bot.answer_callback_query(call.id, "Задача не найдена.")
            return

        user_states[user_id] = {
            "step": "waiting_new_deadline",
            "data": {"task_id": task_id}
        }

        dt_str = task["deadline"]
        try:
            dt = datetime.fromisoformat(dt_str)
            dt_str = dt.strftime("%d.%m.%Y в %H:%M")
        except Exception:
            pass

        bot.send_message(
            call.message.chat.id,
            f"⏳ <b>Продление дедлайна по задаче #{task_id}</b>\n\n"
            f"📝 <b>Задача:</b> {task['title']}\n"
            f"⏰ <b>Текущий дедлайн:</b> {dt_str}\n\n"
            "Введите <b>новую дату и время</b> дедлайна:\n"
            "Например: <code>30.11.2026 19:00</code> или <code>30.11.2026</code>",
            reply_markup=keyboards.get_cancel_keyboard()
        )
        bot.answer_callback_query(call.id)
        return

    # Выбор пользователя для снятия с должности (Председатель)
    if data_str.startswith("rm_usr:"):
        user = db.get_user(user_id)
        if not user or user["role"] not in ADMIN_ROLES:
            bot.answer_callback_query(call.id, "⛔ Доступно только Председателю.", show_alert=True)
            return

        target_id = int(data_str.split(":")[1])
        target_user = db.get_user(target_id)
        if not target_user:
            bot.answer_callback_query(call.id, "Пользователь не найден в базе.", show_alert=True)
            return

        bot.edit_message_text(
            f"⚠️ <b>Подтверждение действия</b>\n\n"
            f"Вы действительно хотите снять сотрудника <b>{target_user['first_name']} {target_user['last_name']}</b> "
            f"с должности <b>{target_user['role']}</b>?\n\n"
            "Его профиль будет удален из базы, а доступ сброшен.",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=keyboards.get_confirm_remove_keyboard(target_id)
        )
        bot.answer_callback_query(call.id)
        return

    # Подтверждение снятия с должности
    if data_str.startswith("conf_rm:"):
        user = db.get_user(user_id)
        if not user or user["role"] not in ADMIN_ROLES:
            bot.answer_callback_query(call.id, "⛔ Доступно только Председателю.", show_alert=True)
            return

        target_id = int(data_str.split(":")[1])
        target_user = db.get_user(target_id)
        if target_user:
            db.delete_user(target_id)
            bot.edit_message_text(
                f"✅ Сотрудник <b>{target_user['first_name']} {target_user['last_name']}</b> "
                f"успешно снят с должности <b>{target_user['role']}</b>.",
                call.message.chat.id,
                call.message.message_id
            )
            bot.answer_callback_query(call.id, "Сотрудник снят с должности!")

            # Оповещаем самого сотрудника
            try:
                bot.send_message(
                    target_id,
                    f"⚠️ <b>Внимание!</b>\n\n"
                    f"Председатель снял вас с должности <b>{target_user['role']}</b>.\n"
                    f"Ваш профиль в боте был сброшен. Чтобы зарегистрироваться заново, отправьте команду /start."
                )
            except Exception:
                pass
        else:
            bot.answer_callback_query(call.id, "Пользователь уже удален.")
        return

    # Отмена удаления
    if data_str == "rm_cancel":
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except Exception:
            pass
        bot.answer_callback_query(call.id, "Отменено.")
        return

    # Добавление даты уборки (Председатель и Завхоз)
    if data_str == "clean:add":
        user = db.get_user(user_id)
        if not user or user["role"] not in CLEANING_ROLES:
            bot.answer_callback_query(call.id, "⛔ Доступно только Председателю и Завхозу.", show_alert=True)
            return

        user_states[user_id] = {"step": "waiting_cleaning_date", "data": {}}
        bot.send_message(
            call.message.chat.id,
            "📅 <b>Добавление даты уборки кабинета</b>\n\n"
            "Введите дату уборки (и при желании комментарий через дефис).\n"
            "Например:\n"
            "• <code>10.11.2026</code>\n"
            "• <code>15.11.2026 - Генеральная уборка</code>\n"
            "• <code>20.11 в 18:00</code>",
            reply_markup=keyboards.get_cancel_keyboard()
        )
        bot.answer_callback_query(call.id)
        return

    # Меню удаления даты уборки (Председатель и Завхоз)
    if data_str == "clean:del_menu":
        user = db.get_user(user_id)
        if not user or user["role"] not in CLEANING_ROLES:
            bot.answer_callback_query(call.id, "⛔ Доступно только Председателю и Завхозу.", show_alert=True)
            return

        dates = db.get_cleaning_schedule()
        if not dates:
            bot.answer_callback_query(call.id, "В графике нет дат для удаления.", show_alert=True)
            return

        bot.edit_message_text(
            "🗑️ <b>Выберите дату, которую нужно удалить из графика:</b>",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=keyboards.get_delete_cleaning_keyboard(dates)
        )
        bot.answer_callback_query(call.id)
        return

    # Удаление конкретной даты уборки
    if data_str.startswith("clean:del:"):
        user = db.get_user(user_id)
        if not user or user["role"] not in CLEANING_ROLES:
            bot.answer_callback_query(call.id, "⛔ Доступно только Председателю и Завхозу.", show_alert=True)
            return

        schedule_id = int(data_str.split(":")[2])
        db.delete_cleaning_date(schedule_id)
        bot.edit_message_text(
            "✅ Дата уборки успешно удалена из графика.",
            call.message.chat.id,
            call.message.message_id
        )
        bot.answer_callback_query(call.id, "Удалено!")
        return

    # Отмена в меню уборки
    if data_str == "clean:cancel":
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except Exception:
            pass
        bot.answer_callback_query(call.id, "Отменено.")
        return

    # Выбор активной темы для задач ВСЕ
    if data_str.startswith("set_active_topic:"):
        user = db.get_user(user_id)
        if not user or user["role"] not in ADMIN_ROLES:
            bot.answer_callback_query(call.id, "⛔ Доступно только Председателю.", show_alert=True)
            return

        choice = data_str.split(":")[1]
        if choice == "none":
            db.set_setting("general_topic_id", "")
            bot.answer_callback_query(call.id, "Выбран Основной чат (без темы)")
        else:
            db.set_setting("general_topic_id", choice)
            top_obj = db.get_forum_topic(int(choice)) if choice.isdigit() else None
            top_name = top_obj["title"] if top_obj else f"ID {choice}"
            bot.answer_callback_query(call.id, f"Выбрана тема: {top_name}")

        # Обновляем инлайн-кнопки
        chat_id = db.get_setting("general_chat_id")
        current_topic_id = db.get_setting("general_topic_id")
        topics = db.get_forum_topics()

        active_title = "Основной чат (без темы)"
        if current_topic_id and str(current_topic_id).strip() != "":
            current_obj = db.get_forum_topic(int(current_topic_id)) if str(current_topic_id).isdigit() else None
            active_title = f"{current_obj['title']} (ID: {current_topic_id})" if current_obj else f"ID {current_topic_id}"

        chat_info = f"<code>{chat_id}</code>" if chat_id else "<i>не привязана</i>"
        try:
            bot.edit_message_text(
                f"📌 <b>Выбор темы в группе для задач 'ВСЕ'</b>\n\n"
                f"👥 <b>Привязанная группа:</b> {chat_info}\n"
                f"🎯 <b>Текущая активная тема:</b> <b>{active_title}</b>\n\n"
                f"Выберите тему из списка ниже нажатием кнопки (отмечена галочкой ✅), либо добавьте новую прямо из группы:",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=keyboards.get_topics_keyboard(topics, current_topic_id)
            )
        except Exception:
            pass
        return

    # Справка по добавлению темы
    if data_str == "topic:help":
        bot.answer_callback_query(call.id)
        bot.send_message(
            call.message.chat.id,
            "💡 <b>Как добавить тему (топик) форума в этот список:</b>\n\n"
            "1. Зайдите в супергруппу вашей команды.\n"
            "2. Откройте нужную ветку/топик (например, 'Задачи' или 'Дедлайны').\n"
            "3. Отправьте прямо в эту ветку команду:\n"
            "👉 <code>/set_topic Название темы</code>\n\n"
            "Бот автоматически считает ID этой ветки, сохранит её с указанным названием и добавит в кнопки быстрого выбора!"
        )
        return

@bot.message_handler(commands=["app", "webapp"])
def handle_app_command(message: types.Message):
    """Открыть Telegram Mini App"""
    if WEBAPP_URL:
        bot.send_message(
            message.chat.id,
            "📱 <b>Telegram Mini App Proftools</b>\n\n"
            "Нажмите кнопку ниже для запуска полноэкранного приложения:",
            reply_markup=keyboards.get_webapp_inline_keyboard()
        )
    else:
        bot.send_message(
            message.chat.id,
            "ℹ️ <b>Mini App еще не подключен</b>\n\n"
            "Для подключения укажите <code>WEBAPP_URL</code> (HTTPS-ссылку на ваше приложение) в файле <code>.env</code>."
        )

# ==========================================
# ТОЧКА ВХОДА
# ==========================================
if __name__ == "__main__":
    logger.info("Запуск Telegram-бота...")
    db.init_db()

    # Отключаем отображение команд бота в группах, настраиваем только для ЛС
    try:
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
        logger.info("Команды бота настроены исключительно для личных диалогов.")

        # Настраиваем главную кнопку WebApp внизу экрана (Menu Button слева от ввода)
        if WEBAPP_URL:
            bot.set_chat_menu_button(
                menu_button=types.MenuButtonWebApp(
                    text="📱 Приложение",
                    web_app=types.WebAppInfo(url=WEBAPP_URL)
                )
            )
            logger.info(f"Кнопка MenuButtonWebApp настроена на URL: {WEBAPP_URL}")
    except Exception as e:
        logger.warning(f"Не удалось настроить scopes/menu_button: {e}")

    # Запускаем фоновый поток контроля дедлайнов (каждые 45 сек)
    start_scheduler_thread(bot)

    logger.info("Бот успешно запущен и ожидает сообщений!")
    bot.infinity_polling(timeout=20, long_polling_timeout=20)
