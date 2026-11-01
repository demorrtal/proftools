import os
import sys
import logging
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from config import (
    BOT_TOKEN,
    ROLES,
    ADMIN_ROLES,
    CLEANING_ROLES,
    WORKPLAN_URL,
    GENERAL_CHAT_ID,
    GENERAL_TOPIC_ID
)
import database as db
from scheduler import send_notification
from bot import bot

logger = logging.getLogger("webapp_api")

app = FastAPI(title="Telegram Task Mini App API")

# Разрешаем CORS для запросов из Telegram WebApp
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Папка со статикой веб-приложения
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEBAPP_DIR = os.path.join(BASE_DIR, "webapp")
os.makedirs(WEBAPP_DIR, exist_ok=True)

# --- Pydantic модели ---

class RegisterRequest(BaseModel):
    user_id: int
    first_name: str
    last_name: str
    group_number: str = ""
    username: str | None = None
    role: str

class CreateTaskRequest(BaseModel):
    creator_id: int
    title: str
    target_roles: list[str] | str
    deadline: str  # ISO string or parsed datetime string

class CompleteTaskRequest(BaseModel):
    user_id: int

class ExtendDeadlineRequest(BaseModel):
    user_id: int
    new_deadline: str

class CleaningDateRequest(BaseModel):
    user_id: int
    cleaning_date: str
    comment: str = ""

class RemoveMemberRequest(BaseModel):
    admin_id: int
    target_user_id: int

class SetActiveTopicRequest(BaseModel):
    user_id: int
    thread_id: str | int | None = None

# --- API Endpoints ---

@app.get("/api/me")
def get_current_user_profile(user_id: int = Query(...)):
    """Получение профиля пользователя и доступных ролей"""
    user = db.get_user(user_id)
    taken_roles = list(db.get_taken_roles(exclude_user_id=user_id if user else None))
    
    if not user:
        return {
            "registered": False,
            "roles": ROLES,
            "taken_roles": taken_roles
        }

    role = user["role"]
    is_admin = role in ADMIN_ROLES
    is_cleaning = role in CLEANING_ROLES

    return {
        "registered": True,
        "user": user,
        "is_admin": is_admin,
        "is_cleaning": is_cleaning,
        "roles": ROLES,
        "taken_roles": taken_roles
    }

@app.post("/api/register")
def register_user(data: RegisterRequest):
    """Регистрация сотрудника"""
    taken = db.get_taken_roles(exclude_user_id=data.user_id)
    if data.role in taken:
        raise HTTPException(status_code=400, detail=f"Должность '{data.role}' уже занята!")

    db.save_user(
        user_id=data.user_id,
        first_name=data.first_name.strip(),
        last_name=data.last_name.strip(),
        group_number=data.group_number.strip(),
        username=data.username,
        role=data.role
    )
    user = db.get_user(data.user_id)
    return {"success": True, "user": user}

@app.get("/api/tasks")
def get_tasks_list(user_id: int = Query(...), filter_type: str = Query("active")):
    """Получение списка задач (active, my, completed)"""
    user = db.get_user(user_id)
    user_role = user["role"] if user else ""

    if filter_type == "my" and user_role:
        tasks = db.get_user_tasks(user_role)
    elif filter_type == "completed":
        tasks = db.get_completed_tasks(limit=100)
    else:
        tasks = db.get_active_tasks()

    now = datetime.now()
    formatted = []
    for t in tasks:
        item = dict(t)
        # Рассчитываем статус и оставшееся время
        try:
            dl_dt = datetime.fromisoformat(item["deadline"])
            item["formatted_deadline"] = dl_dt.strftime("%d.%m.%Y в %H:%M")
            if item.get("status") == "completed":
                item["badge"] = "completed"
            elif dl_dt < now:
                item["badge"] = "overdue"
            else:
                diff = dl_dt - now
                if diff.days == 0:
                    item["badge"] = "today"
                else:
                    item["badge"] = f"{diff.days}д"
        except Exception:
            item["formatted_deadline"] = item["deadline"]
            item["badge"] = item.get("status", "active")

        # Приводим target_roles к списку
        target = item["target_roles"]
        if isinstance(target, list):
            item["target_roles_display"] = "ВСЕ" if ("ALL" in target or target == "ALL") else ", ".join(target)
        else:
            item["target_roles_display"] = "ВСЕ" if target == "ALL" else str(target)

        formatted.append(item)

    return {"tasks": formatted}

