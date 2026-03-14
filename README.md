## Telegram-магазин внутриигровых услуг (MVP)

### Стек

- **Python** 3.11+
- **aiogram** 3.x (router-based)
- **SQLite** (async, через SQLAlchemy 2.x + aiosqlite)
- **python-dotenv**

### Структура

- `bot/main.py` — точка входа
- `bot/handlers/` — хендлеры бота
- `bot/keyboards/` — клавиатуры
- `bot/database/` — модели и инициализация БД
- `bot/services/` — бизнес-логика (работа с БД)
- `bot/states/` — FSM-состояния
- `bot/utils/` — утилиты (тексты и т.п.)
- `.env` — конфигурация (см. `.env.example`)

### Установка и запуск

1. Перейдите в папку проекта:

   ```bash
   cd project
   ```

2. Создайте виртуальное окружение (пример для Windows PowerShell):

   ```bash
   py -3.11 -m venv .venv
   .venv\Scripts\activate
   ```

3. Установите зависимости:

   ```bash
   pip install -r requirements.txt
   ```

4. Создайте файл `.env` на основе `.env.example` и заполните:

   - `BOT_TOKEN` — токен Telegram-бота
   - `ADMIN_IDS` — список Telegram ID админов через запятую
   - `SUPPORT_USERNAME` — юзернейм саппорта
   - `REVIEWS_URL` — ссылка на отзывы (можно-заглушку)
   - `DATABASE_URL` — по умолчанию `sqlite+aiosqlite:///./shop.db`

5. Запустите бота:

   ```bash
   py -m bot.main
   ```

   или

   ```bash
   python -m bot.main
   ```

При первом запуске БД автоматически создастся и заполнится тестовыми категориями и товарами.

