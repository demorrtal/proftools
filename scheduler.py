import logging
import time
from datetime import datetime, timedelta
import database as db
from config import GENERAL_CHAT_ID, GENERAL_TOPIC_ID

logger = logging.getLogger(__name__)

def send_notification(bot, target_roles: list[str] | str, text: str):
    """Отправка уведомления: в общий чат/тему (если ВСЕ) или в ЛС по должностям"""
    is_all = (target_roles == "ALL" or "ALL" in target_roles)

    if is_all:
        chat_id_db = db.get_setting("general_chat_id")
        target_chat_id = chat_id_db or GENERAL_CHAT_ID

        if target_chat_id:
            topic_id_db = db.get_setting("general_topic_id")
            thread_id = None
            if topic_id_db is not None and str(topic_id_db).strip() != "":
                try:
                    thread_id = int(str(topic_id_db).strip())
                except ValueError:
                    thread_id = None
            elif GENERAL_TOPIC_ID:
                thread_id = GENERAL_TOPIC_ID

            try:
                bot.send_message(
                    chat_id=int(target_chat_id),
                    text=text,
                    parse_mode="HTML",
                    message_thread_id=thread_id
                )
            except Exception as e:
                logger.warning(f"Не удалось отправить в общий чат {target_chat_id} (тема {thread_id}): {e}")
                # Если отправка в топик завершилась ошибкой (например тема удалена), шлем в общий чат
                if thread_id is not None:
                    try:
                        bot.send_message(chat_id=int(target_chat_id), text=text, parse_mode="HTML")
                    except Exception as e2:
                        logger.warning(f"Повторная отправка в чат без темы также не удалась: {e2}")

        # Дублируем зарегистрированным пользователям в ЛС
        users = db.get_all_users()
        for u in users:
            try:
                bot.send_message(chat_id=u["user_id"], text=text, parse_mode="HTML")
            except Exception:
                pass
    else:
        roles_list = target_roles if isinstance(target_roles, list) else [target_roles]
        users = db.get_users_by_roles(roles_list)
        for u in users:
            try:
                bot.send_message(chat_id=u["user_id"], text=text, parse_mode="HTML")
            except Exception as e:
                logger.warning(f"Ошибка отправки ЛС пользователю {u['user_id']}: {e}")

def notify_chairmen(bot, text: str):
    """Оповещение Председателя о нарушении сроков"""
    chairmen = db.get_users_by_role("Председатель")
    for u in chairmen:
        try:
            bot.send_message(chat_id=u["user_id"], text=text, parse_mode="HTML")
        except Exception:
            pass

def check_deadlines(bot):
    """Проверка дедлайнов по всем активным задачам"""
    tasks = db.get_active_tasks()
    if not tasks:
        return

    now = datetime.now()

    for task in tasks:
        task_id = task["id"]
        title = task["title"]
        target = task["target_roles"]
        target_display = "ВСЕ" if ("ALL" in target or target == "ALL") else ", ".join(target)

        try:
            deadline_dt = datetime.fromisoformat(task["deadline"])
        except ValueError:
            continue

        delta = deadline_dt - now

        reminded_5d = task["reminded_5d"]
        reminded_3d = task["reminded_3d"]
        reminded_1d = task["reminded_1d"]
        reminded_overdue = task["reminded_overdue"]
        deadline_str = deadline_dt.strftime("%d.%m.%Y в %H:%M")

        # 1. Дедлайн пропущен (просрочка)
        if delta <= timedelta(seconds=0):
            if not reminded_overdue:
                logger.info(f"Задача #{task_id} просрочена! Рассылка оповещений.")
                
                # Исполнителям
                msg_assignees = (
                    f"🚨 <b>ВНИМАНИЕ! ДЕДЛАЙН ЗАДАЧИ ПРОПУЩЕН!</b>\n\n"
                    f"📌 <b>Задача #{task_id}:</b> {title}\n"
                    f"⏰ <b>Дедлайн истек:</b> {deadline_str}\n"
                    f"👤 <b>Поставил:</b> {task['creator_name']}\n\n"
                    f"⚠️ <i>Информация о пропуске дедлайна передана Председателю.</i>"
                )
                send_notification(bot, target, msg_assignees)

                # Председателю
                msg_chairman = (
                    f"🚨 <b>ОПОВЕЩЕНИЕ О ПРОСРОЧКЕ ЗАДАЧИ!</b>\n\n"
                    f"📌 <b>Задача #{task_id}:</b> {title}\n"
                    f"👥 <b>Ответственные:</b> {target_display}\n"
                    f"⏰ <b>Дедлайн был:</b> {deadline_str}\n"
                    f"👤 <b>Создал задачу:</b> {task['creator_name']}\n\n"
                    f"Вы можете проверить статус или продлить дедлайн через команду /tasks."
                )
                notify_chairmen(bot, msg_chairman)

                db.update_task_reminders(
                    task_id=task_id,
                    reminded_5d=1,
                    reminded_3d=1,
                    reminded_1d=1,
                    reminded_overdue=1,
                    status="overdue"
                )
            continue

        reminder_text = (
            f"⚠️ <b>НАПОМИНАНИЕ</b>\n\n"
            f"📌 <b>Задача #{task_id}:</b> {title}\n"
            f"⏰ <b>Дедлайн:</b> {deadline_str}\n"
            f"👥 <b>Назначено:</b> {target_display}\n"
            f"👤 <b>Поставил:</b> {task['creator_name']}"
        )

        # 2. Напоминание за 1 день
        if delta <= timedelta(days=1):
            if not reminded_1d:
                send_notification(bot, target, reminder_text)
                db.update_task_reminders(task_id, reminded_5d=1, reminded_3d=1, reminded_1d=1, reminded_overdue=0)
            continue

        # 3. Напоминание за 3 дня
        if delta <= timedelta(days=3):
            if not reminded_3d:
                send_notification(bot, target, reminder_text)
                db.update_task_reminders(task_id, reminded_5d=1, reminded_3d=1, reminded_1d=0, reminded_overdue=0)
            continue

        # 4. Напоминание за 5 дней
        if delta <= timedelta(days=5):
            if not reminded_5d:
                send_notification(bot, target, reminder_text)
                db.update_task_reminders(task_id, reminded_5d=1, reminded_3d=0, reminded_1d=0, reminded_overdue=0)

def start_scheduler_thread(bot):
    """Запуск фонового потока проверки дедлайнов (каждые 45 секунд)"""
    import threading
    def loop():
        logger.info("Фоновый поток контроля дедлайнов запущен.")
        while True:
            try:
                check_deadlines(bot)
            except Exception as e:
                logger.error(f"Ошибка в цикле проверки дедлайнов: {e}", exc_info=True)
            time.sleep(45)

    thread = threading.Thread(target=loop, daemon=True)
    thread.start()
    return thread
