"""
Pydantic schemas for API validation v2
С поддержкой ролей и авторизации
"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel
from enum import Enum


# Enums для API
class RoleEnum(str, Enum):
    SUPERADMIN = "superadmin"
    MANAGER = "manager"
    EXECUTOR = "executor"


class TaskStatusEnum(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    PENDING_REVIEW = "pending_review"
    DONE = "done"
    CANCELLED = "cancelled"


class TaskHistoryActionEnum(str, Enum):
    CREATED = "created"
    STATUS_CHANGED = "status_changed"
    ASSIGNED = "assigned"
    REASSIGNED = "reassigned"
    COMMENT_ADDED = "comment_added"
    PRIORITY_CHANGED = "priority_changed"
    DUE_DATE_CHANGED = "due_date_changed"


class TaskPriorityEnum(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


# ============ Auth Schemas ============

class AuthCodeRequest(BaseModel):
    """Запрос на авторизацию по коду"""
    code: str


class AuthResponse(BaseModel):
    """Ответ с токеном"""
    access_token: str
    token_type: str = "bearer"
    user: "UserResponse"


class TokenPayload(BaseModel):
    """Содержимое JWT токена"""
    sub: str
    telegram_id: int
    is_superadmin: bool
    exp: datetime


# ============ User Schemas ============

class UserBase(BaseModel):
    telegram_id: int
    username: Optional[str] = None
    full_name: Optional[str] = None


class UserResponse(UserBase):
    id: int
    is_superadmin: bool
    created_at: datetime
    last_seen: datetime

    class Config:
        from_attributes = True


class UserWithRole(UserResponse):
    """Пользователь с ролью в конкретном проекте"""
    role: Optional[RoleEnum] = None


# ============ Project Membership Schemas ============

class MembershipBase(BaseModel):
    user_id: int
    project_id: int
    role: RoleEnum = RoleEnum.EXECUTOR


class MembershipResponse(MembershipBase):
    id: int
    joined_at: datetime
    user: UserResponse

    class Config:
        from_attributes = True


class MembershipUpdate(BaseModel):
    role: RoleEnum


# ============ Task Schemas ============

class TaskBase(BaseModel):
    description: str
    priority: TaskPriorityEnum = TaskPriorityEnum.NORMAL
    due_date: Optional[datetime] = None


class TaskCreate(TaskBase):
    project_id: int
    assignee_id: int


class TaskUpdate(BaseModel):
    status: Optional[TaskStatusEnum] = None
    priority: Optional[TaskPriorityEnum] = None
    due_date: Optional[datetime] = None
    description: Optional[str] = None
    assignee_id: Optional[int] = None


class TaskResponse(TaskBase):
    id: int
    project_id: int
    creator_id: int
    assignee_id: int
    status: TaskStatusEnum
    message_id: Optional[int]
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime]
    creator: Optional[UserResponse] = None
    assignee: Optional[UserResponse] = None

    class Config:
        from_attributes = True


# ============ Project Schemas ============

class ProjectBase(BaseModel):
    chat_id: int
    name: str
    description: Optional[str] = None


class ProjectCreate(ProjectBase):
    pass


class ProjectResponse(ProjectBase):
    id: int
    is_active: bool
    created_at: datetime
    reminder_enabled: bool = True
    reminder_time: str = "09:00"
    access_token: Optional[str] = None

    class Config:
        from_attributes = True


class ProjectWithDetails(ProjectResponse):
    """Проект с задачами и участниками"""
    tasks: List[TaskResponse] = []
    members: List[MembershipResponse] = []


class ProjectStats(BaseModel):
    project_id: int
    project_name: str
    total_tasks: int
    pending_tasks: int
    in_progress_tasks: int
    pending_review_tasks: int = 0
    completed_tasks: int
    members_count: int


# ============ Dashboard Schemas ============

class DashboardData(BaseModel):
    """Данные для дашборда - зависят от роли"""
    user: UserResponse
    projects: List[ProjectStats]
    recent_tasks: List[TaskResponse]
    total_tasks: int
    total_completed: int
    completion_rate: float


class MyTasksResponse(BaseModel):
    """Мои задачи для исполнителя"""
    user: UserResponse
    tasks: List[TaskResponse]
    stats: dict


# ============ Reminder Schemas ============

class ReminderRequest(BaseModel):
    """Запрос на отправку напоминания"""
    project_id: int
    user_id: Optional[int] = None  # None = всем


class ReminderResponse(BaseModel):
    """Результат отправки напоминаний"""
    success: bool
    sent_count: int
    message: str


# ============ Comment Schemas ============

class CommentCreate(BaseModel):
    """Создание комментария"""
    text: str


class CommentResponse(BaseModel):
    """Ответ с комментарием"""
    id: int
    task_id: int
    user_id: int
    text: str
    created_at: datetime
    user: Optional[UserResponse] = None

    class Config:
        from_attributes = True


# ============ Task History Schemas ============

class TaskHistoryResponse(BaseModel):
    """Запись в истории задачи"""
    id: int
    task_id: int
    user_id: int
    action: TaskHistoryActionEnum
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    created_at: datetime
    user: Optional[UserResponse] = None

    class Config:
        from_attributes = True


# ============ Project Settings Schemas ============

class ProjectSettingsUpdate(BaseModel):
    """Обновление настроек проекта"""
    reminder_enabled: Optional[bool] = None
    reminder_time: Optional[str] = None  # "HH:MM"


class ProjectTokenResponse(BaseModel):
    """Токен доступа к проекту"""
    access_token: str


class ProjectByTokenResponse(BaseModel):
    """Проект по токену с данными"""
    project: ProjectResponse
    stats: ProjectStats
    tasks: List[TaskResponse]


# ============ WebApp Auth Schemas ============

class WebAppAuthRequest(BaseModel):
    """Запрос авторизации через Telegram WebApp"""
    init_data: str


# Update forward refs
AuthResponse.model_rebuild()
