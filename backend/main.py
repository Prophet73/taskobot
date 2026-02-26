"""
FastAPI Application + Telegram Bot v2
Task Tracker with Roles and Authorization
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import FastAPI, Depends, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from database import get_db, init_db
from models import Project, Task, User, ProjectMembership, Role, TaskStatus, TaskPriority, TokenRole
from schemas import (
    ProjectResponse, ProjectWithDetails, TaskResponse, TaskUpdate, TaskCreate,
    ProjectStats, DashboardData, MembershipResponse, MembershipUpdate, MembershipAdd,
    UserResponse, AuthCodeRequest, AuthResponse, ReminderRequest, ReminderResponse,
    MyTasksResponse, CommentCreate, CommentResponse, TaskHistoryResponse,
    ProjectSettingsUpdate, ProjectTokenLegacyResponse, ProjectByTokenResponse,
    ProjectTokenCreate, ProjectTokenResponse, TokenRoleEnum,
    WebAppAuthRequest
)
import crud
from bot import TaskBot, get_task_keyboard
from config import BOT_TOKEN, MORNING_REMINDER_HOUR, ALLOWED_ORIGINS
from auth import (
    get_current_user, get_current_user_optional, CurrentUser,
    verify_auth_code, create_access_token, check_project_access,
    validate_webapp_init_data
)

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Scheduler for reminders
scheduler = AsyncIOScheduler()
bot: Optional[TaskBot] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle events"""
    global bot

    # Startup
    logger.info("Initializing database...")
    init_db()

    # Start bot if token provided
    if BOT_TOKEN:
        logger.info("Starting Telegram bot...")
        bot = TaskBot(BOT_TOKEN)

        # Schedule morning reminders
        scheduler.add_job(
            bot.send_morning_reminders,
            "cron",
            hour=MORNING_REMINDER_HOUR,
            minute=0,
            id="morning_reminders"
        )
        scheduler.start()

        # Run bot in background
        asyncio.create_task(bot.start())
    else:
        logger.warning("BOT_TOKEN not set, bot disabled")

    yield

    # Shutdown
    scheduler.shutdown()
    logger.info("Shutdown complete")


app = FastAPI(
    title="Task Tracker API v2",
    description="API для трекера задач с системой ролей",
    version="2.0.0",
    lifespan=lifespan
)

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


# ============ Public Routes ============

@app.get("/")
async def root():
    return {"message": "Task Tracker API", "version": "2.0.0"}


@app.get("/api/health")
async def health():
    return {"status": "ok", "bot_active": bot is not None}


# ============ Auth Routes ============

@app.post("/api/auth/login", response_model=AuthResponse)
async def login(request: AuthCodeRequest, db: Session = Depends(get_db)):
    """
    Авторизация по коду из Telegram.
    Пользователь запрашивает код командой /weblogin в боте.
    """
    user = verify_auth_code(db, request.code)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired code"
        )

    token = create_access_token(user.id, user.telegram_id, user.is_superadmin)

    return AuthResponse(
        access_token=token,
        user=UserResponse.model_validate(user)
    )


@app.get("/api/auth/me", response_model=UserResponse)
async def get_me(current_user: CurrentUser = Depends(get_current_user)):
    """Получить информацию о текущем пользователе"""
    return UserResponse.model_validate(current_user.user)


# ============ Projects Routes (Protected) ============

