"""
Database models for Task Tracker Bot v2
С системой ролей и разделением проектов
"""
from datetime import datetime
from enum import Enum
from sqlalchemy import Column, Integer, BigInteger, String, DateTime, Boolean, ForeignKey, Text, Enum as SQLEnum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class Role(str, Enum):
    """Роли в проекте"""
    SUPERADMIN = "superadmin"  # Видит все проекты, полный доступ
    MANAGER = "manager"        # Руководитель проекта - ставит задачи, видит всё в проекте
    EXECUTOR = "executor"      # Исполнитель - видит только свои задачи


class TaskStatus(str, Enum):
    """Статусы задач"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    PENDING_REVIEW = "pending_review"  # На проверке у руководителя
    DONE = "done"
    CANCELLED = "cancelled"


class TaskHistoryAction(str, Enum):
    """Типы действий в истории задач"""
    CREATED = "created"
    STATUS_CHANGED = "status_changed"
    ASSIGNED = "assigned"
    REASSIGNED = "reassigned"
    COMMENT_ADDED = "comment_added"
    PRIORITY_CHANGED = "priority_changed"
    DUE_DATE_CHANGED = "due_date_changed"


class TaskPriority(str, Enum):
    """Приоритеты задач"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class User(Base):
    """
    Глобальный пользователь системы.
    Один telegram аккаунт = один User.
    Может участвовать в нескольких проектах с разными ролями.
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(BigInteger, unique=True, index=True, nullable=False)
    username = Column(String(255), index=True)  # @username без @
    full_name = Column(String(255))
    is_superadmin = Column(Boolean, default=False)  # Глобальный админ всей системы
    created_at = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.utcnow)

    # Связи
    memberships = relationship("ProjectMembership", back_populates="user", cascade="all, delete-orphan")
    created_tasks = relationship("Task", back_populates="creator", foreign_keys="Task.creator_id")
    assigned_tasks = relationship("Task", back_populates="assignee", foreign_keys="Task.assignee_id")
    auth_codes = relationship("AuthCode", back_populates="user", cascade="all, delete-orphan")


class Project(Base):
    """
    Проект = Telegram чат.
    Каждый чат - отдельный изолированный проект.
    """
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(BigInteger, unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Настройки напоминаний
    reminder_enabled = Column(Boolean, default=True)
    reminder_time = Column(String(5), default="09:00")  # HH:MM формат

    # Токен для изолированного доступа
    access_token = Column(String(64), unique=True, nullable=True, index=True)

    # Связи
    memberships = relationship("ProjectMembership", back_populates="project", cascade="all, delete-orphan")
    tasks = relationship("Task", back_populates="project", cascade="all, delete-orphan")


class ProjectMembership(Base):
    """
    Связь пользователя с проектом.
    Определяет роль пользователя в конкретном проекте.
    Один пользователь может быть в разных проектах с разными ролями.
    """
    __tablename__ = "project_memberships"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    role = Column(SQLEnum(Role), default=Role.EXECUTOR)
    joined_at = Column(DateTime, default=datetime.utcnow)

    # Уникальная комбинация user + project
    __table_args__ = (
        {'extend_existing': True},
    )

    # Связи
    user = relationship("User", back_populates="memberships")
    project = relationship("Project", back_populates="memberships")


class Task(Base):
    """Задача в проекте"""
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    creator_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    assignee_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    description = Column(Text, nullable=False)
    message_id = Column(Integer, nullable=True)  # ID сообщения в Telegram

    status = Column(SQLEnum(TaskStatus), default=TaskStatus.PENDING)
    priority = Column(SQLEnum(TaskPriority), default=TaskPriority.NORMAL)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    due_date = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Связи
    project = relationship("Project", back_populates="tasks")
    creator = relationship("User", back_populates="created_tasks", foreign_keys=[creator_id])
    assignee = relationship("User", back_populates="assigned_tasks", foreign_keys=[assignee_id])
    comments = relationship("TaskComment", back_populates="task", cascade="all, delete-orphan")
    history = relationship("TaskHistory", back_populates="task", cascade="all, delete-orphan")


class AuthCode(Base):
    """
    Одноразовые коды для авторизации в веб-интерфейсе через Telegram.
    Пользователь запрашивает код в боте, вводит на сайте.
    """
    __tablename__ = "auth_codes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    code = Column(String(10), unique=True, nullable=False)  # 6-значный код
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)  # Код живёт 5 минут
    is_used = Column(Boolean, default=False)

    # Связи
    user = relationship("User", back_populates="auth_codes")


class TaskComment(Base):
    """Комментарии к задачам"""
    __tablename__ = "task_comments"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Связи
    task = relationship("Task", back_populates="comments")
    user = relationship("User")


class TaskHistory(Base):
    """История изменений задач"""
    __tablename__ = "task_history"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    action = Column(SQLEnum(TaskHistoryAction), nullable=False)
    old_value = Column(String(255), nullable=True)
    new_value = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Связи
    task = relationship("Task", back_populates="history")
    user = relationship("User")
