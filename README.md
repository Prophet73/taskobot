# Task Tracker Bot

Telegram бот для трекинга задач в рабочих чатах с веб-дашбордом.

## Возможности

- Создание задач через упоминание: `@username, описание задачи`
- Приоритеты задач (срочно, важно)
- Утренние напоминания о невыполненных задачах
- Веб-дашборд для визуализации
- Поддержка нескольких проектов/чатов
- Статистика выполнения

## Команды бота

| Команда | Описание |
|---------|----------|
| `/start` | Активация бота в чате |
| `/help` | Справка по командам |
| `/tasks` | Все задачи проекта |
| `/mytasks` | Мои задачи |
| `/done [id]` | Отметить задачу выполненной |
| `/stats` | Статистика проекта |
| `/admin @username` | Назначить админа |

## Создание задачи

Просто напиши в чат:
```
@petya, подготовить отчёт за неделю
```

Добавь приоритет:
```
@ivan, срочно! согласовать договор
```

## Установка

### 1. Создание Telegram бота

1. Открой @BotFather в Telegram
2. Отправь `/newbot`
3. Следуй инструкциям и сохрани токен

### 2. Backend

```bash
cd backend

# Создать виртуальное окружение
python -m venv venv
source venv/bin/activate  # Linux/Mac
# или
venv\Scripts\activate  # Windows

# Установить зависимости
pip install -r requirements.txt

# Настроить переменные окружения
cp .env.example .env
# Отредактировать .env и вставить BOT_TOKEN

# Запустить
python main.py
```

### 3. Frontend

```bash
cd frontend

# Установить зависимости
npm install

# Запустить в режиме разработки
npm run dev

# Или собрать для продакшена
npm run build
```

## Структура проекта

```
klishin/
├── backend/
│   ├── main.py          # FastAPI + запуск бота
│   ├── bot.py           # Telegram бот (aiogram)
│   ├── models.py        # SQLAlchemy модели
│   ├── database.py      # Настройка БД
│   ├── crud.py          # Операции с БД
│   ├── schemas.py       # Pydantic схемы
│   ├── config.py        # Конфигурация
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── components/
│   │   │   ├── Layout.jsx
│   │   │   ├── TaskCard.jsx
│   │   │   └── StatsCard.jsx
│   │   ├── pages/
│   │   │   ├── Dashboard.jsx
│   │   │   ├── ProjectPage.jsx
│   │   │   └── TasksPage.jsx
│   │   └── api/
│   │       └── client.js
│   ├── package.json
│   ├── vite.config.js
│   └── tailwind.config.js
└── README.md
```

## API Endpoints

| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/api/dashboard` | Данные дашборда |
| GET | `/api/projects` | Список проектов |
| GET | `/api/projects/{id}` | Детали проекта |
| GET | `/api/projects/{id}/stats` | Статистика проекта |
| GET | `/api/tasks` | Список задач (с фильтрами) |
| PATCH | `/api/tasks/{id}` | Обновить задачу |

## Деплой

### Docker (рекомендуется)

Создай `docker-compose.yml`:

```yaml
version: '3.8'

services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      - BOT_TOKEN=${BOT_TOKEN}
    volumes:
      - ./data:/app/data

  frontend:
    build: ./frontend
    ports:
      - "3000:80"
    depends_on:
      - backend
```

### VPS

1. Установи Python 3.11+ и Node.js 18+
2. Настрой Nginx как reverse proxy
3. Используй systemd для автозапуска
4. Настрой SSL через Let's Encrypt

## Переменные окружения

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `BOT_TOKEN` | Токен Telegram бота | - |
| `MORNING_REMINDER_HOUR` | Час напоминаний (UTC) | 6 |
| `API_HOST` | Хост API | 0.0.0.0 |
| `API_PORT` | Порт API | 8000 |

## Лицензия

MIT
