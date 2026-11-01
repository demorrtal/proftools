import logging
from datetime import datetime, timedelta
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.filters import Command

from config import ADMIN_ROLES, GENERAL_CHAT_ID
import database as db
from keyboards import (
    get_main_menu_keyboard,
    get_task_actions_keyboard,
    get_cancel_reply_keyboard
)
from handlers.tasks import parse_deadline

logger = logging.getLogger(__name__)
router = Router()

class ExtendDeadlineStates(StatesGroup):
    waiting_for_new_deadline = State()

@router.message(F.text == "📋 Список задач")
@router.message(Command("tasks"))
async def show_tasks_list(message: Message):
    """Отображение списка активных и просроченных задач для председателя и 1-го зама"""
    user_id = message.from_user.id
    user = await db.get_user(user_id)

    if not user or user["role"] not in ADMIN_ROLES:
        await message.answer(
            "⛔ <b>Доступ ограничен.</b>\n"
            "Просматривать и управлять списком всех задач могут только Председатель и 1-й заместитель.",
            parse_mode="HTML"
        )
        return

    tasks = await db.get_active_tasks()
    if not tasks:
        await message.answer(
            "🎉 <b>Активных задач нет!</b>\nВсе задачи выполнены либо еще не созданы.",
            parse_mode="HTML"
        )
        return

    await message.answer(
        f"📋 <b>Список активных задач ({len(tasks)}):</b>\n"
        "Под каждой задачей вы можете отметить её выполнение или продлить дедлайн.",
        parse_mode="HTML"
    )

    now = datetime.now()
    for task in tasks:
        task_id = task["id"]
        title = task["title"]
        target = task["target_roles"]
        target_display = "⭐ ВСЕ СОТРУДНИКИ" if "ALL" in target else ", ".join(target)
        
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

        await message.answer(
            msg_text,
            reply_markup=get_task_actions_keyboard(task_id),
            parse_mode="HTML"
        )

@router.callback_query(F.data.startswith("task_done:"))
async def handle_task_done(callback: CallbackQuery, bot: Bot):
    """Отметка задачи как выполненной"""
    user = await db.get_user(callback.from_user.id)
    if not user or user["role"] not in ADMIN_ROLES:
        await callback.answer("⛔ Только Председатель или 1-й зам могут закрывать задачи.", show_alert=True)
        return

    task_id = int(callback.data.split(":")[1])
    task = await db.get_task(task_id)
    if not task:
        await callback.answer("Задача не найдена.", show_alert=True)
        return

    if task["status"] == "completed":
        await callback.answer("Эта задача уже была выполнена!", show_alert=True)
        return

    # Обновляем статус в БД
    await db.complete_task(task_id)

    # Редактируем сообщение задачи
    done_time = datetime.now().strftime("%d.%m.%Y %H:%M")
    new_text = callback.message.html_text + f"\n\n✅ <b>ВЫПОЛНЕНО ({done_time})</b>"
    try:
        await callback.message.edit_text(new_text, reply_markup=None, parse_mode="HTML")
    except Exception:
        pass

    await callback.answer(f"Задача #{task_id} отмечена как выполненная!")

    # Оповещаем исполнителей об успешном закрытии задачи
    target = task["target_roles"]
    notify_msg = (
        f"✅ <b>ЗАДАЧА #{task_id} ВЫПОЛНЕНА!</b>\n\n"
        f"📝 {task['title']}\n\n"
        f"🎉 Руководство отметило задачу как успешно закрытую."
    )

    if "ALL" in target:
        chat_id_db = await db.get_setting("general_chat_id")
        target_chat_id = chat_id_db or GENERAL_CHAT_ID
        if target_chat_id:
            try:
                await bot.send_message(int(target_chat_id), notify_msg, parse_mode="HTML")
            except Exception:
                pass
        users = await db.get_all_users()
        for u in users:
            try:
                await bot.send_message(u["user_id"], notify_msg, parse_mode="HTML")
            except Exception:
                pass
    else:
        users = await db.get_users_by_roles(target)
        for u in users:
            try:
                await bot.send_message(u["user_id"], notify_msg, parse_mode="HTML")
            except Exception:
                pass

