import json
import logging
from datetime import datetime
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.filters import Command

from config import ROLES, ADMIN_ROLES, GENERAL_CHAT_ID
import database as db
from keyboards import (
    get_main_menu_keyboard,
    get_target_roles_keyboard,
    get_cancel_reply_keyboard
)

logger = logging.getLogger(__name__)
router = Router()

class TaskCreationStates(StatesGroup):
    waiting_for_text = State()
    waiting_for_roles = State()
    waiting_for_deadline = State()

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
            # Если формат без года, подставляем текущий год
            if "%Y" not in fmt:
                dt = dt.replace(year=now.year)
                # Если дата уже прошла в этом году, возможно имели в виду следующий год
                if dt < now:
                    dt = dt.replace(year=now.year + 1)
            # Если время не указано, ставим конец дня 23:59
            if is_date_only:
                dt = dt.replace(hour=23, minute=59, second=0)
            return dt
        except ValueError:
            continue
    return None

@router.message(F.text == "➕ Новая задача")
@router.message(Command("new_task"))
async def start_task_creation(message: Message, state: FSMContext):
    """Старт создания новой задачи (только председатель и 1-й зам)"""
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    
    if not user or user["role"] not in ADMIN_ROLES:
        await message.answer(
            "⛔ <b>Доступ запрещен.</b>\n"
            "Добавлять задачи могут только Председатель и 1-й заместитель.",
            parse_mode="HTML"
        )
        return

    await state.clear()
    await state.set_state(TaskCreationStates.waiting_for_text)
    await message.answer(
        "📝 <b>Шаг 1 из 3: Текст задачи</b>\n\n"
        "Опишите суть задачи, что именно необходимо сделать:",
        reply_markup=get_cancel_reply_keyboard(),
        parse_mode="HTML"
    )

@router.message(TaskCreationStates.waiting_for_text, F.text == "❌ Отмена")
@router.message(TaskCreationStates.waiting_for_deadline, F.text == "❌ Отмена")
async def cancel_task_flow(message: Message, state: FSMContext):
    """Отмена создания задачи на шаге ввода текста или дедлайна"""
    await state.clear()
    user = await db.get_user(message.from_user.id)
    is_admin = user["role"] in ADMIN_ROLES if user else False
    await message.answer(
        "❌ Создание задачи отменено.",
        reply_markup=get_main_menu_keyboard(is_admin)
    )

@router.message(TaskCreationStates.waiting_for_text)
async def process_task_text(message: Message, state: FSMContext):
    """Получение описания задачи"""
    text = message.text.strip()
    if len(text) < 3:
        await message.answer("⚠️ Описание задачи слишком короткое. Опишите подробнее:")
        return

    await state.update_data(task_text=text, selected_roles=[])
    await state.set_state(TaskCreationStates.waiting_for_roles)
    
    await message.answer(
        "👥 <b>Шаг 2 из 3: Для кого эта задача?</b>\n\n"
        "Отметьте нужные должности кнопками ниже (можно выбрать несколько).\n"
        "Или выберите <b>'ВСЕ'</b> для всей команды.\n\n"
        "После выбора нажмите зеленую кнопку <b>'Готово / Далее'</b>:",
        reply_markup=get_target_roles_keyboard([]),
        parse_mode="HTML"
    )

@router.callback_query(TaskCreationStates.waiting_for_roles, F.data == "task_create_cancel")
async def callback_cancel_roles(callback: CallbackQuery, state: FSMContext):
    """Отмена на этапе выбора ролей"""
    await state.clear()
    await callback.message.delete()
    user = await db.get_user(callback.from_user.id)
    is_admin = user["role"] in ADMIN_ROLES if user else False
    await callback.message.answer("❌ Создание задачи отменено.", reply_markup=get_main_menu_keyboard(is_admin))
    await callback.answer()

@router.callback_query(TaskCreationStates.waiting_for_roles, F.data.startswith("target_role:"))
async def toggle_target_role(callback: CallbackQuery, state: FSMContext):
    """Переключение чекбоксов должностей"""
    role_key = callback.data.split(":")[1]
    data = await state.get_data()
    selected_roles: list[str] = data.get("selected_roles", [])

    if role_key == "ALL":
        # Переключение режима ВСЕ
        if "ALL" in selected_roles:
            selected_roles = []
        else:
            selected_roles = ["ALL"]
    else:
        # Если было выбрано ВСЕ, сбрасываем и начинаем точечный выбор
        if "ALL" in selected_roles:
            selected_roles = []
        
        try:
            role_idx = int(role_key)
            role_name = ROLES[role_idx]
            if role_name in selected_roles:
                selected_roles.remove(role_name)
            else:
                selected_roles.append(role_name)
        except (ValueError, IndexError):
            await callback.answer("Ошибка выбора роли.")
            return

    await state.update_data(selected_roles=selected_roles)
    await callback.message.edit_reply_markup(reply_markup=get_target_roles_keyboard(selected_roles))
    await callback.answer()

