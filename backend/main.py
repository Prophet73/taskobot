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
from models import Project, Task, User, ProjectMembership, Role, TaskStatus, TaskPriority
from schemas import (
    ProjectResponse, ProjectWithDetails, TaskResponse, TaskUpdate, TaskCreate,
    ProjectStats, DashboardData, MembershipResponse, MembershipUpdate,
    UserResponse, AuthCodeRequest, AuthResponse, ReminderRequest, ReminderResponse,
    MyTasksResponse, CommentCreate, CommentResponse, TaskHistoryResponse,
    ProjectSettingsUpdate, ProjectTokenResponse, ProjectByTokenResponse,
    WebAppAuthRequest
)
import crud
from bot import TaskBot
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


# ============ Tasks Routes (Protected) ============

@app.get("/api/tasks", response_model=List[TaskResponse])
async def get_tasks(
    project_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    assignee_id: Optional[int] = Query(None),
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

    return query.order_by(Task.created_at.desc()).all()


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

    return crud.get_task(db, task_id)


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

    return crud.create_comment(db, task_id, current_user.user_id, comment_data.text)


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


@app.post("/api/projects/{project_id}/token", response_model=ProjectTokenResponse)
async def generate_project_token(
    project_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Сгенерировать токен доступа для проекта (manager+)"""
    membership = check_project_access(db, current_user, project_id, Role.MANAGER)
    if not membership:
        raise HTTPException(status_code=403, detail="Access denied")

    token = crud.generate_project_token(db, project_id)
    return ProjectTokenResponse(access_token=token)


# ============ Token-based Access (Public) ============

@app.get("/api/project-by-token", response_model=ProjectByTokenResponse)
async def get_project_by_token(
    token: str = Query(...),
    db: Session = Depends(get_db)
):
    """Получить проект по токену доступа (публичный endpoint)"""
    project = crud.get_project_by_token(db, token)
    if not project:
        raise HTTPException(status_code=404, detail="Invalid token or project not found")

    stats = crud.get_project_stats(db, project.id)
    tasks = crud.get_project_tasks(db, project.id)

    return ProjectByTokenResponse(
        project=ProjectResponse.model_validate(project),
        stats=ProjectStats(
            project_id=project.id,
            project_name=project.name,
            **stats
        ),
        tasks=[TaskResponse.model_validate(t) for t in tasks]
    )


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
