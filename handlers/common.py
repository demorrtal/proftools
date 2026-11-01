import logging
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command

from config import ADMIN_ROLES, ROLES
import database as db
from keyboards import get_main_menu_keyboard

logger = logging.getLogger(__name__)
router = Router()

@router.message(F.text == "👤 Мой профиль")
@router.message(Command("profile"))
async def show_profile(message: Message):
    """Показать профиль текущего пользователя"""
    user = await db.get_user(message.from_user.id)
    if not user:
        await message.answer("Вы еще не зарегистрированы. Напишите команду /start для регистрации.")
        return

    is_admin = user["role"] in ADMIN_ROLES
    role_info = " (Права управления задачами)" if is_admin else ""

    await message.answer(
        f"👤 <b>Ваш рабочий профиль</b>\n\n"
        f"🔹 <b>ФИО:</b> {user['first_name']} {user['last_name']}\n"
        f"💼 <b>Должность:</b> {user['role']}{role_info}\n"
        f"🔗 <b>Telegram:</b> @{user['username'] or 'не указан'}\n"
        f"🆔 <b>ID пользователя:</b> <code>{user['user_id']}</code>\n\n"
        f"<i>Для изменения имени или должности введите команду /reregister</i>",
        reply_markup=get_main_menu_keyboard(is_admin),
        parse_mode="HTML"
    )

@router.message(F.text == "👥 Список команды")
@router.message(Command("team"))
async def show_team(message: Message):
    """Список всех зарегистрированных участников команды"""
    users = await db.get_all_users()
    if not users:
        await message.answer("В базе пока нет зарегистрированных участников.")
        return

    text_lines = ["👥 <b>Зарегистрированная команда:</b>\n"]
    for idx, u in enumerate(users, 1):
        uname = f"(@{u['username']})" if u['username'] else ""
        text_lines.append(f"{idx}. <b>{u['role']}</b>: {u['first_name']} {u['last_name']} {uname}")

    await message.answer("\n".join(text_lines), parse_mode="HTML")

@router.message(Command("set_group"))
async def set_group_chat(message: Message):
    """Привязка общего чата для задач 'ВСЕ' (команда вводится внутри группы)"""
    if message.chat.type not in ["group", "supergroup"]:
        await message.answer(
            "⚠️ Команду <code>/set_group</code> нужно отправлять <b>внутри общего чата вашей команды</b>, "
            "куда бот добавлен участником или администратором.",
            parse_mode="HTML"
        )
        return

    user = await db.get_user(message.from_user.id)
    if not user or user["role"] not in ADMIN_ROLES:
        await message.answer("⛔ Привязать общий чат могут только Председатель или 1-й заместитель.")
        return

    chat_id = str(message.chat.id)
    chat_title = message.chat.title or "Общий чат"
    await db.set_setting("general_chat_id", chat_id)

    await message.answer(
        f"✅ <b>Группа успешно привязана!</b>\n\n"
        f"Чат: <b>{chat_title}</b> (ID: <code>{chat_id}</code>)\n"
        f"Теперь все задачи и дедлайны с назначением <b>'ВСЕ'</b> будут автоматически приходить в эту группу.",
        parse_mode="HTML"
    )

@router.message(F.text == "❓ Помощь")
@router.message(Command("help"))
async def show_help(message: Message):
    """Справка по боту и командам"""
    user = await db.get_user(message.from_user.id)
    is_admin = user["role"] in ADMIN_ROLES if user else False

    admin_help = ""
    if is_admin:
        admin_help = (
            "\n<b>Команды руководителя:</b>\n"
            "➕ <code>/new_task</code> — создать новую задачу с выбором ролей и дедлайна\n"
            "📋 <code>/tasks</code> — список активных задач (кнопки 'Выполнено' и 'Продлить')\n"
            "👥 <code>/set_group</code> — отправьте эту команду в группу, чтобы привязать её как общий чат\n"
        )

    await message.answer(
        "🤖 <b>Справка по боту управления задачами</b>\n\n"
        "<b>Как работает бот:</b>\n"
        "1. Каждый участник при входе выбирает свою должность из 11 доступных.\n"
        "2. Руководство (Председатель и 1-й зам) ставит задачи конкретным должностям или ВСЕМ.\n"
        "3. Бот автоматически напоминает о дедлайнах:\n"
        "   • <b>за 5 дней</b> до срока\n"
        "   • <b>за 3 дня</b> до срока\n"
        "   • <b>за 1 день</b> до срока\n"
        "   • <b>при просрочке дедлайна</b> — срочное оповещение исполнителя и Председателя!\n"
        f"{admin_help}\n"
        "<b>Общие команды:</b>\n"
        "👤 <code>/profile</code> — ваш профиль и должность\n"
        "👥 <code>/team</code> — посмотреть список всей команды\n"
        "🔄 <code>/reregister</code> — сменить имя/должность\n"
        "❓ <code>/help</code> — это сообщение со справкой",
        reply_markup=get_main_menu_keyboard(is_admin),
        parse_mode="HTML"
    )
