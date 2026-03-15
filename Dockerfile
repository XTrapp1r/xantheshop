FROM python:3.11-slim

WORKDIR /app

# Зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Код бота
COPY bot/ ./bot/
COPY .env.example .env.example

# БД по умолчанию в /data (в compose монтируем volume)
ENV DATABASE_URL=sqlite+aiosqlite:///data/shop.db

# Запуск из корня проекта: python -m bot.main
CMD ["python", "-m", "bot.main"]