@router.callback_query(TaskCreationStates.waiting_for_roles, F.data == "target_roles_confirm")
async def confirm_target_roles(callback: CallbackQuery, state: FSMContext):
    """Подтверждение выбора ролей"""
    data = await state.get_data()
    selected_roles = data.get("selected_roles", [])
    
    if not selected_roles:
        await callback.answer("⚠️ Выберите хотя бы одну должность или кнопку 'ВСЕ'!", show_alert=True)
        return

    await state.set_state(TaskCreationStates.waiting_for_deadline)
    await callback.message.delete()
    
    roles_display = "ВСЕ (Общий чат)" if "ALL" in selected_roles else ", ".join(selected_roles)

    await callback.message.answer(
        f"🎯 Выбрано: <b>{roles_display}</b>\n\n"
        "⏰ <b>Шаг 3 из 3: Дедлайн задачи</b>\n\n"
        "Введите дату и время дедлайна в формате:\n"
        "• <code>25.11.2026 18:00</code> (дата и время)\n"
        "• <code>25.11.2026</code> (дедлайн до конца дня 23:59)\n"
        "• <code>25.11 15:00</code> (текущий год)",
        reply_markup=get_cancel_reply_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()

@router.message(TaskCreationStates.waiting_for_deadline)
async def process_task_deadline(message: Message, state: FSMContext, bot: Bot):
    """Обработка дедлайна и сохранение задачи"""
    raw_date = message.text.strip()
    dt = parse_deadline(raw_date)
    
    if not dt:
        await message.answer(
            "⚠️ <b>Неверный формат даты.</b>\n"
            "Пожалуйста, введите дату в формате <code>ДД.ММ.ГГГГ ЧЧ:ММ</code>\n"
            "Например: <code>30.11.2026 19:00</code>",
            parse_mode="HTML"
        )
        return

    now = datetime.now()
    if dt <= now:
        await message.answer(
            "⚠️ <b>Дедлайн не может быть в прошлом!</b>\n"
            "Укажите будущую дату и время:",
            parse_mode="HTML"
        )
        return

    data = await state.get_data()
    task_text = data.get("task_text")
    selected_roles = data.get("selected_roles")
    
    creator_id = message.from_user.id
    creator = await db.get_user(creator_id)
    creator_name = f"{creator['first_name']} {creator['last_name']}" if creator else message.from_user.full_name
    creator_role = creator["role"] if creator else "Руководитель"

    deadline_iso = dt.strftime("%Y-%m-%d %H:%M:%S")
    deadline_display = dt.strftime("%d.%m.%Y в %H:%M")

    # Сохраняем задачу в SQLite
    task_id = await db.create_task(
        title=task_text,
        creator_id=creator_id,
        creator_name=f"{creator_name} ({creator_role})",
        target_roles=selected_roles,
        deadline_iso=deadline_iso
    )

    await state.clear()
    
    target_display = "⭐ ВСЕ СОТРУДНИКИ" if "ALL" in selected_roles else ", ".join(selected_roles)
    
    is_admin = creator["role"] in ADMIN_ROLES if creator else True
    await message.answer(
        f"✅ <b>Задача #{task_id} успешно создана!</b>\n\n"
        f"📝 <b>Задача:</b> {task_text}\n"
        f"👥 <b>Кому:</b> {target_display}\n"
        f"⏰ <b>Дедлайн:</b> {deadline_display}\n\n"
        f"🔔 Бот будет автоматически отправлять напоминания за 5, 3 и 1 день, а также при просрочке.",
        reply_markup=get_main_menu_keyboard(is_admin),
        parse_mode="HTML"
    )

    # Мгновенно оповещаем исполнителей о новой задаче
    await notify_new_task(bot, task_id, task_text, selected_roles, deadline_display, creator_name, creator_role)

async def notify_new_task(bot: Bot, task_id: int, text: str, target_roles: list[str], deadline_display: str, creator_name: str, creator_role: str):
    """Рассылка оповещения о создании новой задачи"""
    notification = (
        f"🆕 <b>НОВАЯ ЗАДАЧА #{task_id}</b>\n\n"
        f"📝 {text}\n\n"
        f"⏰ <b>Дедлайн:</b> {deadline_display}\n"
        f"👤 <b>Поставил:</b> {creator_name} ({creator_role})"
    )

    if "ALL" in target_roles:
        # Пытаемся отправить в общий чат
        chat_id_db = await db.get_setting("general_chat_id")
        target_chat_id = chat_id_db or GENERAL_CHAT_ID
        sent_to_group = False
        
        if target_chat_id:
            try:
                await bot.send_message(chat_id=int(target_chat_id), text=f"📢 <b>ВНИМАНИЕ ВСЕМ!</b>\n\n{notification}", parse_mode="HTML")
                sent_to_group = True
            except Exception as e:
                logger.warning(f"Не удалось отправить в общий чат {target_chat_id}: {e}")

        # Также отправляем всем зарегистрированным пользователям в ЛС
        users = await db.get_all_users()
        for u in users:
            try:
                await bot.send_message(chat_id=u["user_id"], text=f"📢 <b>ОБЩАЯ ЗАДАЧА ДЛЯ ВСЕХ</b>\n\n{notification}", parse_mode="HTML")
            except Exception as e:
                logger.debug(f"Не удалось отправить пользователю {u['user_id']}: {e}")
    else:
        # Отправляем в ЛС только людям с назначенными должностями
        users = await db.get_users_by_roles(target_roles)
        for u in users:
            try:
                await bot.send_message(chat_id=u["user_id"], text=notification, parse_mode="HTML")
            except Exception as e:
                logger.warning(f"Не удалось отправить уведомление пользователю {u['user_id']}: {e}")
