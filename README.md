# TMDB Bot

Telegram-бот для поиска фильмов, сериалов, актёров и режиссёров через TMDB API.

Лёгкий: Python + aiogram 3 + aiohttp, без БД и Redis. Работает в личке, доступ ограничен белым списком пользователей.

## Возможности

- Поиск по категориям: 🎬 Фильмы | 📺 Сериалы | 🧑 Актёры и режиссёры
- Карточка тайтла: постер, название, год, рейтинг, жанры, длительность/сезоны, сюжет
- Кнопки на карточке: RuTube, YouTube, Трейлер (поиск по названию)
- Актёры с ролями и пагинацией, режиссёр, фильмография (от новых к старым)
- Похожие тайтлы: фильтр мусора (<20 голосов), подстраховка рекомендациями, сортировка по качеству
- Доступ только для пользователей из `ALLOWED_USERS`

## Структура

```
bot.py             # хендлеры, FSM, клавиатуры
tmdb.py            # клиент TMDB API + кэш в памяти
config.py          # чтение настроек из окружения
pyproject.toml     # зависимости
tmdb-bot.service   # systemd unit
```

## Установка и запуск

```bash
python3 -m venv .venv
.venv/bin/pip install -e .

# настроить секреты
cat > .tmdb-bot.env <<EOF
BOT_TOKEN=<токен от @BotFather>
TMDB_API_KEY=<ключ на themoviedb.org/settings/api>
ALLOWED_USERS=<tg_user_id>,<tg_user_id>
EOF

.venv/bin/python bot.py
```

Кэш TMDB-ответов — 1 час, без файлов на диске (постеры отправляются из памяти).

## Деплой (systemd)

Сервис предполагает размещение в `/opt/tmdb-bot`:

```bash
sudo cp tmdb-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now tmdb-bot.service
```

Обновление: `git pull && sudo systemctl restart tmdb-bot.service`.

## Переменные окружения

| Переменная | Описание |
|---|---|
| `BOT_TOKEN` | Токен бота от @BotFather |
| `TMDB_API_KEY` | Ключ TMDB API (бесплатный) |
| `ALLOWED_USERS` | Telegram user ID через запятую — кому разрешён доступ |