@app.get("/api/projects", response_model=List[ProjectResponse])
async def get_projects(
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Получить проекты пользователя.
    Суперадмин видит все, остальные - только свои.
    """
    if current_user.is_superadmin:
        return crud.get_all_projects(db)
    return crud.get_user_projects(db, current_user.user_id)


@app.get("/api/projects/{project_id}", response_model=ProjectWithDetails)
async def get_project(
    project_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Получить проект с деталями"""
    membership = check_project_access(db, current_user, project_id)
    if not membership:
        raise HTTPException(status_code=403, detail="Access denied")

    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    return project


@app.get("/api/projects/{project_id}/stats", response_model=ProjectStats)
async def get_project_stats(
    project_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Статистика проекта"""
    membership = check_project_access(db, current_user, project_id)
    if not membership:
        raise HTTPException(status_code=403, detail="Access denied")

    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    stats = crud.get_project_stats(db, project_id)
    return ProjectStats(
        project_id=project.id,
        project_name=project.name,
        **stats
    )


@app.get("/api/projects/{project_id}/members", response_model=List[MembershipResponse])
async def get_project_members(
    project_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Получить участников проекта (только для manager+)"""
    membership = check_project_access(db, current_user, project_id, Role.MANAGER)
    if not membership:
        raise HTTPException(status_code=403, detail="Access denied - manager role required")

    return crud.get_project_members(db, project_id)


@app.patch("/api/projects/{project_id}/members/{user_id}", response_model=MembershipResponse)
async def update_member_role(
    project_id: int,
    user_id: int,
    update: MembershipUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Изменить роль участника (только для manager+)"""
    membership = check_project_access(db, current_user, project_id, Role.MANAGER)
    if not membership:
        raise HTTPException(status_code=403, detail="Access denied - manager role required")

    # Нельзя менять роль себе
    if user_id == current_user.user_id and not current_user.is_superadmin:
        raise HTTPException(status_code=400, detail="Cannot change your own role")

    role = Role(update.role.value)
    updated = crud.update_member_role(db, user_id, project_id, role)
    if not updated:
        raise HTTPException(status_code=404, detail="Membership not found")

    return updated


@app.post("/api/projects/{project_id}/members", response_model=MembershipResponse)
async def add_project_member(
    project_id: int,
    data: MembershipAdd,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Добавить участника в проект по username (manager+)"""
    membership = check_project_access(db, current_user, project_id, Role.MANAGER)
    if not membership:
        raise HTTPException(status_code=403, detail="Access denied - manager role required")

    username = data.username.lstrip("@").strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username is required")

    role = Role(data.role.value)
    result = crud.add_member_by_username(db, project_id, username, role)
    if not result:
        raise HTTPException(status_code=400, detail="Failed to add member")

    return result


@app.delete("/api/projects/{project_id}/members/{user_id}")
async def remove_project_member(
    project_id: int,
    user_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Удалить участника из проекта (manager+)"""
    membership = check_project_access(db, current_user, project_id, Role.MANAGER)
    if not membership:
        raise HTTPException(status_code=403, detail="Access denied - manager role required")

    if user_id == current_user.user_id and not current_user.is_superadmin:
        raise HTTPException(status_code=400, detail="Cannot remove yourself")

    if not crud.remove_member(db, project_id, user_id):
        raise HTTPException(status_code=404, detail="Member not found")

    return {"status": "removed"}


# ============ Tasks Routes (Protected) ============

@app.get("/api/tasks", response_model=List[TaskResponse])
async def get_tasks(
    project_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    assignee_id: Optional[int] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Получить задачи.
    - Суперадмин/Менеджер: все задачи проекта
    - Исполнитель: только свои задачи
    """
    if project_id:
        membership = check_project_access(db, current_user, project_id)
        if not membership:
            raise HTTPException(status_code=403, detail="Access denied")

        # Исполнитель видит только свои задачи
        if membership.role == Role.EXECUTOR:
            assignee_id = current_user.user_id

    query = db.query(Task)

    if project_id:
        query = query.filter(Task.project_id == project_id)
    else:
        # Без project_id - только задачи из проектов пользователя
        if not current_user.is_superadmin:
            user_projects = crud.get_user_projects(db, current_user.user_id)
            project_ids = [p.id for p in user_projects]
            query = query.filter(Task.project_id.in_(project_ids))

    if status:
        query = query.filter(Task.status == status)
    if assignee_id:
        query = query.filter(Task.assignee_id == assignee_id)

    return query.order_by(Task.created_at.desc()).offset(skip).limit(limit).all()


@app.get("/api/tasks/my", response_model=MyTasksResponse)
async def get_my_tasks(
    project_id: Optional[int] = Query(None),
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Мои задачи (для исполнителя)"""
    tasks = crud.get_user_tasks(db, current_user.user_id, project_id, active_only=True)
    stats = crud.get_user_stats(db, current_user.user_id, project_id)

    return MyTasksResponse(
        user=UserResponse.model_validate(current_user.user),
        tasks=tasks,
        stats=stats
    )


@app.get("/api/tasks/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Получить задачу по ID"""
    task = crud.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Проверяем доступ к проекту
    membership = check_project_access(db, current_user, task.project_id)
    if not membership:
        raise HTTPException(status_code=403, detail="Access denied")

    # Исполнитель видит только свои задачи
    if membership.role == Role.EXECUTOR and task.assignee_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    return task


@app.post("/api/tasks", response_model=TaskResponse)
async def create_task(
    task_data: TaskCreate,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Создать задачу (только manager+)"""
    membership = check_project_access(db, current_user, task_data.project_id, Role.MANAGER)
    if not membership:
        raise HTTPException(status_code=403, detail="Access denied - manager role required")

    priority = TaskPriority(task_data.priority.value) if task_data.priority else TaskPriority.NORMAL

    task = crud.create_task(
        db=db,
        project_id=task_data.project_id,
        creator_id=current_user.user_id,
        assignee_id=task_data.assignee_id,
        description=task_data.description,
        priority=priority,
        due_date=task_data.due_date
    )

    # Уведомляем исполнителя через бот (в фоне, не блокируя API)
    if bot and task.assignee and task.assignee.telegram_id != 0:
        creator = current_user.user
        creator_name = f"@{creator.username}" if creator.username else creator.full_name or "Менеджер"
        project = crud.get_project(db, task_data.project_id)
        project_name = project.name if project else "Проект"

        async def _notify():
            try:
                await bot.bot.send_message(
                    task.assignee.telegram_id,
                    f"📋 <b>Новая задача #{task.id}!</b>\n\n"
                    f"📝 {task.description[:100]}\n\n"
                    f"👤 От: {creator_name}\n"
                    f"📁 Проект: {project_name}",
                    reply_markup=get_task_keyboard(task.id, task.status)
                )
            except Exception as e:
                logger.warning(f"Failed to notify assignee via bot: {e}")

        asyncio.create_task(_notify())

    return task


@app.patch("/api/tasks/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: int,
    update: TaskUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Обновить задачу.
    - Исполнитель может менять только статус своих задач
    - Менеджер может менять всё
    """
    task = crud.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    membership = check_project_access(db, current_user, task.project_id)
    if not membership:
        raise HTTPException(status_code=403, detail="Access denied")

    # Исполнитель может только менять статус своих задач
    if membership.role == Role.EXECUTOR:
        if task.assignee_id != current_user.user_id:
            raise HTTPException(status_code=403, detail="Access denied")
        # Разрешаем только смену статуса
        if update.status:
            task_status = TaskStatus(update.status.value)
            crud.update_task_status_with_history(db, task_id, task_status, current_user.user_id)
        return crud.get_task(db, task_id)

    # Менеджер может всё
    old_assignee_id = task.assignee_id

    if update.status:
        task_status = TaskStatus(update.status.value)
        crud.update_task_status_with_history(db, task_id, task_status, current_user.user_id)

    update_data = {}
    if update.description:
        update_data['description'] = update.description
    if update.priority:
        update_data['priority'] = TaskPriority(update.priority.value)
    if update.due_date:
        update_data['due_date'] = update.due_date
    if update.assignee_id:
        update_data['assignee_id'] = update.assignee_id

    if update_data:
        crud.update_task(db, task_id, **update_data)

    updated_task = crud.get_task(db, task_id)

    # Уведомляем нового исполнителя при смене (в фоне)
    if bot and update.assignee_id and update.assignee_id != old_assignee_id:
        new_assignee = crud.get_user(db, update.assignee_id)
        if new_assignee and new_assignee.telegram_id != 0:
            project = crud.get_project(db, updated_task.project_id)
            project_name = project.name if project else "Проект"
            changer = current_user.user
            changer_name = f"@{changer.username}" if changer.username else changer.full_name or "Менеджер"

            async def _notify():
                try:
                    await bot.bot.send_message(
                        new_assignee.telegram_id,
                        f"📋 <b>Тебе назначена задача #{updated_task.id}</b>\n\n"
                        f"📝 {updated_task.description[:100]}\n\n"
                        f"👤 От: {changer_name}\n"
                        f"📁 Проект: {project_name}",
                        reply_markup=get_task_keyboard(updated_task.id, updated_task.status)
                    )
                except Exception as e:
                    logger.warning(f"Failed to notify new assignee: {e}")

            asyncio.create_task(_notify())

    return updated_task


@app.delete("/api/tasks/{task_id}")
async def delete_task(
    task_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Удалить задачу (только manager+)"""
    task = crud.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    membership = check_project_access(db, current_user, task.project_id, Role.MANAGER)
    if not membership:
        raise HTTPException(status_code=403, detail="Access denied - manager role required")

    crud.delete_task(db, task_id)
    return {"status": "deleted"}


# ============ Dashboard Routes ============

@app.get("/api/dashboard", response_model=DashboardData)
async def get_dashboard(
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Данные для дашборда.
    Зависят от роли пользователя.
    """
    # Получаем проекты пользователя
    if current_user.is_superadmin:
        projects = crud.get_all_projects(db)
    else:
        projects = crud.get_user_projects(db, current_user.user_id)

    project_stats = []
    total_tasks = 0
    total_completed = 0

    for project in projects:
        stats = crud.get_project_stats(db, project.id)
        project_stats.append(ProjectStats(
            project_id=project.id,
            project_name=project.name,
            **stats
        ))
        total_tasks += stats["total_tasks"]
        total_completed += stats["completed_tasks"]

    # Recent tasks - только из доступных проектов
    project_ids = [p.id for p in projects]
    recent_tasks = db.query(Task).filter(
        Task.project_id.in_(project_ids)
    ).order_by(Task.created_at.desc()).limit(10).all()

    completion_rate = (total_completed / total_tasks * 100) if total_tasks > 0 else 0

    return DashboardData(
        user=UserResponse.model_validate(current_user.user),
        projects=project_stats,
        recent_tasks=recent_tasks,
        total_tasks=total_tasks,
        total_completed=total_completed,
        completion_rate=completion_rate
    )


# ============ Reminder Routes (Manager+) ============

@app.post("/api/reminders/send", response_model=ReminderResponse)
async def send_reminders(
    request: ReminderRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Отправить напоминания (только manager+).
    Если user_id указан - одному пользователю, иначе всем.
    """
    global bot

    membership = check_project_access(db, current_user, request.project_id, Role.MANAGER)
    if not membership:
        raise HTTPException(status_code=403, detail="Access denied - manager role required")

    if not bot:
        raise HTTPException(status_code=503, detail="Bot is not available")

    project = crud.get_project(db, request.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        if request.user_id:
            # Напоминание одному пользователю
            user = crud.get_user(db, request.user_id)
            if not user or user.telegram_id == 0:
                raise HTTPException(status_code=404, detail="User not found or has no telegram_id")

            tasks = crud.get_user_tasks(db, request.user_id, request.project_id, active_only=True)
            if tasks:
                await bot.send_reminder_to_user(user, tasks, project.name)
                return ReminderResponse(
                    success=True,
                    sent_count=1,
                    message=f"Reminder sent to {user.full_name or user.username}"
                )
            else:
                return ReminderResponse(
                    success=True,
                    sent_count=0,
                    message="User has no pending tasks"
                )
        else:
            # Напоминание всем
            count = await bot.send_project_reminders(request.project_id)
            return ReminderResponse(
                success=True,
                sent_count=count,
                message=f"Reminders sent to {count} users"
            )
    except Exception as e:
        logger.error(f"Failed to send reminders: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============ Comments Routes ============

@app.get("/api/tasks/{task_id}/comments", response_model=List[CommentResponse])
async def get_task_comments(
    task_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Получить комментарии к задаче"""
    task = crud.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    membership = check_project_access(db, current_user, task.project_id)
    if not membership:
        raise HTTPException(status_code=403, detail="Access denied")

    return crud.get_task_comments(db, task_id)


@app.post("/api/tasks/{task_id}/comments", response_model=CommentResponse)
async def create_comment(
    task_id: int,
    comment_data: CommentCreate,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Добавить комментарий к задаче"""
    task = crud.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    membership = check_project_access(db, current_user, task.project_id)
    if not membership:
        raise HTTPException(status_code=403, detail="Access denied")

    comment = crud.create_comment(db, task_id, current_user.user_id, comment_data.text)

    # Уведомляем другую сторону через бот (в фоне)
    if bot:
        commenter = current_user.user
        commenter_name = f"@{commenter.username}" if commenter.username else commenter.full_name or "Пользователь"
        notify_text = (
            f"💬 <b>Новый комментарий к задаче #{task.id}</b>\n\n"
            f"{commenter_name}: {comment_data.text[:200]}\n\n"
            f"📝 {task.description[:60]}"
        )

        async def _notify_comment():
            # Если комментирует исполнитель — уведомляем менеджеров
            if task.assignee_id == current_user.user_id:
                managers = crud.get_project_managers(db, task.project_id)
                for manager in managers:
                    if manager.telegram_id != 0 and manager.id != current_user.user_id:
                        try:
                            await bot.bot.send_message(
                                manager.telegram_id, notify_text,
                                reply_markup=get_task_keyboard(task.id, task.status, is_manager=True)
                            )
                        except Exception as e:
                            logger.warning(f"Failed to notify manager about comment: {e}")
            else:
                # Иначе уведомляем исполнителя
                if task.assignee and task.assignee.telegram_id != 0 and task.assignee_id != current_user.user_id:
                    try:
                        await bot.bot.send_message(
                            task.assignee.telegram_id, notify_text,
                            reply_markup=get_task_keyboard(task.id, task.status)
                        )
                    except Exception as e:
                        logger.warning(f"Failed to notify assignee about comment: {e}")

        asyncio.create_task(_notify_comment())

    return comment


@app.delete("/api/comments/{comment_id}")
async def delete_comment(
    comment_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Удалить свой комментарий"""
    if not crud.delete_comment(db, comment_id, current_user.user_id):
        raise HTTPException(status_code=404, detail="Comment not found or access denied")
    return {"status": "deleted"}


# ============ Task History Routes ============

@app.get("/api/tasks/{task_id}/history", response_model=List[TaskHistoryResponse])
async def get_task_history(
    task_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Получить историю изменений задачи"""
    task = crud.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    membership = check_project_access(db, current_user, task.project_id)
    if not membership:
        raise HTTPException(status_code=403, detail="Access denied")

    return crud.get_task_history(db, task_id)


# ============ Project Settings Routes ============

@app.patch("/api/projects/{project_id}/settings", response_model=ProjectResponse)
async def update_project_settings(
    project_id: int,
    settings: ProjectSettingsUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Обновить настройки проекта (manager+)"""
    membership = check_project_access(db, current_user, project_id, Role.MANAGER)
    if not membership:
        raise HTTPException(status_code=403, detail="Access denied")

    project = crud.update_project_settings(
        db, project_id,
        reminder_enabled=settings.reminder_enabled,
        reminder_time=settings.reminder_time
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    return project


@app.post("/api/projects/{project_id}/token", response_model=ProjectTokenLegacyResponse)
async def generate_project_token_legacy(
    project_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Сгенерировать токен доступа для проекта (legacy, manager+)"""
    membership = check_project_access(db, current_user, project_id, Role.MANAGER)
    if not membership:
        raise HTTPException(status_code=403, detail="Access denied")

    token = crud.generate_project_token(db, project_id)
    return ProjectTokenLegacyResponse(access_token=token)


# ============ Project Tokens (Role-based) ============

@app.post("/api/projects/{project_id}/tokens", response_model=ProjectTokenResponse)
async def create_project_token(
    project_id: int,
    data: ProjectTokenCreate,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Создать токен доступа с ролью (manager+). Для executor — нужен member_id."""
    membership = check_project_access(db, current_user, project_id, Role.MANAGER)
    if not membership:
        raise HTTPException(status_code=403, detail="Access denied - manager role required")

    role = TokenRole(data.role.value)

    if role == TokenRole.EXECUTOR:
        if not data.member_id:
            raise HTTPException(status_code=400, detail="member_id is required for executor tokens")
        # Проверяем что пользователь — участник проекта
        member = crud.get_membership(db, data.member_id, project_id)
        if not member:
            raise HTTPException(status_code=404, detail="User is not a member of this project")

    pt = crud.create_project_token(db, project_id, role, member_id=data.member_id)
    return pt


@app.get("/api/projects/{project_id}/tokens", response_model=List[ProjectTokenResponse])
async def get_project_tokens(
    project_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Получить все токены проекта (manager+)"""
    membership = check_project_access(db, current_user, project_id, Role.MANAGER)
    if not membership:
        raise HTTPException(status_code=403, detail="Access denied - manager role required")

    return crud.get_project_tokens(db, project_id)


@app.delete("/api/projects/{project_id}/tokens/{token_id}")
async def revoke_project_token(
    project_id: int,
    token_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Отозвать токен проекта (manager+)"""
    membership = check_project_access(db, current_user, project_id, Role.MANAGER)
    if not membership:
        raise HTTPException(status_code=403, detail="Access denied - manager role required")

    if not crud.revoke_project_token(db, token_id):
        raise HTTPException(status_code=404, detail="Token not found")

    return {"status": "revoked"}


# ============ Token-based Access (Public) ============

@app.get("/api/project-by-token", response_model=ProjectByTokenResponse)
async def get_project_by_token(
    token: str = Query(...),
    db: Session = Depends(get_db)
):
    """Получить проект по токену доступа (публичный endpoint)"""
    result = crud.get_project_by_token(db, token)
    if not result:
        raise HTTPException(status_code=404, detail="Invalid token or project not found")

    project, token_role, member_id = result

    stats = crud.get_project_stats(db, project.id)
    tasks = crud.get_project_tasks(db, project.id)
    members = crud.get_project_members(db, project.id)

    # Executor с привязкой к участнику — показываем только его задачи
    if token_role == TokenRole.EXECUTOR and member_id:
        tasks = [t for t in tasks if t.assignee_id == member_id]

    return ProjectByTokenResponse(
        project=ProjectResponse.model_validate(project),
        stats=ProjectStats(
            project_id=project.id,
            project_name=project.name,
            **stats
        ),
        tasks=[TaskResponse.model_validate(t) for t in tasks],
        token_role=TokenRoleEnum(token_role.value),
        member_id=member_id,
        members=[MembershipResponse.model_validate(m) for m in members]
    )


@app.patch("/api/token-tasks/{task_id}", response_model=TaskResponse)
async def update_task_by_token(
    task_id: int,
    update: TaskUpdate,
    token: str = Query(...),
    db: Session = Depends(get_db)
):
    """Обновить задачу через токен доступа (публичный endpoint с проверкой роли)"""
    result = crud.get_project_by_token(db, token)
    if not result:
        raise HTTPException(status_code=404, detail="Invalid token")

    project, token_role, member_id = result

    task = crud.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.project_id != project.id:
        raise HTTPException(status_code=403, detail="Task does not belong to this project")

    # Executor с привязкой — может менять только свои задачи
    if token_role == TokenRole.EXECUTOR and member_id and task.assignee_id != member_id:
        raise HTTPException(status_code=403, detail="This token can only modify tasks assigned to its member")

    # Observer — только просмотр
    if token_role == TokenRole.OBSERVER:
        raise HTTPException(status_code=403, detail="Observer tokens cannot modify tasks")

    # Executor — может менять только статус (start, to_review)
    if token_role == TokenRole.EXECUTOR:
        if not update.status:
            raise HTTPException(status_code=403, detail="Executor can only change task status")
        allowed_transitions = {
            TaskStatus.PENDING: [TaskStatus.IN_PROGRESS],
            TaskStatus.IN_PROGRESS: [TaskStatus.PENDING_REVIEW],
        }
        current = task.status
        target = TaskStatus(update.status.value)
        if target not in allowed_transitions.get(current, []):
            raise HTTPException(
                status_code=403,
                detail=f"Executor cannot change status from {current.value} to {target.value}"
            )
        crud.update_task_status(db, task_id, target)
        return crud.get_task(db, task_id)

    # Manager — может всё (статус, включая approve/reject)
    if update.status:
        task_status = TaskStatus(update.status.value)
        crud.update_task_status(db, task_id, task_status)

    update_data = {}
    if update.description:
        update_data['description'] = update.description
    if update.priority:
        update_data['priority'] = TaskPriority(update.priority.value)
    if update.due_date:
        update_data['due_date'] = update.due_date
    if update.assignee_id:
        update_data['assignee_id'] = update.assignee_id

    if update_data:
        crud.update_task(db, task_id, **update_data)

    return crud.get_task(db, task_id)


# ============ WebApp Auth ============

@app.post("/api/auth/webapp", response_model=AuthResponse)
async def webapp_auth(
    request: WebAppAuthRequest,
    db: Session = Depends(get_db)
):
    """Авторизация через Telegram WebApp"""
    user_data = validate_webapp_init_data(request.init_data)
    if not user_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid WebApp data"
        )

    # Получаем или создаём пользователя
    full_name = f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}".strip()
    user = crud.get_or_create_user(
        db,
        telegram_id=user_data["id"],
        username=user_data.get("username"),
        full_name=full_name or None
    )

    token = create_access_token(user.id, user.telegram_id, user.is_superadmin)

    return AuthResponse(
        access_token=token,
        user=UserResponse.model_validate(user)
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
