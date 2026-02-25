"""
CRUD operations for Task Tracker v2
"""
from datetime import datetime
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

import secrets

from models import (
    User, Project, ProjectMembership, Task, Role, TaskStatus, TaskPriority,
    TaskComment, TaskHistory, TaskHistoryAction
)


# ============ User Operations ============

def get_user_by_telegram_id(db: Session, telegram_id: int) -> Optional[User]:
    """Найти пользователя по Telegram ID"""
    return db.query(User).filter(User.telegram_id == telegram_id).first()


def get_user_by_username(db: Session, username: str) -> Optional[User]:
    """Найти пользователя по username"""
    username = username.lstrip("@").lower()
    return db.query(User).filter(User.username.ilike(username)).first()


def get_user(db: Session, user_id: int) -> Optional[User]:
    """Получить пользователя по ID"""
    return db.query(User).filter(User.id == user_id).first()


def create_user(
    db: Session,
    telegram_id: int,
    username: Optional[str] = None,
    full_name: Optional[str] = None,
    is_superadmin: bool = False
) -> User:
    """Создать нового пользователя"""
    user = User(
        telegram_id=telegram_id,
        username=username.lstrip("@") if username else None,
        full_name=full_name,
        is_superadmin=is_superadmin
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_or_create_user(
    db: Session,
    telegram_id: int,
    username: Optional[str] = None,
    full_name: Optional[str] = None
) -> User:
    """Получить или создать пользователя"""
    user = get_user_by_telegram_id(db, telegram_id)

    if not user:
        # Проверяем, есть ли placeholder с таким username (telegram_id=0)
        if username:
            placeholder = db.query(User).filter(
                User.telegram_id == 0,
                User.username.ilike(username.lstrip("@"))
            ).first()
            if placeholder:
                # Обновляем placeholder
                placeholder.telegram_id = telegram_id
                placeholder.full_name = full_name
                db.commit()
                db.refresh(placeholder)
                return placeholder

        user = create_user(db, telegram_id, username, full_name)
    else:
        # Обновляем данные
        updated = False
        if username and user.username != username.lstrip("@"):
            user.username = username.lstrip("@")
            updated = True
        if full_name and user.full_name != full_name:
            user.full_name = full_name
            updated = True
        user.last_seen = datetime.utcnow()
        if updated:
            db.commit()
            db.refresh(user)

    return user


def create_placeholder_user(db: Session, username: str) -> User:
    """Создать placeholder пользователя (когда ставят задачу на @username, но человек ещё не писал)"""
    # Проверяем нет ли уже такого
    existing = get_user_by_username(db, username)
    if existing:
        return existing

    user = User(
        telegram_id=0,  # Placeholder
        username=username.lstrip("@")
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# ============ Project Operations ============

def get_project_by_chat_id(db: Session, chat_id: int) -> Optional[Project]:
    """Найти проект по Chat ID"""
    return db.query(Project).filter(Project.chat_id == chat_id).first()


def get_project(db: Session, project_id: int) -> Optional[Project]:
    """Получить проект по ID"""
    return db.query(Project).filter(Project.id == project_id).first()


def get_all_projects(db: Session) -> List[Project]:
    """Получить все активные проекты"""
    return db.query(Project).filter(Project.is_active == True).all()


def get_user_projects(db: Session, user_id: int) -> List[Project]:
    """Получить проекты пользователя"""
    memberships = db.query(ProjectMembership).filter(
        ProjectMembership.user_id == user_id
    ).all()
    project_ids = [m.project_id for m in memberships]
    return db.query(Project).filter(
        Project.id.in_(project_ids),
        Project.is_active == True
    ).all()


def create_project(db: Session, chat_id: int, name: str, description: str = None) -> Project:
    """Создать новый проект"""
    project = Project(
        chat_id=chat_id,
        name=name,
        description=description
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def get_or_create_project(db: Session, chat_id: int, name: str) -> Project:
    """Получить или создать проект"""
    project = get_project_by_chat_id(db, chat_id)
    if not project:
        project = create_project(db, chat_id, name)
    return project


# ============ Membership Operations ============

def get_membership(db: Session, user_id: int, project_id: int) -> Optional[ProjectMembership]:
    """Получить membership пользователя в проекте"""
    return db.query(ProjectMembership).filter(
        ProjectMembership.user_id == user_id,
        ProjectMembership.project_id == project_id
    ).first()


def get_project_members(db: Session, project_id: int) -> List[ProjectMembership]:
    """Получить всех участников проекта"""
    return db.query(ProjectMembership).filter(
        ProjectMembership.project_id == project_id
    ).all()


def get_project_managers(db: Session, project_id: int) -> List[User]:
    """Получить менеджеров проекта"""
    memberships = db.query(ProjectMembership).filter(
        ProjectMembership.project_id == project_id,
        ProjectMembership.role == Role.MANAGER
    ).all()
    return [m.user for m in memberships]


def add_member_to_project(
    db: Session,
    user_id: int,
    project_id: int,
    role: Role = Role.EXECUTOR
) -> ProjectMembership:
    """Добавить пользователя в проект"""
    # Проверяем, нет ли уже membership
    existing = get_membership(db, user_id, project_id)
    if existing:
        return existing

    membership = ProjectMembership(
        user_id=user_id,
        project_id=project_id,
        role=role
    )
    db.add(membership)
    db.commit()
    db.refresh(membership)
    return membership


def update_member_role(db: Session, user_id: int, project_id: int, role: Role) -> Optional[ProjectMembership]:
    """Обновить роль пользователя в проекте"""
    membership = get_membership(db, user_id, project_id)
    if membership:
        membership.role = role
        db.commit()
        db.refresh(membership)
    return membership


def ensure_project_membership(
    db: Session,
    user: User,
    project_id: int,
    role: Role = Role.EXECUTOR
) -> ProjectMembership:
    """Убедиться что пользователь в проекте, если нет - добавить"""
    membership = get_membership(db, user.id, project_id)
    if not membership:
        membership = add_member_to_project(db, user.id, project_id, role)
    return membership


# ============ Task Operations ============

def create_task(
    db: Session,
    project_id: int,
    creator_id: int,
    assignee_id: int,
    description: str,
    message_id: Optional[int] = None,
    priority: TaskPriority = TaskPriority.NORMAL,
    due_date: Optional[datetime] = None
) -> Task:
    """Создать задачу"""
    task = Task(
        project_id=project_id,
        creator_id=creator_id,
        assignee_id=assignee_id,
        description=description,
        message_id=message_id,
        priority=priority,
        due_date=due_date
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def get_task(db: Session, task_id: int) -> Optional[Task]:
    """Получить задачу по ID"""
    return db.query(Task).filter(Task.id == task_id).first()


def get_project_tasks(
    db: Session,
    project_id: int,
    status: Optional[TaskStatus] = None,
    assignee_id: Optional[int] = None
) -> List[Task]:
    """Получить задачи проекта с фильтрами"""
    query = db.query(Task).filter(Task.project_id == project_id)

    if status:
        query = query.filter(Task.status == status)
    if assignee_id:
        query = query.filter(Task.assignee_id == assignee_id)

    return query.order_by(Task.created_at.desc()).all()


def get_user_tasks(
    db: Session,
    user_id: int,
    project_id: Optional[int] = None,
    active_only: bool = True
) -> List[Task]:
    """Получить задачи пользователя"""
    query = db.query(Task).filter(Task.assignee_id == user_id)

    if project_id:
        query = query.filter(Task.project_id == project_id)

    if active_only:
        query = query.filter(Task.status.in_([TaskStatus.PENDING, TaskStatus.IN_PROGRESS]))

    return query.order_by(Task.created_at.desc()).all()


def get_pending_tasks_for_reminders(db: Session, project_id: Optional[int] = None) -> List[Task]:
    """Получить невыполненные задачи для напоминаний"""
    query = db.query(Task).filter(
        Task.status.in_([TaskStatus.PENDING, TaskStatus.IN_PROGRESS])
    )

    if project_id:
        query = query.filter(Task.project_id == project_id)

    return query.order_by(Task.project_id, Task.assignee_id).all()


def update_task_status(db: Session, task_id: int, status: TaskStatus) -> Optional[Task]:
    """Обновить статус задачи"""
    task = get_task(db, task_id)
    if task:
        task.status = status
        task.updated_at = datetime.utcnow()
        if status == TaskStatus.DONE:
            task.completed_at = datetime.utcnow()
        db.commit()
        db.refresh(task)
    return task


def update_task(
    db: Session,
    task_id: int,
    description: Optional[str] = None,
    priority: Optional[TaskPriority] = None,
    due_date: Optional[datetime] = None,
    assignee_id: Optional[int] = None
) -> Optional[Task]:
    """Обновить задачу"""
    task = get_task(db, task_id)
    if task:
        if description:
            task.description = description
        if priority:
            task.priority = priority
        if due_date:
            task.due_date = due_date
        if assignee_id:
            task.assignee_id = assignee_id
        task.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(task)
    return task


def delete_task(db: Session, task_id: int) -> bool:
    """Удалить задачу и связанные данные"""
    task = get_task(db, task_id)
    if not task:
        return False
    # Удаляем связанные комментарии и историю
    db.query(TaskComment).filter(TaskComment.task_id == task_id).delete()
    db.query(TaskHistory).filter(TaskHistory.task_id == task_id).delete()
    db.delete(task)
    db.commit()
    return True


# ============ Statistics ============

def get_project_stats(db: Session, project_id: int) -> dict:
    """Статистика проекта"""
    total = db.query(Task).filter(Task.project_id == project_id).count()
    pending = db.query(Task).filter(
        Task.project_id == project_id,
        Task.status == TaskStatus.PENDING
    ).count()
    in_progress = db.query(Task).filter(
        Task.project_id == project_id,
        Task.status == TaskStatus.IN_PROGRESS
    ).count()
    pending_review = db.query(Task).filter(
        Task.project_id == project_id,
        Task.status == TaskStatus.PENDING_REVIEW
    ).count()
    done = db.query(Task).filter(
        Task.project_id == project_id,
        Task.status == TaskStatus.DONE
    ).count()
    members = db.query(ProjectMembership).filter(
        ProjectMembership.project_id == project_id
    ).count()

    return {
        "total_tasks": total,
        "pending_tasks": pending,
        "in_progress_tasks": in_progress,
        "pending_review_tasks": pending_review,
        "completed_tasks": done,
        "members_count": members
    }


def get_user_stats(db: Session, user_id: int, project_id: Optional[int] = None) -> dict:
    """Статистика пользователя"""
    query = db.query(Task).filter(Task.assignee_id == user_id)
    if project_id:
        query = query.filter(Task.project_id == project_id)

    total = query.count()
    pending = query.filter(Task.status == TaskStatus.PENDING).count()
    in_progress = query.filter(Task.status == TaskStatus.IN_PROGRESS).count()
    done = query.filter(Task.status == TaskStatus.DONE).count()

    return {
        "total_tasks": total,
        "pending_tasks": pending,
        "in_progress_tasks": in_progress,
        "completed_tasks": done
    }


# ============ Task History Operations ============

def log_task_history(
    db: Session,
    task_id: int,
    user_id: int,
    action: TaskHistoryAction,
    old_value: Optional[str] = None,
    new_value: Optional[str] = None
) -> TaskHistory:
    """Записать действие в историю задачи"""
    entry = TaskHistory(
        task_id=task_id,
        user_id=user_id,
        action=action,
        old_value=old_value,
        new_value=new_value
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def get_task_history(db: Session, task_id: int) -> List[TaskHistory]:
    """Получить историю задачи"""
    return db.query(TaskHistory).filter(
        TaskHistory.task_id == task_id
    ).order_by(TaskHistory.created_at.desc()).all()


def update_task_status_with_history(
    db: Session,
    task_id: int,
    status: TaskStatus,
    user_id: int
) -> Optional[Task]:
    """Обновить статус задачи с записью в историю"""
    task = get_task(db, task_id)
    if task:
        old_status = task.status.value
        task.status = status
        task.updated_at = datetime.utcnow()
        if status == TaskStatus.DONE:
            task.completed_at = datetime.utcnow()
        db.commit()
        db.refresh(task)

        # Записываем в историю
        log_task_history(
            db, task_id, user_id,
            TaskHistoryAction.STATUS_CHANGED,
            old_status, status.value
        )
    return task


# ============ Comment Operations ============

def create_comment(db: Session, task_id: int, user_id: int, text: str) -> TaskComment:
    """Создать комментарий к задаче"""
    comment = TaskComment(
        task_id=task_id,
        user_id=user_id,
        text=text
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)

    # Записываем в историю
    log_task_history(
        db, task_id, user_id,
        TaskHistoryAction.COMMENT_ADDED,
        None, text[:50] + "..." if len(text) > 50 else text
    )
    return comment


def get_task_comments(db: Session, task_id: int) -> List[TaskComment]:
    """Получить комментарии к задаче"""
    return db.query(TaskComment).filter(
        TaskComment.task_id == task_id
    ).order_by(TaskComment.created_at.asc()).all()


def delete_comment(db: Session, comment_id: int, user_id: int) -> bool:
    """Удалить комментарий (только свой)"""
    comment = db.query(TaskComment).filter(
        TaskComment.id == comment_id,
        TaskComment.user_id == user_id
    ).first()
    if comment:
        db.delete(comment)
        db.commit()
        return True
    return False


# ============ Project Token Operations ============

def generate_project_token(db: Session, project_id: int) -> str:
    """Сгенерировать токен доступа для проекта"""
    token = secrets.token_urlsafe(32)
    project = get_project(db, project_id)
    if project:
        project.access_token = token
        db.commit()
        db.refresh(project)
    return token


def get_project_by_token(db: Session, token: str) -> Optional[Project]:
    """Получить проект по токену доступа"""
    return db.query(Project).filter(
        Project.access_token == token,
        Project.is_active == True
    ).first()


def update_project_settings(
    db: Session,
    project_id: int,
    reminder_enabled: Optional[bool] = None,
    reminder_time: Optional[str] = None
) -> Optional[Project]:
    """Обновить настройки проекта"""
    project = get_project(db, project_id)
    if project:
        if reminder_enabled is not None:
            project.reminder_enabled = reminder_enabled
        if reminder_time is not None:
            project.reminder_time = reminder_time
        db.commit()
        db.refresh(project)
    return project


# ============ Tasks for Review ============

def get_tasks_pending_review(db: Session, project_id: int) -> List[Task]:
    """Получить задачи на проверке"""
    return db.query(Task).filter(
        Task.project_id == project_id,
        Task.status == TaskStatus.PENDING_REVIEW
    ).order_by(Task.updated_at.desc()).all()