@router.callback_query(F.data.startswith("task_extend:"))
async def handle_task_extend_click(callback: CallbackQuery, state: FSMContext):
    """Нажатие кнопки 'Продлить дедлайн'"""
    user = await db.get_user(callback.from_user.id)
    if not user or user["role"] not in ADMIN_ROLES:
        await callback.answer("⛔ Только Председатель или 1-й зам могут продлевать дедлайн.", show_alert=True)
        return

    task_id = int(callback.data.split(":")[1])
    task = await db.get_task(task_id)
    if not task:
        await callback.answer("Задача не найдена.", show_alert=True)
        return

    await state.clear()
    await state.set_state(ExtendDeadlineStates.waiting_for_new_deadline)
    await state.update_data(extend_task_id=task_id)

    dt_str = task["deadline"]
    try:
        dt = datetime.fromisoformat(dt_str)
        dt_str = dt.strftime("%d.%m.%Y в %H:%M")
    except Exception:
        pass

    await callback.message.answer(
        f"⏳ <b>Продление дедлайна по задаче #{task_id}</b>\n\n"
        f"📝 <b>Задача:</b> {task['title']}\n"
        f"⏰ <b>Текущий дедлайн:</b> {dt_str}\n\n"
        "Введите <b>новую дату и время</b> дедлайна:\n"
        "Например: <code>30.11.2026 19:00</code> или <code>30.11.2026</code>",
        reply_markup=get_cancel_reply_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()

@router.message(ExtendDeadlineStates.waiting_for_new_deadline, F.text == "❌ Отмена")
async def cancel_extend_deadline(message: Message, state: FSMContext):
    """Отмена продления дедлайна"""
    await state.clear()
    user = await db.get_user(message.from_user.id)
    is_admin = user["role"] in ADMIN_ROLES if user else True
    await message.answer("Продление дедлайна отменено.", reply_markup=get_main_menu_keyboard(is_admin))

@router.message(ExtendDeadlineStates.waiting_for_new_deadline)
async def process_new_deadline(message: Message, state: FSMContext, bot: Bot):
    """Сохранение нового дедлайна и оповещение ответственных"""
    raw_date = message.text.strip()
    dt = parse_deadline(raw_date)

    if not dt:
        await message.answer(
            "⚠️ <b>Неверный формат даты.</b>\n"
            "Пожалуйста, введите дату в формате <code>ДД.ММ.ГГГГ ЧЧ:ММ</code> (например: <code>30.11.2026 19:00</code>):",
            parse_mode="HTML"
        )
        return

    now = datetime.now()
    if dt <= now:
        await message.answer(
            "⚠️ <b>Новый дедлайн должен быть в будущем!</b> Попробуйте еще раз:",
            parse_mode="HTML"
        )
        return

    data = await state.get_data()
    task_id = data.get("extend_task_id")
    task = await db.get_task(task_id)

    if not task:
        await state.clear()
        await message.answer("Ошибка: задача не найдена в базе данных.")
        return

    # Вычисляем, какие флаги напоминаний сбросить
    delta = dt - now
    reset_flags = {
        "reminded_overdue": 0,
        "reminded_1d": 1 if delta <= timedelta(days=1) else 0,
        "reminded_3d": 1 if delta <= timedelta(days=3) else 0,
        "reminded_5d": 1 if delta <= timedelta(days=5) else 0,
    }

    new_deadline_iso = dt.strftime("%Y-%m-%d %H:%M:%S")
    new_deadline_display = dt.strftime("%d.%m.%Y в %H:%M")

    await db.extend_task_deadline(task_id, new_deadline_iso, reset_flags)
    await state.clear()

    user = await db.get_user(message.from_user.id)
    is_admin = user["role"] in ADMIN_ROLES if user else True
    admin_name = f"{user['first_name']} {user['last_name']}" if user else message.from_user.full_name
    admin_role = user["role"] if user else "Руководитель"

    await message.answer(
        f"✅ <b>Дедлайн по задаче #{task_id} успешно продлен!</b>\n\n"
        f"⏰ Новый дедлайн: <b>{new_deadline_display}</b>\n"
        f"Бот обновил график напоминаний.",
        reply_markup=get_main_menu_keyboard(is_admin),
        parse_mode="HTML"
    )

    # Оповещаем исполнителей о продлении дедлайна
    target = task["target_roles"]
    extend_notification = (
        f"⏳ <b>ПРОДЛЕНИЕ ДЕДЛАЙНА ПО ЗАДАЧЕ #{task_id}</b>\n\n"
        f"📝 <b>Задача:</b> {task['title']}\n"
        f"⏰ <b>Новый дедлайн:</b> {new_deadline_display}\n"
        f"👤 <b>Продлил:</b> {admin_name} ({admin_role})"
    )

    if "ALL" in target:
        chat_id_db = await db.get_setting("general_chat_id")
        target_chat_id = chat_id_db or GENERAL_CHAT_ID
        if target_chat_id:
            try:
                await bot.send_message(int(target_chat_id), extend_notification, parse_mode="HTML")
            except Exception:
                pass
        users = await db.get_all_users()
        for u in users:
            try:
                await bot.send_message(u["user_id"], extend_notification, parse_mode="HTML")
            except Exception:
                pass
    else:
        users = await db.get_users_by_roles(target)
        for u in users:
            try:
                await bot.send_message(u["user_id"], extend_notification, parse_mode="HTML")
            except Exception:
                pass
