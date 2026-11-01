#!/usr/bin/env bash
set -e

# ========================================================
# Скрипт автоматической настройки Nginx + SSL (Certbot)
# для Telegram Mini App на Ubuntu 24.04 LTS
# ========================================================

echo "========================================================"
echo "    Настройка Nginx + HTTPS для Telegram Mini App      "
echo "========================================================"

if [ "$EUID" -ne 0 ]; then
    echo "❌ Ошибка: запустите скрипт с правами sudo:"
    echo "sudo bash setup_nginx.sh"
    exit 1
fi

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 1. Запрос доменного имени
echo ""
read -p "👉 Введите ваш домен (например, bot.mydomain.ru или mybot.duckdns.org): " DOMAIN
DOMAIN="$(echo "$DOMAIN" | tr -d '[:space:]')"

if [ -z "$DOMAIN" ]; then
    echo "❌ Ошибка: домен не введен. Настройка отменена."
    exit 1
fi

echo "🌐 Настраиваем домен: $DOMAIN"
echo ""

# 2. Установка Nginx и Certbot
echo "🔄 [1/4] Установка Nginx и Certbot..."
apt update -y
apt install -y nginx certbot python3-certbot-nginx

# Открываем порты 80 и 443 в UFW (если фаервол включен)
if ufw status | grep -q "Status: active"; then
    echo "🛡️ Настройка фаервола UFW (открытие портов 80 и 443)..."
    ufw allow 'Nginx Full'
fi

# 3. Создание конфигурации сайта в Nginx
echo ""
echo "📝 [2/4] Создание конфигурации Nginx..."
CONF_PATH="/etc/nginx/sites-available/proftools"

cat <<EOF > "$CONF_PATH"
server {
    listen 80;
    server_name $DOMAIN;

    client_max_body_size 20M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;

        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
}
EOF

# Активация конфигурации
ln -sf "$CONF_PATH" /etc/nginx/sites-enabled/proftools

# Удаляем default сайт, если он конфликтует
rm -f /etc/nginx/sites-enabled/default

# Проверка синтаксиса
echo "🔍 Проверка конфигурации Nginx..."
nginx -t
systemctl restart nginx

# 4. Выпуск бесплатного SSL-сертификата (HTTPS)
echo ""
echo "🔒 [3/4] Выпуск бесплатного SSL-сертификата Let's Encrypt через Certbot..."
echo "Certbot автоматически настроит HTTPS и редирект с HTTP."
echo ""

certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --register-unsafely-without-email || {
    echo "⚠️ Автоматический выпуск завершился с предупреждением."
    echo "Если нужно ввести email вручную, выполните: sudo certbot --nginx -d $DOMAIN"
}

# 5. Обновление .env файла бота
echo ""
echo "⚙️  [4/4] Обновление WEBAPP_URL в файле .env..."
ENV_FILE="$APP_DIR/.env"

if [ -f "$ENV_FILE" ]; then
    HTTPS_URL="https://$DOMAIN"
    if grep -q "WEBAPP_URL=" "$ENV_FILE"; then
        sed -i "s|^WEBAPP_URL=.*|WEBAPP_URL=$HTTPS_URL|" "$ENV_FILE"
    else
        echo "WEBAPP_URL=$HTTPS_URL" >> "$ENV_FILE"
    fi
    echo "✅ В .env установлен: WEBAPP_URL=$HTTPS_URL"

    # Перезапускаем бота, чтобы он привязал кнопку WebApp
    if systemctl is-active --quiet telegram-bot.service; then
        echo "🔄 Перезапуск службы telegram-bot..."
        systemctl restart telegram-bot.service
    fi
fi

echo ""
echo "========================================================"
echo "🎉 НАСТРОЙКА УСПЕШНО ЗАВЕРШЕНА!"
echo "========================================================"
echo "🌐 Ваше приложение доступно по адресу: https://$DOMAIN"
echo "📱 Ссылка для Telegram Mini App: https://$DOMAIN"
echo ""
echo "Проверить статус Nginx: sudo systemctl status nginx"
echo "========================================================"