@app.post("/api/tasks")
def create_new_task(data: CreateTaskRequest):
    """Создание новой задачи Председателем"""
    creator = db.get_user(data.creator_id)
    if not creator or creator["role"] not in ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Только Председатель может создавать задачи!")

    creator_name = f"{creator['first_name']} {creator['last_name']}"
    creator_role = creator["role"]

    # Пробуем разобрать дедлайн
    try:
        dt = datetime.fromisoformat(data.deadline)
    except ValueError:
        raise HTTPException(status_code=400, detail="Неверный формат даты дедлайна!")

    if dt <= datetime.now():
        raise HTTPException(status_code=400, detail="Дедлайн не может быть в прошлом!")

    deadline_iso = dt.strftime("%Y-%m-%d %H:%M:%S")
    deadline_display = dt.strftime("%d.%m.%Y в %H:%M")

    task_id = db.create_task(
        title=data.title.strip(),
        creator_id=data.creator_id,
        creator_name=f"{creator_name} ({creator_role})",
        target_roles=data.target_roles,
        deadline_iso=deadline_iso
    )

    is_all = (data.target_roles == "ALL" or (isinstance(data.target_roles, list) and "ALL" in data.target_roles))
    target_display = "ВСЕ" if is_all else (", ".join(data.target_roles) if isinstance(data.target_roles, list) else data.target_roles)

    # Оповещение через Telegram
    notify_msg = (
        f"🆕 <b>НОВАЯ ЗАДАЧА</b>\n\n"
        f"📝 {data.title}\n\n"
        f"👥 <b>Кому:</b> {target_display}\n"
        f"⏰ <b>Дедлайн:</b> {deadline_display}\n"
        f"👤 <b>Поставил:</b> {creator_name} ({creator_role})"
    )
    send_notification(bot, data.target_roles, notify_msg)

    return {"success": True, "task_id": task_id}

@app.post("/api/tasks/{task_id}/complete")
def complete_task(task_id: int, data: CompleteTaskRequest):
    """Отметка задачи выполненной"""
    user = db.get_user(data.user_id)
    if not user or user["role"] not in ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Только Председатель может закрывать задачи!")

    task = db.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Задача не найдена")

    db.complete_task(task_id)

    done_msg = (
        f"✅ <b>ЗАДАЧА #{task_id} ВЫПОЛНЕНА!</b>\n\n"
        f"📝 {task['title']}\n\n"
        f"🎉 Председатель отметил задачу как успешно выполненную."
    )
    send_notification(bot, task["target_roles"], done_msg)
    return {"success": True}

@app.post("/api/tasks/{task_id}/extend")
def extend_task(task_id: int, data: ExtendDeadlineRequest):
    """Продление срока дедлайна"""
    user = db.get_user(data.user_id)
    if not user or user["role"] not in ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Только Председатель может продлевать дедлайн!")

    task = db.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Задача не найдена")

    try:
        new_dt = datetime.fromisoformat(data.new_deadline)
    except ValueError:
        raise HTTPException(status_code=400, detail="Неверный формат даты!")

    now = datetime.now()
    if new_dt <= now:
        raise HTTPException(status_code=400, detail="Новый дедлайн должен быть в будущем!")

    new_deadline_iso = new_dt.strftime("%Y-%m-%d %H:%M:%S")
    new_deadline_display = new_dt.strftime("%d.%m.%Y в %H:%M")

    delta = new_dt - now
    reset_reminders = {
        "reminded_5d": 0 if delta > timedelta(days=5) else 1,
        "reminded_3d": 0 if delta > timedelta(days=3) else 1,
        "reminded_1d": 0 if delta > timedelta(days=1) else 1,
        "reminded_overdue": 0
    }
    db.extend_task_deadline(task_id, new_deadline_iso, reset_reminders)

    extend_msg = (
        f"⏳ <b>ПРОДЛЕНИЕ ДЕДЛАЙНА ПО ЗАДАЧЕ #{task_id}</b>\n\n"
        f"📝 <b>Задача:</b> {task['title']}\n"
        f"⏰ <b>Новый дедлайн:</b> {new_deadline_display}\n"
        f"👤 <b>Продлил:</b> {user['first_name']} {user['last_name']} ({user['role']})"
    )
    send_notification(bot, task["target_roles"], extend_msg)
    return {"success": True}

