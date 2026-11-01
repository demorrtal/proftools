#!/usr/bin/env bash

# ========================================================
# Утилита управления Telegram-ботом на Ubuntu 24.04
# Репозиторий: https://github.com/demorrtal/proftools
# ========================================================

SERVICE_NAME="telegram-bot.service"
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

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
        echo "🔄 Загрузка обновлений из https://github.com/demorrtal/proftools..."
        cd "$APP_DIR"
        if [ -d ".git" ]; then
            git pull origin main || git pull
        else
            echo "⚠️  Каталог не является git-репозиторием. Пропускаем git pull."
        fi
        echo "📦 Проверка зависимостей Python..."
        "$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt" --upgrade
        echo "🚀 Перезапуск службы $SERVICE_NAME..."
        sudo systemctl restart $SERVICE_NAME
        echo "✅ Обновление успешно завершено!"
        ;;
    *)
        echo "Использование: ./manage.sh {status|logs|restart|stop|start|update}"
        echo ""
        echo "  status  - показать текущее состояние службы"
        echo "  logs    - просмотр логов в реальном времени"
        echo "  restart - перезапустить бота"
        echo "  stop    - остановить бота"
        echo "  start   - запустить бота"
        echo "  update  - скачать обновления из GitHub (git pull) и перезапустить бота"
        exit 1
        ;;
esac
