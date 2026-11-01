import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.filters import CommandStart, Command

from config import ROLES, ADMIN_ROLES
import database as db
from keyboards import (
    get_main_menu_keyboard,
    get_registration_roles_keyboard,
    get_cancel_reply_keyboard
)

logger = logging.getLogger(__name__)
router = Router()

class RegistrationStates(StatesGroup):
    waiting_for_first_name = State()
    waiting_for_last_name = State()
    waiting_for_role = State()

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """Обработчик команды /start"""
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    
    if user:
        is_admin = user["role"] in ADMIN_ROLES
        await state.clear()
        admin_notice = "\n👑 У вас есть права председателя / заместителя по управлению задачами." if is_admin else ""
        await message.answer(
            f"👋 С возвращением, <b>{user['first_name']} {user['last_name']}</b>!\n"
            f"💼 Ваша должность: <b>{user['role']}</b>\n"
            f"🔗 Юзернейм: @{user['username'] or 'не указан'}{admin_notice}\n\n"
            f"Используйте кнопки меню внизу для работы с ботом.",
            reply_markup=get_main_menu_keyboard(is_admin),
            parse_mode="HTML"
        )
        return

    await state.clear()
    await state.set_state(RegistrationStates.waiting_for_first_name)
    await message.answer(
        "👋 <b>Добро пожаловать в бота управления задачами!</b>\n\n"
        "Для начала работы необходимо зарегистрироваться в базе команды.\n"
        "Пожалуйста, введите ваше <b>имя</b>:",
        reply_markup=get_cancel_reply_keyboard(),
        parse_mode="HTML"
    )

@router.message(Command("reregister"))
async def cmd_reregister(message: Message, state: FSMContext):
    """Повторная регистрация или изменение должности"""
    await state.clear()
    await state.set_state(RegistrationStates.waiting_for_first_name)
    await message.answer(
        "🔄 <b>Перерегистрация профиля</b>\n\n"
        "Введите ваше <b>имя</b>:",
        reply_markup=get_cancel_reply_keyboard(),
        parse_mode="HTML"
    )

@router.message(RegistrationStates.waiting_for_first_name, F.text == "❌ Отмена")
@router.message(RegistrationStates.waiting_for_last_name, F.text == "❌ Отмена")
async def cancel_registration(message: Message, state: FSMContext):
    """Отмена регистрации"""
    await state.clear()
    user = await db.get_user(message.from_user.id)
    is_admin = user["role"] in ADMIN_ROLES if user else False
    await message.answer(
        "Ввод данных отменен.",
        reply_markup=get_main_menu_keyboard(is_admin)
    )

@router.message(RegistrationStates.waiting_for_first_name)
async def process_first_name(message: Message, state: FSMContext):
    """Шаг 1: Получение имени"""
    name = message.text.strip()
    if len(name) < 2 or len(name) > 40:
        await message.answer("⚠️ Имя должно содержать от 2 до 40 символов. Попробуйте еще раз:")
        return

    await state.update_data(first_name=name)
    await state.set_state(RegistrationStates.waiting_for_last_name)
    await message.answer(
        f"Принято, {name}!\nТеперь введите вашу <b>фамилию</b>:",
        reply_markup=get_cancel_reply_keyboard(),
        parse_mode="HTML"
    )

@router.message(RegistrationStates.waiting_for_last_name)
async def process_last_name(message: Message, state: FSMContext):
    """Шаг 2: Получение фамилии"""
    last_name = message.text.strip()
    if len(last_name) < 2 or len(last_name) > 40:
        await message.answer("⚠️ Фамилия должна содержать от 2 до 40 символов. Попробуйте еще раз:")
        return

    await state.update_data(last_name=last_name)
    await state.set_state(RegistrationStates.waiting_for_role)
    await message.answer(
        "Отлично! Теперь выберите вашу <b>должность</b> из списка ниже:",
        reply_markup=get_registration_roles_keyboard(),
        parse_mode="HTML"
    )

@router.callback_query(RegistrationStates.waiting_for_role, F.data.startswith("reg_role:"))
async def process_role_selection(callback: CallbackQuery, state: FSMContext):
    """Шаг 3: Выбор должности из 11 вариантов и сохранение в базу"""
    try:
        role_idx = int(callback.data.split(":")[1])
        selected_role = ROLES[role_idx]
    except (IndexError, ValueError):
        await callback.answer("Ошибка при выборе роли. Попробуйте снова.", show_alert=True)
        return

    data = await state.get_data()
    first_name = data.get("first_name", "")
    last_name = data.get("last_name", "")
    username = callback.from_user.username
    user_id = callback.from_user.id

    # Сохраняем в SQLite
    await db.save_user(
        user_id=user_id,
        first_name=first_name,
        last_name=last_name,
        username=username,
        role=selected_role
    )

    await state.clear()
    await callback.message.delete()

    is_admin = selected_role in ADMIN_ROLES
    role_perks = "\n👑 <b>Вам доступны функции создания и контроля задач!</b>" if is_admin else ""

    await callback.message.answer(
        f"🎉 <b>Регистрация успешно завершена!</b>\n\n"
        f"👤 <b>ФИО:</b> {first_name} {last_name}\n"
        f"💼 <b>Должность:</b> {selected_role}\n"
        f"🔗 <b>Telegram:</b> @{username or 'нет'}\n"
        f"{role_perks}\n\n"
        f"Бот будет напоминать вам о дедлайнах за 5, 3 и 1 день, а также в случае просрочки.",
        reply_markup=get_main_menu_keyboard(is_admin),
        parse_mode="HTML"
    )
    await callback.answer("Вы успешно зарегистрированы!")
