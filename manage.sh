#!/usr/bin/env bash

# ========================================================
# Утилита управления Telegram-ботом на Ubuntu
# ========================================================

SERVICE_NAME="telegram-bot.service"

case "$1" in
    status)
        sudo systemctl status $SERVICE_NAME
        ;;
    logs)
        sudo journalctl -u $SERVICE_NAME -f -n 50
        ;;
    restart)
        echo "Перезапуск бота..."
        sudo systemctl restart $SERVICE_NAME
        echo "Готово. Статус:"
        sudo systemctl status $SERVICE_NAME --no-pager
        ;;
    stop)
        echo "Остановка бота..."
        sudo systemctl stop $SERVICE_NAME
        echo "Бот остановлен."
        ;;
    start)
        echo "Запуск бота..."
        sudo systemctl start $SERVICE_NAME
        echo "Готово. Статус:"
        sudo systemctl status $SERVICE_NAME --no-pager
        ;;
    update)
        echo "Обновление зависимостей..."
        APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
        "$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt" --upgrade
        sudo systemctl restart $SERVICE_NAME
        echo "Обновление завершено и бот перезапущен."
        ;;
    *)
        echo "Использование: ./manage.sh {status|logs|restart|stop|start|update}"
        echo ""
        echo "  status  - показать текущее состояние бота"
        echo "  logs    - просмотр логов в реальном времени"
        echo "  restart - перезапустить бота"
        echo "  stop    - остановить бота"
        echo "  start   - запустить бота"
        echo "  update  - обновить библиотеки и перезапустить"
        exit 1
        ;;
esac
