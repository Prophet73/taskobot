"""
Система авторизации через Telegram
JWT токены для веб-интерфейса
"""
import hashlib
import hmac
import json
import secrets
import string
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import parse_qs

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from database import get_db
from models import User, AuthCode, ProjectMembership, Role
from config import SECRET_KEY, BOT_TOKEN

# Конфигурация
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24 * 7  # Токен живёт неделю
AUTH_CODE_EXPIRE_MINUTES = 5  # Код живёт 5 минут

security = HTTPBearer(auto_error=False)


def generate_auth_code() -> str:
    """Генерация 6-значного кода для авторизации"""
    return ''.join(secrets.choice(string.digits) for _ in range(6))


def create_auth_code(db: Session, user_id: int) -> AuthCode:
    """Создать код авторизации для пользователя"""
    # Удаляем ВСЕ старые коды этого юзера (и использованные тоже — чтобы не было коллизий)
    db.query(AuthCode).filter(
        AuthCode.user_id == user_id
    ).delete()

    # Чистим просроченные коды всех юзеров
    db.query(AuthCode).filter(
        AuthCode.expires_at <= datetime.utcnow()
    ).delete()
    db.commit()

    # Создаём новый код
    code = generate_auth_code()
    expires_at = datetime.utcnow() + timedelta(minutes=AUTH_CODE_EXPIRE_MINUTES)

    auth_code = AuthCode(
        user_id=user_id,
        code=code,
        expires_at=expires_at
    )
    db.add(auth_code)
    db.commit()
    db.refresh(auth_code)
    return auth_code


def verify_auth_code(db: Session, code: str) -> Optional[User]:
    """Проверить код и вернуть пользователя"""
    auth_code = db.query(AuthCode).filter(
        AuthCode.code == code,
        AuthCode.is_used == False,
        AuthCode.expires_at > datetime.utcnow()
    ).first()

    if not auth_code:
        return None

    # Помечаем код как использованный
    auth_code.is_used = True
    db.commit()

    return auth_code.user


def create_access_token(user_id: int, telegram_id: int, is_superadmin: bool = False) -> str:
    """Создать JWT токен"""
    expires = datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    payload = {
        "sub": str(user_id),
        "telegram_id": telegram_id,
        "is_superadmin": is_superadmin,
        "exp": expires
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    """Декодировать JWT токен"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


class CurrentUser:
    """Данные текущего пользователя из токена"""
    def __init__(self, user_id: int, telegram_id: int, is_superadmin: bool, user: User):
        self.user_id = user_id
        self.telegram_id = telegram_id
        self.is_superadmin = is_superadmin
        self.user = user


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> CurrentUser:
    """Dependency для получения текущего пользователя из JWT"""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )

    payload = decode_token(credentials.credentials)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )

    user_id = int(payload["sub"])
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )

    # Обновляем last_seen только если прошло > 5 минут
    now = datetime.utcnow()
    if not user.last_seen or (now - user.last_seen).total_seconds() > 300:
        user.last_seen = now
        db.commit()

    return CurrentUser(
        user_id=user.id,
        telegram_id=user.telegram_id,
        is_superadmin=user.is_superadmin,
        user=user
    )


async def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> Optional[CurrentUser]:
    """Опциональная авторизация - не выбрасывает ошибку"""
    if not credentials:
        return None

    try:
        return await get_current_user(credentials, db)
    except HTTPException:
        return None


def check_project_access(
    db: Session,
    user: CurrentUser,
    project_id: int,
    min_role: Role = Role.EXECUTOR
) -> Optional[ProjectMembership]:
    """
    Проверить доступ пользователя к проекту.
    Возвращает membership если есть доступ, иначе None.

    min_role определяет минимальную требуемую роль:
    - EXECUTOR: любой участник
    - MANAGER: только менеджер
    - SUPERADMIN: только суперадмин
    """
    # Суперадмин имеет доступ ко всему
    if user.is_superadmin:
        return ProjectMembership(
            user_id=user.user_id,
            project_id=project_id,
            role=Role.SUPERADMIN
        )

    membership = db.query(ProjectMembership).filter(
        ProjectMembership.user_id == user.user_id,
        ProjectMembership.project_id == project_id
    ).first()

    if not membership:
        return None

    # Проверяем уровень роли
    role_hierarchy = {Role.EXECUTOR: 1, Role.MANAGER: 2, Role.SUPERADMIN: 3}

    if role_hierarchy.get(membership.role, 0) >= role_hierarchy.get(min_role, 0):
        return membership

    return None


def require_project_access(min_role: Role = Role.EXECUTOR):
    """Decorator/dependency для проверки доступа к проекту"""
    async def dependency(
        project_id: int,
        current_user: CurrentUser = Depends(get_current_user),
        db: Session = Depends(get_db)
    ) -> ProjectMembership:
        membership = check_project_access(db, current_user, project_id, min_role)
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this project"
            )
        return membership

    return dependency


def validate_webapp_init_data(init_data: str) -> Optional[dict]:
    """
    Валидация данных от Telegram WebApp.
    Проверяет подпись и возвращает данные пользователя.
    """
    if not BOT_TOKEN:
        return None

    try:
        # Парсим данные
        parsed = {}
        for item in init_data.split("&"):
            if "=" in item:
                key, value = item.split("=", 1)
                parsed[key] = value

        if "hash" not in parsed:
            return None

        received_hash = parsed.pop("hash")

        # Формируем строку для проверки (отсортированные пары key=value)
        data_check_string = "\n".join(
            f"{k}={parsed[k]}" for k in sorted(parsed.keys())
        )

        # Вычисляем секретный ключ
        secret_key = hmac.new(
            b"WebAppData",
            BOT_TOKEN.encode(),
            hashlib.sha256
        ).digest()

        # Вычисляем hash
        computed_hash = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256
        ).hexdigest()

        if computed_hash != received_hash:
            return None

        # Возвращаем данные пользователя
        if "user" in parsed:
            from urllib.parse import unquote
            user_json = unquote(parsed["user"])
            return json.loads(user_json)

        return None
    except Exception:
        return None
