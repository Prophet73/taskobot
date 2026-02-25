"""
Configuration settings
"""
import os
import secrets
from dotenv import load_dotenv

load_dotenv()

# Telegram Bot
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# Database
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/tasktracker.db")

# Morning reminder time (hour in UTC)
MORNING_REMINDER_HOUR = int(os.getenv("MORNING_REMINDER_HOUR", "6"))  # 6 UTC = 9 MSK

# API
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8002"))

# Security
SECRET_KEY = os.getenv("SECRET_KEY", "")
if not SECRET_KEY:
    # Генерируем временный ключ для разработки (в проде должен быть в .env!)
    SECRET_KEY = secrets.token_urlsafe(32)
    print("WARNING: SECRET_KEY not set in .env, using generated key. Set SECRET_KEY in production!")

# CORS - разрешённые домены (через запятую)
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:3010,http://localhost:3002,http://localhost:5173").split(",")

# WebApp URL для Telegram
WEBAPP_URL = os.getenv("WEBAPP_URL", "")
