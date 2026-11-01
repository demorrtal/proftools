import os
import sqlite3
import json
import logging
from datetime import datetime
from config import DATABASE_PATH

logger = logging.getLogger(__name__)

def get_connection():
    """Создание соединения с базой данных SQLite"""
    db_dir = os.path.dirname(DATABASE_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Инициализация таблиц базы данных SQLite"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA busy_timeout=5000;")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                first_name TEXT NOT NULL,
                last_name TEXT NOT NULL,
                group_number TEXT,
                username TEXT,
                role TEXT NOT NULL,
                registered_at TEXT NOT NULL
            )
        """)

        # Автоматическая миграция: проверка наличия колонки group_number
        cursor.execute("PRAGMA table_info(users)")
        columns = [row["name"] for row in cursor.fetchall()]
        if "group_number" not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN group_number TEXT")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                creator_id INTEGER NOT NULL,
                creator_name TEXT NOT NULL,
                target_roles TEXT NOT NULL,
                deadline TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                reminded_5d INTEGER NOT NULL DEFAULT 0,
                reminded_3d INTEGER NOT NULL DEFAULT 0,
                reminded_1d INTEGER NOT NULL DEFAULT 0,
                reminded_overdue INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cleaning_schedule (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cleaning_date TEXT NOT NULL,
                comment TEXT,
                created_at TEXT NOT NULL
            )
        """)
        conn.commit()
    logger.info("База данных SQLite успешно инициализирована.")

# --- Пользователи ---

def get_user(user_id: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def save_user(user_id: int, first_name: str, last_name: str, group_number: str, username: str | None, role: str):
    now = datetime.now().isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO users (user_id, first_name, last_name, group_number, username, role, registered_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                first_name=excluded.first_name,
                last_name=excluded.last_name,
                group_number=excluded.group_number,
                username=excluded.username,
                role=excluded.role
        """, (user_id, first_name, last_name, group_number, username, role, now))
        conn.commit()

def get_taken_roles(exclude_user_id: int | None = None) -> set[str]:
    """Получить множество уже занятых должностей"""
    with get_connection() as conn:
        cursor = conn.cursor()
        if exclude_user_id:
            cursor.execute("SELECT role FROM users WHERE user_id != ?", (exclude_user_id,))
        else:
            cursor.execute("SELECT role FROM users")
        rows = cursor.fetchall()
        return {row["role"] for row in rows}

def get_users_by_role(role: str):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE role = ?", (role,))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

def get_users_by_roles(roles: list[str]):
    if not roles:
        return []
    placeholders = ",".join("?" for _ in roles)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM users WHERE role IN ({placeholders})", roles)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

def get_all_users():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users ORDER BY registered_at ASC")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

def delete_user(user_id: int):
    """Удаление пользователя из базы данных (снятие с должности)"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
        conn.commit()

# --- Задачи ---

def create_task(title: str, creator_id: int, creator_name: str, target_roles: list[str] | str, deadline_iso: str) -> int:
    now = datetime.now().isoformat()
    target_json = json.dumps(target_roles, ensure_ascii=False)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO tasks (title, creator_id, creator_name, target_roles, deadline, status, created_at)
            VALUES (?, ?, ?, ?, ?, 'active', ?)
        """, (title, creator_id, creator_name, target_json, deadline_iso, now))
        conn.commit()
        return cursor.lastrowid

def get_task(task_id: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        row = cursor.fetchone()
        if not row:
            return None
        data = dict(row)
        data["target_roles"] = json.loads(data["target_roles"])
        return data

def get_active_tasks():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM tasks 
            WHERE status != 'completed' 
            ORDER BY deadline ASC
        """)
        rows = cursor.fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["target_roles"] = json.loads(item["target_roles"])
            result.append(item)
        return result

def get_user_tasks(role: str):
    """Получить активные задачи, назначенные конкретной роли или ВСЕМ"""
    all_active = get_active_tasks()
    user_tasks = []
    for t in all_active:
        target = t["target_roles"]
        if target == "ALL" or "ALL" in target or role in target:
            user_tasks.append(t)
    return user_tasks

def get_completed_tasks(limit: int = 50):
    """Получить список выполненных задач"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM tasks 
            WHERE status = 'completed' 
            ORDER BY id DESC LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["target_roles"] = json.loads(item["target_roles"])
            result.append(item)
        return result

def complete_task(task_id: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE tasks SET status = 'completed' WHERE id = ?", (task_id,))
        conn.commit()

def extend_task_deadline(task_id: int, new_deadline_iso: str, reset_reminders: dict):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE tasks 
            SET deadline = ?,
                status = 'active',
                reminded_5d = ?,
                reminded_3d = ?,
                reminded_1d = ?,
                reminded_overdue = ?
            WHERE id = ?
        """, (
            new_deadline_iso,
            reset_reminders.get("reminded_5d", 0),
            reset_reminders.get("reminded_3d", 0),
            reset_reminders.get("reminded_1d", 0),
            reset_reminders.get("reminded_overdue", 0),
            task_id
        ))
        conn.commit()

def update_task_reminders(task_id: int, reminded_5d: int, reminded_3d: int, reminded_1d: int, reminded_overdue: int, status: str = None):
    with get_connection() as conn:
        cursor = conn.cursor()
        if status:
            cursor.execute("""
                UPDATE tasks 
                SET reminded_5d = ?, reminded_3d = ?, reminded_1d = ?, reminded_overdue = ?, status = ?
                WHERE id = ?
            """, (reminded_5d, reminded_3d, reminded_1d, reminded_overdue, status, task_id))
        else:
            cursor.execute("""
                UPDATE tasks 
                SET reminded_5d = ?, reminded_3d = ?, reminded_1d = ?, reminded_overdue = ?
                WHERE id = ?
            """, (reminded_5d, reminded_3d, reminded_1d, reminded_overdue, task_id))
        conn.commit()

# --- Настройки ---

def set_setting(key: str, value: str):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """, (key, value))
        conn.commit()

def get_setting(key: str, default: str | None = None):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row[0] if row else default

# --- График уборки кабинета ---

def add_cleaning_date(cleaning_date: str, comment: str = "") -> int:
    """Добавить дату уборки в график"""
    now = datetime.now().isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO cleaning_schedule (cleaning_date, comment, created_at)
            VALUES (?, ?, ?)
        """, (cleaning_date, comment, now))
        conn.commit()
        return cursor.lastrowid

def get_cleaning_schedule():
    """Получить все запланированные даты уборки"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM cleaning_schedule ORDER BY id ASC")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

def delete_cleaning_date(schedule_id: int):
    """Удалить дату уборки из графика"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM cleaning_schedule WHERE id = ?", (schedule_id,))
        conn.commit()
