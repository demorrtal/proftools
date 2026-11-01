# Резервная копия Telegram Mini App (Proftools)

В этой папке сохранена полная реализация Telegram Mini App (Web App), созданная для бота:

## Содержимое
1. **api.py** — бэкенд на FastAPI с REST API эндпоинтами для профилей, задач, графиков уборки, тем форума и отдачи веб-интерфейса.
2. **webapp/**:
   - `index.html` — адаптивный мобильный интерфейс в стиле Telegram WebApp с поддержкой safe-area, темной темы и табов.
   - `styles.css` — стили Telegram UI с CSS переменными (`--tg-theme-*`).
   - `app.js` — клиентская логика на чистом JS с поддержкой Telegram WebApp SDK, тактильного отклика (haptics) и API запросов.
3. **run.py** — единый запуск бота и веб-сервера FastAPI (uvicorn) в отдельных потоках.
4. **setup_nginx.sh** и **nginx_proftools.conf** — автоматизация Nginx обратного проксирования и Let's Encrypt SSL сертификата для Ubuntu 24.04.
5. **telegram-bot_miniapp.service** — systemd unit для запуска Mini App версии через `run.py`.
6. **bot_miniapp.py** / **keyboards_miniapp.py** / **config_miniapp.py** / **requirements_miniapp.txt** — версии файлов бота, поддерживающие вызов WebApp и кнопку в меню Telegram.

## Как восстановить Mini App при необходимости:
1. Скопировать файлы из `miniapp_backup` обратно в корень проекта.
2. Установить зависимости: `pip install -r miniapp_backup/requirements_miniapp.txt`
3. Запустить через `python run.py`.
