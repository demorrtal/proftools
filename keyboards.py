from telebot import types
from config import ROLES, LEADERSHIP_ROLES

def get_main_menu(is_admin: bool = False, role: str = "") -> types.ReplyKeyboardMarkup:
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    can_lead = is_admin or (role in LEADERSHIP_ROLES)
    if is_admin:
        markup.row(types.KeyboardButton("➕ Новая задача"), types.KeyboardButton("📋 Список задач"))
        markup.row(types.KeyboardButton("📢 Собрание"), types.KeyboardButton("📌 Мои задачи"))
        markup.row(types.KeyboardButton("✅ Выполненные задачи"), types.KeyboardButton("🧹 График уборки"))
        markup.row(types.KeyboardButton("📊 План работы профбюро"), types.KeyboardButton("👤 Мой профиль"))
        markup.row(types.KeyboardButton("👥 Список команды"), types.KeyboardButton("🗑️ Снять с должности"))
        markup.row(types.KeyboardButton("📌 Тема в группе (ВСЕ)"), types.KeyboardButton("➕ Добавить в группу"))
    elif can_lead:
        markup.row(types.KeyboardButton("📢 Собрание"), types.KeyboardButton("📌 Мои задачи"))
        markup.row(types.KeyboardButton("🧹 График уборки"), types.KeyboardButton("📊 План работы профбюро"))
        markup.row(types.KeyboardButton("👤 Мой профиль"), types.KeyboardButton("👥 Список команды"))
    else:
        markup.row(types.KeyboardButton("📌 Мои задачи"))
        markup.row(types.KeyboardButton("🧹 График уборки"), types.KeyboardButton("📊 План работы профбюро"))
        markup.row(types.KeyboardButton("👤 Мой профиль"), types.KeyboardButton("👥 Список команды"))
    markup.row(types.KeyboardButton("❓ Помощь"))
    return markup

def get_cancel_keyboard() -> types.ReplyKeyboardMarkup:
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add(types.KeyboardButton("❌ Отмена"))
    return markup

def get_registration_roles_keyboard(taken_roles: set[str] | list[str] | None = None) -> types.InlineKeyboardMarkup:
    """Клавиатура для выбора свободной должности при регистрации (занятые должности скрываются)"""
    taken = set(taken_roles) if taken_roles else set()
    markup = types.InlineKeyboardMarkup(row_width=1)
    for idx, role in enumerate(ROLES):
        if role in taken:
            continue
        markup.add(types.InlineKeyboardButton(text=role, callback_data=f"reg_role:{idx}"))
    return markup

def get_target_roles_keyboard(selected_roles: list[str] | str) -> types.InlineKeyboardMarkup:
    is_all = (selected_roles == "ALL" or "ALL" in selected_roles)
    markup = types.InlineKeyboardMarkup(row_width=1)
    
    # Кнопка ВСЕ
    all_icon = "⭐" if is_all else "👥"
    all_text = f"{all_icon} ВСЕ"
    markup.add(types.InlineKeyboardButton(text=all_text, callback_data="target:ALL"))

    # Каждая из 11 должностей
    for idx, role in enumerate(ROLES):
        if is_all:
            mark = "✅"
        else:
            checked = role in selected_roles
            mark = "✅" if checked else "◻️"
        button_text = f"{mark} {role}"
        markup.add(types.InlineKeyboardButton(text=button_text, callback_data=f"target:{idx}"))

    # Кнопки подтверждения и отмены
    markup.row(
        types.InlineKeyboardButton(text="✅ Готово / Далее", callback_data="target:DONE"),
        types.InlineKeyboardButton(text="❌ Отмена", callback_data="target:CANCEL")
    )
    return markup

def get_task_actions_keyboard(task_id: int) -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton(text="✅ Выполнено", callback_data=f"done:{task_id}"),
        types.InlineKeyboardButton(text="⏳ Продлить дедлайн", callback_data=f"extend:{task_id}")
    )
    return markup