@app.get("/api/cleaning")
def get_cleaning():
    """Получение графика уборки кабинета"""
    return {"dates": db.get_cleaning_schedule()}

@app.post("/api/cleaning")
def add_cleaning(data: CleaningDateRequest):
    """Добавление даты уборки (Председатель и Завхоз)"""
    user = db.get_user(data.user_id)
    if not user or user["role"] not in CLEANING_ROLES:
        raise HTTPException(status_code=403, detail="Доступно только Председателю и Завхозу!")

    cid = db.add_cleaning_date(data.cleaning_date.strip(), data.comment.strip())
    return {"success": True, "id": cid}

@app.delete("/api/cleaning/{item_id}")
def delete_cleaning(item_id: int, user_id: int = Query(...)):
    """Удаление даты уборки из графика"""
    user = db.get_user(user_id)
    if not user or user["role"] not in CLEANING_ROLES:
        raise HTTPException(status_code=403, detail="Доступно только Председателю и Завхозу!")

    db.delete_cleaning_date(item_id)
    return {"success": True}

@app.get("/api/team")
def get_team_members():
    """Список команды и свободных должностей"""
    users = db.get_all_users()
    taken_dict = {u["role"]: u for u in users}
    
    roster = []
    for r in ROLES:
        member = taken_dict.get(r)
        roster.append({
            "role": r,
            "occupied": member is not None,
            "user": member
        })
    return {"team": roster, "users": users}

@app.post("/api/team/remove")
def remove_team_member(data: RemoveMemberRequest):
    """Снятие сотрудника с должности (Председатель)"""
    admin = db.get_user(data.admin_id)
    if not admin or admin["role"] not in ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Только Председатель может снимать с должности!")

    target = db.get_user(data.target_user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Сотрудник не найден")

    db.delete_user(data.target_user_id)
    try:
        bot.send_message(
            data.target_user_id,
            f"ℹ️ Вы были сняты с должности <b>{target['role']}</b> Председателем команды."
        )
    except Exception:
        pass

    return {"success": True}

@app.get("/api/topics")
def get_topics_info():
    """Получение списка тем и активной темы"""
    topics = db.get_forum_topics()
    current_topic_id = db.get_setting("general_topic_id", "")
    chat_id = db.get_setting("general_chat_id", str(GENERAL_CHAT_ID or ""))
    return {
        "topics": topics,
        "active_topic_id": current_topic_id,
        "chat_id": chat_id
    }

@app.post("/api/topics/active")
def set_active_topic(data: SetActiveTopicRequest):
    """Смена активной темы форума для задач ВСЕ"""
    admin = db.get_user(data.user_id)
    if not admin or admin["role"] not in ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Только Председатель может настраивать тему!")

    val = str(data.thread_id) if data.thread_id and str(data.thread_id) != "none" else ""
    db.set_setting("general_topic_id", val)
    return {"success": True, "active_topic_id": val}

@app.get("/api/settings")
def get_general_settings():
    """Общие настройки и ссылки"""
    return {
        "workplan_url": WORKPLAN_URL,
        "chat_id": db.get_setting("general_chat_id", str(GENERAL_CHAT_ID or "")),
        "topic_id": db.get_setting("general_topic_id", "")
    }

# --- Статика веб-приложения ---

app.mount("/static", StaticFiles(directory=WEBAPP_DIR), name="static")

@app.api_route("/", methods=["GET", "HEAD"])
def serve_index_page():
    index_path = os.path.join(WEBAPP_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Telegram Task Mini App Server is running. UI not found."}
