#!/usr/bin/env bash
set -e

# ========================================================
# Скрипт автоматической установки и запуска Telegram-бота
# для операционной системы Ubuntu 24.04 LTS (Noble Numbat)
# ========================================================

echo "========================================================"
echo "   Установка и запуск Telegram-бота на Ubuntu 24.04"
echo "========================================================"

# 1. Проверка прав суперпользователя (root)
if [ "$EUID" -ne 0 ]; then
    echo "❌ Ошибка: этот скрипт необходимо запускать с правами sudo!"
    echo "Используйте: sudo bash install_ubuntu24.sh"
    exit 1
fi

# Определение рабочей папки и пользователя
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ACTUAL_USER="${SUDO_USER:-$USER}"

echo "📁 Рабочая директория: $APP_DIR"
echo "👤 Пользователь службы: $ACTUAL_USER"
echo ""

# 2. Обновление пакетов и установка зависимостей Ubuntu 24
echo "🔄 [1/5] Установка системных пакетов (Python 3.12, venv, pip, curl, git)..."
export DEBIAN_FRONTEND=noninteractive
apt update -y
apt install -y python3 python3-venv python3-pip curl tzdata git

# Настройка git safe.directory для исключения конфликтов прав
git config --global --add safe.directory "$APP_DIR" 2>/dev/null || true

# Настройка таймзоны (по умолчанию Europe/Moscow)
if [ ! -f /etc/timezone ] || ! grep -q "Europe/Moscow" /etc/timezone; then
    echo "⏰ Настройка часового пояса Europe/Moscow..."
    ln -snf /usr/share/zoneinfo/Europe/Moscow /etc/localtime
    echo "Europe/Moscow" > /etc/timezone
fi

# 3. Создание изолированного виртуального окружения (PEP 668 compliant)
echo ""
echo "🐍 [2/5] Настройка виртуального окружения Python..."
cd "$APP_DIR"

if [ ! -d "$APP_DIR/venv" ]; then
    python3 -m venv "$APP_DIR/venv"
    echo "✅ Окружение venv создано."
else
    echo "ℹ️  Виртуальное окружение venv уже существует."
fi

# Обновление pip и установка зависимостей
echo "📦 Установка библиотек pyTelegramBotAPI и python-dotenv..."
"$APP_DIR/venv/bin/pip" install --upgrade pip --quiet
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"

# 4. Проверка файла конфигурации .env
echo ""
echo "⚙️  [3/5] Проверка файла конфигурации .env..."
if [ ! -f "$APP_DIR/.env" ]; then
    if [ -f "$APP_DIR/.env.example" ]; then
        cp "$APP_DIR/.env.example" "$APP_DIR/.env"
        echo "⚠️  Создан файл .env из примера .env.example."
    else
        touch "$APP_DIR/.env"
    fi
fi

# Проверка токена
if ! grep -q "BOT_TOKEN=" "$APP_DIR/.env" || grep -q "BOT_TOKEN=1234567890:ABCdef" "$APP_DIR/.env" || grep -q "BOT_TOKEN=$" "$APP_DIR/.env"; then
    echo ""
    echo "⚠️  Внимание: BOT_TOKEN не задан или содержит тестовое значение!"
    read -p "👉 Введите ваш токен Telegram-бота (от @BotFather): " input_token
    input_token="$(echo -e "${input_token}" | tr -d '[:space:]')"
    if [ -n "$input_token" ]; then
        if grep -q "BOT_TOKEN=" "$APP_DIR/.env"; then
            sed -i "s|^BOT_TOKEN=.*|BOT_TOKEN=$input_token|" "$APP_DIR/.env"
        else
            echo "BOT_TOKEN=$input_token" >> "$APP_DIR/.env"
        fi
        echo "✅ Токен сохранен в .env"
    else
        echo "❌ Токен не введен. Обязательно добавьте его вручную в $APP_DIR/.env перед запуском!"
    fi
fi

# Выставляем права на файлы пользователю
chown -R "$ACTUAL_USER:$ACTUAL_USER" "$APP_DIR"
chmod -R 755 "$APP_DIR"

# 5. Создание systemd службы
echo ""
echo "🚀 [4/5] Настройка системной службы systemd..."

SERVICE_FILE="/etc/systemd/system/telegram-bot.service"

cat <<EOF > "$SERVICE_FILE"
[Unit]
Description=Telegram Task Manager Bot
After=network.target network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$ACTUAL_USER
Group=$ACTUAL_USER
WorkingDirectory=$APP_DIR
Environment="PYTHONUNBUFFERED=1"
Environment="TZ=Europe/Moscow"
ExecStart=$APP_DIR/venv/bin/python $APP_DIR/run.py
Restart=always
RestartSec=5
TimeoutStopSec=10
KillMode=mixed

[Install]
WantedBy=multi-user.target
EOF

# 6. Активация и запуск службы
echo ""
echo "🔄 [5/5] Запуск и включение автозагрузки бота..."
systemctl daemon-reload
systemctl enable telegram-bot.service
systemctl restart telegram-bot.service

sleep 2

# Проверка статуса
if systemctl is-active --quiet telegram-bot.service; then
    echo ""
    echo "========================================================"
    echo "🎉 ПОЗДРАВЛЯЕМ! Бот успешно запущен и работает в фоне!"
    echo "========================================================"
    echo ""
    echo "📌 Полезные команды для управления ботом:"
    echo "   Проверить статус:  sudo systemctl status telegram-bot"
    echo "   Смотреть логи:     sudo journalctl -u telegram-bot -f"
    echo "   Перезапустить:     sudo systemctl restart telegram-bot"
    echo "   Остановить:        sudo systemctl stop telegram-bot"
    echo "   Запустить:         sudo systemctl start telegram-bot"
    echo ""
    echo "Либо используйте удобную утилиту: ./manage.sh [status|logs|restart|stop|start]"
    echo "========================================================"
else
    echo ""
    echo "❌ Ошибка: служба не смогла запуститься. Смотрите последние логи:"
    journalctl -u telegram-bot -n 20 --no-pager
fi