def get_remove_user_keyboard(users: list, current_user_id: int) -> types.InlineKeyboardMarkup:
    """Клавиатура для выбора сотрудника для снятия с должности"""
    markup = types.InlineKeyboardMarkup(row_width=1)
    for u in users:
        if u["user_id"] == current_user_id:
            continue
        uname = f" (@{u['username']})" if u.get("username") else ""
        btn_text = f"❌ {u['first_name']} {u['last_name']} — {u['role']}{uname}"
        markup.add(types.InlineKeyboardButton(text=btn_text, callback_data=f"rm_usr:{u['user_id']}"))
    markup.add(types.InlineKeyboardButton(text="Отмена", callback_data="rm_cancel"))
    return markup

def get_confirm_remove_keyboard(user_id: int) -> types.InlineKeyboardMarkup:
    """Подтверждение снятия с должности"""
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton(text="🗑️ Да, снять", callback_data=f"conf_rm:{user_id}"),
        types.InlineKeyboardButton(text="❌ Отмена", callback_data="rm_cancel")
    )
    return markup

def get_add_to_group_keyboard(bot_username: str) -> types.InlineKeyboardMarkup:
    """Кнопка прямого добавления бота в группу"""
    markup = types.InlineKeyboardMarkup()
    url = f"https://t.me/{bot_username}?startgroup=true"
    markup.add(types.InlineKeyboardButton(text="➕ Выбрать группу для бота", url=url))
    return markup

def get_workplan_keyboard() -> types.InlineKeyboardMarkup:
    """Кнопка-ссылка на Google Таблицу плана работы профбюро"""
    markup = types.InlineKeyboardMarkup()
    url = "https://docs.google.com/spreadsheets/d/1tS4d_nbAoP4bjHVnFgZBJu2ddpYKa7es_PRqyUODJgU/edit?usp=drive_link"
    markup.add(types.InlineKeyboardButton(text="📄 Открыть план работы (Google Таблица)", url=url))
    return markup

def get_cleaning_menu_keyboard(can_manage: bool = False, has_dates: bool = False) -> types.InlineKeyboardMarkup | None:
    """Кнопки управления графиком уборки для Председателя и Завхоза"""
    if not can_manage:
        return None
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton(text="➕ Добавить дату уборки", callback_data="clean:add"))
    if has_dates:
        markup.add(types.InlineKeyboardButton(text="🗑️ Удалить дату из графика", callback_data="clean:del_menu"))
    return markup

def get_delete_cleaning_keyboard(dates: list) -> types.InlineKeyboardMarkup:
    """Список дат уборки для удаления"""
    markup = types.InlineKeyboardMarkup(row_width=1)
    for d in dates:
        comment_part = f" ({d['comment']})" if d.get("comment") else ""
        btn_text = f"❌ {d['cleaning_date']}{comment_part}"
        markup.add(types.InlineKeyboardButton(text=btn_text, callback_data=f"clean:del:{d['id']}"))
    markup.add(types.InlineKeyboardButton(text="Отмена", callback_data="clean:cancel"))
    return markup

def get_topics_keyboard(topics: list[dict], current_topic_id: str | int | None = None) -> types.InlineKeyboardMarkup:
    """Клавиатура выбора активной темы для задач ВСЕ"""
    markup = types.InlineKeyboardMarkup(row_width=1)
    cur_id_str = str(current_topic_id).strip() if current_topic_id is not None and str(current_topic_id).strip() != "" else None

    # Кнопка для Основного чата (без темы)
    is_general_active = cur_id_str is None
    gen_mark = "✅ " if is_general_active else "◻️ "
    markup.add(types.InlineKeyboardButton(
        text=f"{gen_mark}💬 Основной чат / без темы",
        callback_data="set_active_topic:none"
    ))

    # Кнопки для каждой темы
    for t in topics:
        tid_str = str(t["thread_id"])
        is_active = (tid_str == cur_id_str)
        mark = "✅ " if is_active else "◻️ "
        markup.add(types.InlineKeyboardButton(
            text=f"{mark}📌 {t['title']} (ID: {t['thread_id']})",
            callback_data=f"set_active_topic:{t['thread_id']}"
        ))

    markup.add(types.InlineKeyboardButton(text="ℹ️ Как добавить новую тему", callback_data="topic:help"))
    return markup
