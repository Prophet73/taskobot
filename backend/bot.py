"""
Telegram Bot for Task Tracking v2
DM-only mode: все взаимодействие через личные сообщения
"""
import re
import logging
from datetime import datetime, date, timedelta
from typing import Optional, List

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from database import get_db_session
from models import Role, TaskStatus, TaskPriority, User, Task, TaskHistoryAction
from auth import create_auth_code
from config import WEBAPP_URL
import crud

logger = logging.getLogger(__name__)

# Regex для парсинга задач: @username, текст задачи
TASK_PATTERN = re.compile(r"@(\w+)[,\s]+(.+)", re.DOTALL)

# Приоритеты из текста
PRIORITY_KEYWORDS = {
    "срочно": TaskPriority.URGENT,
    "важно": TaskPriority.HIGH,
    "urgent": TaskPriority.URGENT,
    "high": TaskPriority.HIGH,
    "!!": TaskPriority.URGENT,
    "!": TaskPriority.HIGH,
}

# Emoji
STATUS_EMOJI = {
    TaskStatus.PENDING: "⏳",
    TaskStatus.IN_PROGRESS: "🔄",
    TaskStatus.PENDING_REVIEW: "📝",
    TaskStatus.DONE: "✅",
    TaskStatus.CANCELLED: "❌"
}
PRIORITY_EMOJI = {
    TaskPriority.URGENT: "🔴",
    TaskPriority.HIGH: "🟠",
    TaskPriority.NORMAL: "🟢",
    TaskPriority.LOW: "⚪"
}
ROLE_EMOJI = {
    Role.SUPERADMIN: "👑",
    Role.MANAGER: "📋",
    Role.EXECUTOR: "👤"
}


# ============ Keyboards ============

def get_task_keyboard(task_id: int, status: TaskStatus, is_manager: bool = False) -> InlineKeyboardMarkup:
    """Клавиатура для задачи"""
    buttons = []

    if status == TaskStatus.PENDING:
        buttons.append([
            InlineKeyboardButton(text="▶️ В работу", callback_data=f"task_progress_{task_id}"),
        ])
    elif status == TaskStatus.IN_PROGRESS:
        buttons.append([
            InlineKeyboardButton(text="📝 На проверку", callback_data=f"task_review_{task_id}"),
            InlineKeyboardButton(text="⏸ Отложить", callback_data=f"task_pending_{task_id}")
        ])
    elif status == TaskStatus.PENDING_REVIEW:
        if is_manager:
            buttons.append([
                InlineKeyboardButton(text="✅ Принять", callback_data=f"task_done_{task_id}"),
                InlineKeyboardButton(text="↩️ Вернуть", callback_data=f"task_progress_{task_id}")
            ])
        else:
            buttons.append([
                InlineKeyboardButton(text="⏳ Ожидает проверки", callback_data=f"task_info_{task_id}")
            ])

    buttons.append([
        InlineKeyboardButton(text="📋 Подробнее", callback_data=f"task_info_{task_id}"),
        InlineKeyboardButton(text="💬 Комментарий", callback_data=f"comment_add_{task_id}")
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_tasks_list_keyboard(tasks: List[Task], page: int = 0, per_page: int = 5) -> InlineKeyboardMarkup:
    """Клавиатура со списком задач"""
    buttons = []
    start = page * per_page
    end = start + per_page
    page_tasks = tasks[start:end]

    for task in page_tasks:
        emoji = PRIORITY_EMOJI.get(task.priority, "")
        status = STATUS_EMOJI.get(task.status, "")
        desc = task.description[:25] + "..." if len(task.description) > 25 else task.description
        text = f"{emoji}{status} #{task.id}: {desc}"
        buttons.append([InlineKeyboardButton(text=text, callback_data=f"task_show_{task.id}")])

    # Навигация
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"tasks_page_{page-1}"))
    if end < len(tasks):
        nav_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"tasks_page_{page+1}"))
    if nav_buttons:
        buttons.append(nav_buttons)

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_main_menu_keyboard(
    is_manager: bool = False,
    is_admin: bool = False,
    is_superadmin: bool = False
) -> InlineKeyboardMarkup:
    """
    Главное меню — разное для каждой роли.
    Executor: задачи, статистика
    Manager: + все задачи, напоминания
    Admin: + создать проект, управление
    Superadmin: + управление пользователями
    """
    from aiogram.types import WebAppInfo

    buttons = []

    # === Все роли ===
    buttons.append([InlineKeyboardButton(text="📋 Мои задачи", callback_data="menu_mytasks")])
    buttons.append([InlineKeyboardButton(text="📈 Статистика", callback_data="menu_stats")])

    # === Manager+ ===
    if is_manager or is_admin or is_superadmin:
        buttons.append([InlineKeyboardButton(text="🎯 Создать задачу", callback_data="menu_newtask")])
        buttons.append([InlineKeyboardButton(text="📊 Все задачи проекта", callback_data="menu_tasks")])
        buttons.append([InlineKeyboardButton(text="📢 Напоминания", callback_data="menu_remind")])

    # === Admin+ ===
    if is_admin or is_superadmin:
        buttons.append([InlineKeyboardButton(text="📁 Мои проекты", callback_data="menu_myprojects")])
        buttons.append([InlineKeyboardButton(text="➕ Создать проект", callback_data="menu_newproject")])

    # === Superadmin ===
    if is_superadmin:
        buttons.append([InlineKeyboardButton(text="👑 Управление правами", callback_data="menu_admin")])

    # === Все роли ===
    buttons.append([InlineKeyboardButton(text="🔀 Переключить проект", callback_data="menu_switchproject")])

    if WEBAPP_URL:
        buttons.append([
            InlineKeyboardButton(text="🌐 Открыть панель", web_app=WebAppInfo(url=WEBAPP_URL))
        ])
    else:
        buttons.append([InlineKeyboardButton(text="🔑 Войти в веб", callback_data="menu_weblogin")])

    buttons.append([InlineKeyboardButton(text="❓ Помощь", callback_data="menu_help")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_projects_keyboard(projects: list, action: str = "select") -> InlineKeyboardMarkup:
    """Клавиатура выбора проекта"""
    buttons = []
    for p in projects:
        buttons.append([
            InlineKeyboardButton(text=f"📁 {p.name}", callback_data=f"project_{action}_{p.id}")
        ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_remind_keyboard(project_id: int, members: list) -> InlineKeyboardMarkup:
    """Клавиатура выбора кому отправить напоминания"""
    buttons = [
        [InlineKeyboardButton(text="📢 Всем участникам", callback_data=f"remind_all_{project_id}")]
    ]

    for member in members[:8]:  # Максимум 8 человек
        user = member.user
        name = f"@{user.username}" if user.username else user.full_name or f"User {user.id}"
        buttons.append([
            InlineKeyboardButton(text=f"👤 {name}", callback_data=f"remind_user_{project_id}_{user.id}")
        ])

    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="remind_cancel")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ============ Bot Class ============

class TaskBot:
    def __init__(self, token: str):
        self.bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        self.dp = Dispatcher()
        # Хранилище последнего раздела меню (user_id -> {"action": "mytasks/tasks/review", "project_id": 1})
        self.user_menu_context = {}
        # Черновик задачи: telegram_id -> {"project_id": int, "assignee_id": int, "assignee_name": str}
        self.user_task_draft = {}
        # Черновик комментария: telegram_id -> {"task_id": int}
        self.user_comment_draft = {}
        # Контекст смены статуса: telegram_id -> {"task_id": int, "new_status": str}
        self.user_status_comment = {}
        self._register_handlers()

    def _register_handlers(self):
        """Регистрация обработчиков"""
        # Команды
        self.dp.message.register(self.cmd_start, CommandStart())
        self.dp.message.register(self.cmd_help, Command("help"))
        self.dp.message.register(self.cmd_menu, Command("menu"))
        self.dp.message.register(self.cmd_tasks, Command("tasks"))
        self.dp.message.register(self.cmd_mytasks, Command("mytasks"))
        self.dp.message.register(self.cmd_done, Command("done"))
        self.dp.message.register(self.cmd_stats, Command("stats"))
        self.dp.message.register(self.cmd_remind, Command("remind"))
        self.dp.message.register(self.cmd_weblogin, Command("weblogin"))
        self.dp.message.register(self.cmd_newproject, Command("newproject"))
        self.dp.message.register(self.cmd_addmember, Command("addmember"))
        self.dp.message.register(self.cmd_removemember, Command("removemember"))
        self.dp.message.register(self.cmd_task, Command("task"))
        self.dp.message.register(self.cmd_allow, Command("allow"))
        self.dp.message.register(self.cmd_disallow, Command("disallow"))
        self.dp.message.register(self.cmd_project, Command("project"))
        self.dp.message.register(self.cmd_deleteproject, Command("deleteproject"))
        self.dp.message.register(self.cmd_role, Command("role"))

        # Callbacks
        self.dp.callback_query.register(self.callback_task_action, F.data.startswith("task_"))
        self.dp.callback_query.register(self.callback_tasks_page, F.data.startswith("tasks_page_"))
        self.dp.callback_query.register(self.callback_menu, F.data.startswith("menu_"))
        self.dp.callback_query.register(self.callback_remind, F.data.startswith("remind_"))
        self.dp.callback_query.register(self.callback_project_select, F.data.startswith("project_"))
        self.dp.callback_query.register(self.callback_dm_action, F.data.startswith("dm_"))
        self.dp.callback_query.register(self.callback_newtask_assignee, F.data.startswith("newtask_"))
        self.dp.callback_query.register(self.callback_comment, F.data.startswith("comment_"))
        self.dp.callback_query.register(self.callback_skip_status_comment, F.data.startswith("skipstatus_"))
        self.dp.callback_query.register(self.callback_confirm_delete, F.data.startswith("confirmdelete_"))
        self.dp.callback_query.register(self.callback_cancel_delete, F.data == "canceldelete")

        # Обычные сообщения (DM only — парсинг @username паттерна)
        self.dp.message.register(self.handle_message, F.text)

    async def setup_commands(self):
        """Настройка меню команд"""
        commands = [
            BotCommand(command="menu", description="📱 Главное меню"),
            BotCommand(command="mytasks", description="📋 Мои задачи"),
            BotCommand(command="tasks", description="📊 Все задачи проекта"),
            BotCommand(command="newproject", description="📁 Создать проект"),
            BotCommand(command="addmember", description="👤 Добавить участника"),
            BotCommand(command="task", description="🎯 Создать задачу"),
            BotCommand(command="project", description="🔀 Переключить проект"),
            BotCommand(command="stats", description="📈 Статистика"),
            BotCommand(command="remind", description="📢 Отправить напоминания (РП)"),
            BotCommand(command="weblogin", description="🔑 Код для входа в веб"),
            BotCommand(command="help", description="❓ Помощь"),
        ]
        await self.bot.set_my_commands(commands)

    def _get_user_role_in_project(self, db, user_id: int, project_id: int) -> Optional[Role]:
        """Получить роль пользователя в проекте"""
        user = crud.get_user(db, user_id)
        if user and user.is_superadmin:
            return Role.SUPERADMIN

        membership = crud.get_membership(db, user_id, project_id)
        return membership.role if membership else None

    def _can_create_tasks(self, role: Optional[Role]) -> bool:
        """Может ли пользователь создавать задачи"""
        return role in [Role.SUPERADMIN, Role.MANAGER]

    def _can_see_all_tasks(self, role: Optional[Role]) -> bool:
        """Может ли пользователь видеть все задачи"""
        return role in [Role.SUPERADMIN, Role.MANAGER]

    def _get_menu_flags(self, db, user: User, project=None) -> dict:
        """
        Определить флаги для меню на основе глобальной роли + роли в проекте.
        Returns: {"is_manager": bool, "is_admin": bool, "is_superadmin": bool}
        """
        is_superadmin = user.is_superadmin
        is_admin = user.can_create_projects or is_superadmin
        is_manager = is_admin  # admin всегда >= manager

        if project and not is_manager:
            role = self._get_user_role_in_project(db, user.id, project.id)
            is_manager = role in [Role.SUPERADMIN, Role.MANAGER]

        return {
            "is_manager": is_manager,
            "is_admin": is_admin,
            "is_superadmin": is_superadmin,
        }

    async def _get_project_for_dm(self, message: Message, db) -> Optional[tuple]:
        """
        Получить проект для команды в ЛС.
        Возвращает (project, user) или None если нужно выбрать проект.
        """
        if not message.from_user:
            return None

        user = crud.get_or_create_user(
            db,
            message.from_user.id,
            message.from_user.username,
            message.from_user.full_name
        )

        projects = crud.get_user_projects(db, user.id)

        if not projects:
            await message.reply(
                "У тебя нет проектов.\n"
                "Создай проект: /newproject Название проекта"
            )
            return None

        if len(projects) == 1:
            return (projects[0], user)

        # Несколько проектов - проверяем контекст из БД
        active_project = crud.get_active_project(db, user.id)
        if active_project and active_project in projects:
            return (active_project, user)

        # Показываем выбор проекта
        await message.reply(
            "📁 <b>Выбери проект:</b>",
            reply_markup=get_projects_keyboard(projects, "select")
        )
        return None

    async def _get_project_for_callback(self, callback: CallbackQuery, db) -> Optional[tuple]:
        """
        Получить проект для callback в ЛС.
        Возвращает (project, user) или None если нужно выбрать проект.
        """
        if not callback.from_user:
            return None

        user = crud.get_or_create_user(
            db,
            callback.from_user.id,
            callback.from_user.username,
            callback.from_user.full_name
        )

        projects = crud.get_user_projects(db, user.id)

        if not projects:
            await callback.message.answer(
                "У тебя нет проектов.\n"
                "Создай проект: /newproject Название проекта"
            )
            return None

        if len(projects) == 1:
            return (projects[0], user)

        # Несколько проектов - проверяем контекст из БД
        active_project = crud.get_active_project(db, user.id)
        if active_project and active_project in projects:
            return (active_project, user)

        # Показываем выбор проекта
        await callback.message.answer(
            "📁 <b>Выбери проект:</b>",
            reply_markup=get_projects_keyboard(projects, "select")
        )
        return None

    # ============ DM Helpers ============

    async def send_to_dm(self, user: User, text: str, reply_markup=None) -> bool:
        """Отправить сообщение в ЛС пользователю"""
        if user.telegram_id == 0:
            return False

        try:
            await self.bot.send_message(
                user.telegram_id,
                text,
                reply_markup=reply_markup
            )
            return True
        except Exception as e:
            logger.warning(f"Cannot send DM to {user.telegram_id}: {e}")
            return False

    async def notify_assignee(self, task: Task, project_name: str):
        """Уведомить исполнителя о новой задаче"""
        if task.assignee.telegram_id == 0:
            return

        text = (
            f"📋 <b>Новая задача!</b>\n\n"
            f"#{task.id}: {task.description[:100]}\n\n"
            f"👤 От: @{task.creator.username or task.creator.full_name}\n"
            f"📁 Проект: {project_name}"
        )

        try:
            await self.bot.send_message(
                task.assignee.telegram_id,
                text,
                reply_markup=get_task_keyboard(task.id, task.status)
            )
        except Exception as e:
            logger.warning(f"Failed to notify assignee: {e}")

    async def notify_managers_review(self, task: Task, project_id: int):
        """Уведомить менеджеров о задаче на проверке"""
        with get_db_session() as db:
            managers = crud.get_project_managers(db, project_id)
            project = crud.get_project(db, project_id)

            text = (
                f"📝 <b>Задача на проверке</b>\n\n"
                f"#{task.id}: {task.description[:100]}\n\n"
                f"👤 Исполнитель: @{task.assignee.username or task.assignee.full_name}\n"
                f"📁 Проект: {project.name if project else 'Unknown'}"
            )

            for manager in managers:
                if manager.telegram_id != 0:
                    try:
                        await self.bot.send_message(
                            manager.telegram_id,
                            text,
                            reply_markup=get_task_keyboard(task.id, task.status, is_manager=True)
                        )
                    except Exception as e:
                        logger.warning(f"Failed to notify manager {manager.id}: {e}")

    def _detect_priority(self, text: str) -> TaskPriority:
        """Определить приоритет из текста"""
        for keyword, prio in PRIORITY_KEYWORDS.items():
            if keyword in text.lower():
                return prio
        return TaskPriority.NORMAL

    # ============ Commands ============

    async def cmd_start(self, message: Message):
        """Команда /start — приветствие, показ проектов"""
        if not message.from_user:
            return

        # DM-only: если пишут из группы — отвечаем что бот работает только в ЛС
        if message.chat.type in ["group", "supergroup"]:
            bot_me = await self.bot.me()
            await message.reply(
                "Этот бот работает только в личных сообщениях.\n"
                f"Напиши мне в ЛС: @{bot_me.username}",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="💬 Написать боту", url=f"https://t.me/{bot_me.username}")]
                ])
            )
            return

        with get_db_session() as db:
            user = crud.get_or_create_user(
                db,
                message.from_user.id,
                message.from_user.username,
                message.from_user.full_name
            )
            projects = crud.get_user_projects(db, user.id)

            # Определяем флаги для меню
            # Для /start берём роль в первом/сохранённом проекте
            project = None
            if len(projects) == 1:
                project = projects[0]
            else:
                project = crud.get_active_project(db, user.id)
            flags = self._get_menu_flags(db, user, project)

            if projects:
                name = user.full_name or user.username or "друг"

                text = f"👋 Привет, {name}!\n\nТвои проекты:\n"
                for p in projects:
                    stats = crud.get_project_stats(db, p.id)
                    active = stats['pending_tasks'] + stats['in_progress_tasks']
                    text += f"📁 <b>{p.name}</b> — {active} активных\n"

                text += "\nВыбери проект или открой меню:"

                # Кнопки: проекты + меню
                kb_buttons = []
                for p in projects:
                    kb_buttons.append([
                        InlineKeyboardButton(text=f"📁 {p.name}", callback_data=f"project_select_{p.id}")
                    ])
                kb_buttons.append([InlineKeyboardButton(text="📱 Меню", callback_data="menu_show")])

                await message.reply(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_buttons))
            else:
                can_create = user.can_create_projects or user.is_superadmin
                text = "👋 Привет! Я бот для трекинга задач.\n\n"
                if can_create:
                    text += "Создай проект: /newproject Название\n"
                else:
                    text += "Тебя пока нет ни в одном проекте.\nПопроси руководителя добавить тебя.\n"

                text += "\n/help — справка"
                await message.reply(text, reply_markup=get_main_menu_keyboard(**flags))

    async def cmd_help(self, message: Message):
        """Справка"""
        help_text = """
📖 <b>Справка Task Tracker</b>

<b>📁 Проекты:</b>
/newproject &lt;название&gt; — создать проект
/addmember @nick [manager|executor] — добавить участника
/removemember @nick — удалить участника
/project — переключить активный проект

<b>🎯 Создание задач (только РП):</b>
/task @username описание задачи
<code>@username, описание задачи</code>

<b>📱 Команды:</b>
/menu — главное меню
/mytasks — мои задачи
/tasks — все задачи (для РП)
/stats — статистика
/done #123 — отметить задачу выполненной
/remind — отправить напоминания (РП)
/role @user manager|executor — сменить роль (РП)
/weblogin — код для входа в веб

<b>👑 Админ:</b>
/allow @nick — разрешить создание проектов
/disallow @nick — запретить создание проектов

<b>🎨 Приоритеты:</b>
<code>срочно</code>, <code>!!</code> → 🔴 Срочно
<code>важно</code>, <code>!</code> → 🟠 Важно

<b>👥 Роли:</b>
👑 Superadmin — доступ ко всем проектам
📋 Manager (РП) — управляет проектом
👤 Executor — видит только свои задачи
"""
        await message.reply(help_text)

    async def cmd_newproject(self, message: Message):
        """/newproject <название> — создать проект (whitelist)"""
        if not message.from_user:
            return

        if message.chat.type != "private":
            await message.reply("Эта команда работает только в ЛС.")
            return

        with get_db_session() as db:
            user = crud.get_or_create_user(
                db,
                message.from_user.id,
                message.from_user.username,
                message.from_user.full_name
            )

            if not user.can_create_projects and not user.is_superadmin:
                await message.reply("⛔ У тебя нет прав на создание проектов.\nПопроси администратора: /allow")
                return

            parts = message.text.split(maxsplit=1)
            if len(parts) < 2 or not parts[1].strip():
                await message.reply("Использование: /newproject Название проекта")
                return

            project_name = parts[1].strip()
            project = crud.create_dm_project(db, user.id, project_name)

            # Автоматически выбираем этот проект (сохраняем в БД)
            crud.set_active_project(db, user.id, project.id)

            await message.reply(
                f"✅ Проект <b>{project.name}</b> создан!\n\n"
                f"Ты — руководитель проекта.\n\n"
                f"Добавь участников:\n"
                f"/addmember @username\n\n"
                f"Создай задачу:\n"
                f"/task @username описание"
            )

    async def cmd_addmember(self, message: Message):
        """/addmember @nick [manager|executor] — добавить участника"""
        if not message.from_user:
            return

        if message.chat.type != "private":
            await message.reply("Эта команда работает только в ЛС.")
            return

        with get_db_session() as db:
            result = await self._get_project_for_dm(message, db)
            if not result:
                return
            project, user = result

            role = self._get_user_role_in_project(db, user.id, project.id)
            if not self._can_create_tasks(role):
                await message.reply("⛔ Только руководитель может добавлять участников.")
                return

            parts = message.text.split()
            if len(parts) < 2:
                await message.reply("Использование: /addmember @username [manager|executor]")
                return

            target_username = parts[1].lstrip("@")

            # Определяем роль
            member_role = Role.EXECUTOR
            if len(parts) >= 3:
                role_str = parts[2].lower()
                if role_str == "manager":
                    member_role = Role.MANAGER
                elif role_str != "executor":
                    await message.reply("Роль должна быть: manager или executor")
                    return

            membership = crud.add_member_by_username(db, project.id, target_username, member_role)
            role_name = "руководитель" if member_role == Role.MANAGER else "исполнитель"

            await message.reply(
                f"✅ @{target_username} добавлен в <b>{project.name}</b> как {role_name}"
            )

            # Уведомляем добавленного пользователя, если он реальный
            added_user = crud.get_user_by_username(db, target_username)
            if added_user and added_user.telegram_id != 0:
                await self.send_to_dm(
                    added_user,
                    f"📁 Тебя добавили в проект <b>{project.name}</b> как {role_name}.\n"
                    f"Используй /start чтобы увидеть свои проекты."
                )

    async def cmd_removemember(self, message: Message):
        """/removemember @nick — удалить участника"""
        if not message.from_user:
            return

        if message.chat.type != "private":
            await message.reply("Эта команда работает только в ЛС.")
            return

        with get_db_session() as db:
            result = await self._get_project_for_dm(message, db)
            if not result:
                return
            project, user = result

            role = self._get_user_role_in_project(db, user.id, project.id)
            if not self._can_create_tasks(role):
                await message.reply("⛔ Только руководитель может удалять участников.")
                return

            parts = message.text.split()
            if len(parts) < 2:
                await message.reply("Использование: /removemember @username")
                return

            target_username = parts[1].lstrip("@")
            target = crud.get_user_by_username(db, target_username)
            if not target:
                await message.reply(f"Пользователь @{target_username} не найден.")
                return

            if target.id == user.id:
                await message.reply("Нельзя удалить себя из проекта.")
                return

            if crud.remove_member(db, project.id, target.id):
                await message.reply(f"✅ @{target_username} удалён из <b>{project.name}</b>")
            else:
                await message.reply(f"@{target_username} не является участником проекта.")

    async def cmd_task(self, message: Message):
        """/task @nick описание — создать задачу"""
        if not message.from_user:
            return

        if message.chat.type != "private":
            await message.reply("Эта команда работает только в ЛС.")
            return

        with get_db_session() as db:
            result = await self._get_project_for_dm(message, db)
            if not result:
                return
            project, user = result

            role = self._get_user_role_in_project(db, user.id, project.id)
            if not self._can_create_tasks(role):
                await message.reply("⛔ Только руководитель может создавать задачи.")
                return

            # Парсим: /task @username описание
            text = message.text
            # Убираем /task
            text = re.sub(r"^/task\s*", "", text, count=1)
            match = TASK_PATTERN.match(text)
            if not match:
                await message.reply(
                    "Использование: /task @username описание задачи\n"
                    "Пример: /task @ivan подготовить отчёт"
                )
                return

            assignee_username = match.group(1)
            task_description = match.group(2).strip()
            if not task_description:
                await message.reply("Укажи описание задачи.")
                return

            await self._create_task_in_project(
                message, db, project, user, assignee_username, task_description
            )

    async def _create_task_in_project(
        self, message: Message, db, project, creator: User,
        assignee_username: str, task_description: str
    ):
        """Общая логика создания задачи в проекте"""
        priority = self._detect_priority(task_description)

        # Исполнитель
        assignee = crud.get_user_by_username(db, assignee_username)
        if not assignee:
            assignee = crud.create_placeholder_user(db, assignee_username)

        # Добавляем исполнителя в проект если его нет
        crud.ensure_project_membership(db, assignee, project.id, Role.EXECUTOR)

        # Создаём задачу
        task = crud.create_task(
            db,
            project_id=project.id,
            creator_id=creator.id,
            assignee_id=assignee.id,
            description=task_description,
            message_id=message.message_id,
            priority=priority
        )

        # Логируем в историю
        crud.log_task_history(
            db, task.id, creator.id,
            TaskHistoryAction.CREATED,
            None, f"Создана для @{assignee_username}"
        )

        p_emoji = PRIORITY_EMOJI.get(priority, "")

        # Подтверждение создателю
        await message.reply(
            f"{p_emoji} <b>Задача #{task.id}</b> создана!\n\n"
            f"📝 {task_description}\n\n"
            f"👤 Исполнитель: @{assignee_username}\n"
            f"📁 Проект: {project.name}",
            reply_markup=get_task_keyboard(task.id, task.status, is_manager=True)
        )

        # Уведомляем исполнителя
        await self.notify_assignee(task, project.name)

    async def cmd_allow(self, message: Message):
        """/allow @nick — разрешить создание проектов (superadmin)"""
        if not message.from_user:
            return

        with get_db_session() as db:
            sender = crud.get_or_create_user(
                db,
                message.from_user.id,
                message.from_user.username,
                message.from_user.full_name
            )
            if not sender.is_superadmin:
                await message.reply("⛔ Эта команда доступна только суперадмину.")
                return

            parts = message.text.split()
            if len(parts) < 2:
                await message.reply("Использование: /allow @username")
                return

            target_username = parts[1].lstrip("@")
            target = crud.get_user_by_username(db, target_username)
            if not target:
                target = crud.create_placeholder_user(db, target_username)

            crud.set_user_can_create_projects(db, target.id, True)
            await message.reply(f"✅ @{target_username} теперь может создавать проекты.")

    async def cmd_disallow(self, message: Message):
        """/disallow @nick — запретить создание проектов (superadmin)"""
        if not message.from_user:
            return

        with get_db_session() as db:
            sender = crud.get_or_create_user(
                db,
                message.from_user.id,
                message.from_user.username,
                message.from_user.full_name
            )
            if not sender.is_superadmin:
                await message.reply("⛔ Эта команда доступна только суперадмину.")
                return

            parts = message.text.split()
            if len(parts) < 2:
                await message.reply("Использование: /disallow @username")
                return

            target_username = parts[1].lstrip("@")
            target = crud.get_user_by_username(db, target_username)
            if not target:
                await message.reply(f"Пользователь @{target_username} не найден.")
                return

            crud.set_user_can_create_projects(db, target.id, False)
            await message.reply(f"✅ @{target_username} больше не может создавать проекты.")

    async def cmd_project(self, message: Message):
        """/project — переключить активный проект"""
        if not message.from_user:
            return

        if message.chat.type != "private":
            await message.reply("Эта команда работает только в ЛС.")
            return

        with get_db_session() as db:
            user = crud.get_or_create_user(
                db,
                message.from_user.id,
                message.from_user.username,
                message.from_user.full_name
            )
            projects = crud.get_user_projects(db, user.id)

            if not projects:
                await message.reply("У тебя нет проектов.\nСоздай: /newproject Название")
                return

            if len(projects) == 1:
                crud.set_active_project(db, user.id, projects[0].id)
                await message.reply(f"📁 Активный проект: <b>{projects[0].name}</b>")
                return

            # Показываем текущий контекст и выбор
            active_proj = crud.get_active_project(db, user.id)
            current_id = active_proj.id if active_proj else None
            text = "📁 <b>Выбери проект:</b>\n\n"
            for p in projects:
                marker = " ← текущий" if p.id == current_id else ""
                text += f"• {p.name}{marker}\n"

            await message.reply(text, reply_markup=get_projects_keyboard(projects, "select"))

    async def cmd_deleteproject(self, message: Message):
        """/deleteproject — удалить текущий проект (руководитель/superadmin)"""
        if not message.from_user:
            return

        if message.chat.type != "private":
            await message.reply("Эта команда работает только в ЛС.")
            return

        with get_db_session() as db:
            result = await self._get_project_for_dm(message, db)
            if not result:
                return
            project, user = result

            role = self._get_user_role_in_project(db, user.id, project.id)
            # Только создатель проекта или superadmin
            is_creator = project.created_by_user_id == user.id
            if not user.is_superadmin and not is_creator:
                await message.reply("⛔ Удалить проект может только его создатель или суперадмин.")
                return

            # Подтверждение через inline кнопки
            await message.reply(
                f"❗ Удалить проект <b>{project.name}</b>?\n\n"
                f"Все задачи останутся в базе, но проект станет неактивным.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [
                        InlineKeyboardButton(text="🗑 Да, удалить", callback_data=f"confirmdelete_{project.id}"),
                        InlineKeyboardButton(text="❌ Отмена", callback_data="canceldelete")
                    ]
                ])
            )

    async def cmd_menu(self, message: Message):
        """Главное меню"""
        flags = {"is_manager": False, "is_admin": False, "is_superadmin": False}
        if message.from_user:
            with get_db_session() as db:
                user = crud.get_or_create_user(db, message.from_user.id, message.from_user.username)
                projects = crud.get_user_projects(db, user.id)
                project = None
                if len(projects) == 1:
                    project = projects[0]
                else:
                    project = crud.get_active_project(db, user.id)
                flags = self._get_menu_flags(db, user, project)

        await message.reply(
            "📱 <b>Главное меню</b>",
            reply_markup=get_main_menu_keyboard(**flags)
        )

    async def cmd_tasks(self, message: Message):
        """Все задачи проекта (для РП)"""
        with get_db_session() as db:
            result = await self._get_project_for_dm(message, db)
            if not result:
                return
            project, user = result

            role = self._get_user_role_in_project(db, user.id, project.id)

            if not self._can_see_all_tasks(role):
                await message.reply("⛔ Только руководитель может видеть все задачи.\nИспользуй /mytasks")
                return

            tasks = crud.get_project_tasks(db, project.id)
            active_tasks = [t for t in tasks if t.status in [TaskStatus.PENDING, TaskStatus.IN_PROGRESS, TaskStatus.PENDING_REVIEW]]

            if not active_tasks:
                await message.reply(f"✅ <b>{project.name}</b>\nВсе задачи выполнены!")
                return

            text = f"📊 <b>{project.name}</b> — Задачи ({len(active_tasks)})"
            await message.reply(text, reply_markup=get_tasks_list_keyboard(active_tasks))

    async def cmd_mytasks(self, message: Message):
        """Мои задачи"""
        if not message.from_user:
            return

        with get_db_session() as db:
            result = await self._get_project_for_dm(message, db)
            if not result:
                return
            project, user = result

            tasks = crud.get_user_tasks(db, user.id, project.id)

            if not tasks:
                await message.reply("🎉 У тебя нет активных задач!")
                return

            dm_text = f"📋 <b>Твои задачи</b> ({len(tasks)})\n\n"
            for t in tasks:
                emoji = PRIORITY_EMOJI.get(t.priority, "")
                status = STATUS_EMOJI.get(t.status, "")
                dm_text += f"{emoji}{status} #{t.id}: {t.description[:50]}\n"

            await message.reply(dm_text, reply_markup=get_tasks_list_keyboard(tasks))

    async def cmd_done(self, message: Message):
        """Отметить задачу выполненной"""
        if not message.from_user:
            return

        parts = message.text.split()
        if len(parts) < 2:
            await message.reply("Укажи номер: /done 123")
            return

        try:
            task_id = int(parts[1].lstrip("#"))
        except ValueError:
            await message.reply("Неверный номер.")
            return

        with get_db_session() as db:
            task = crud.get_task(db, task_id)
            if not task:
                await message.reply(f"❌ Задача #{task_id} не найдена.")
                return

            user = crud.get_or_create_user(db, message.from_user.id, message.from_user.username)
            role = self._get_user_role_in_project(db, user.id, task.project_id)

            # Исполнитель может закрыть только свою, РП - любую
            if task.assignee_id != user.id and not self._can_see_all_tasks(role):
                await message.reply("⛔ Можно закрывать только свои задачи.")
                return

            crud.update_task_status_with_history(db, task_id, TaskStatus.DONE, user.id)
            await message.reply(f"✅ Задача #{task_id} выполнена!")

    async def cmd_stats(self, message: Message):
        """Статистика"""
        with get_db_session() as db:
            result = await self._get_project_for_dm(message, db)
            if not result:
                return
            project, user = result

            stats = crud.get_project_stats(db, project.id)
            rate = (stats["completed_tasks"] / stats["total_tasks"] * 100) if stats["total_tasks"] > 0 else 0
            filled = int(rate / 10)
            bar = "█" * filled + "░" * (10 - filled)

            text = f"""
📈 <b>{project.name}</b>

{bar} {rate:.0f}%

📊 Всего: {stats['total_tasks']}
⏳ Ожидают: {stats['pending_tasks']}
🔄 В работе: {stats['in_progress_tasks']}
✅ Выполнено: {stats['completed_tasks']}
👥 Участников: {stats['members_count']}
"""
            await message.reply(text)

    async def cmd_role(self, message: Message):
        """Сменить роль пользователя"""
        if not message.from_user:
            return

        parts = message.text.split()
        if len(parts) < 3:
            await message.reply("Использование: /role @username manager|executor")
            return

        target_username = parts[1].lstrip("@")
        new_role_str = parts[2].lower()

        role_map = {"manager": Role.MANAGER, "executor": Role.EXECUTOR}
        new_role = role_map.get(new_role_str)
        if not new_role:
            await message.reply("Роль должна быть: manager или executor")
            return

        with get_db_session() as db:
            result = await self._get_project_for_dm(message, db)
            if not result:
                return
            project, user = result

            sender_role = self._get_user_role_in_project(db, user.id, project.id)
            if not self._can_create_tasks(sender_role):
                await message.reply("⛔ Только руководитель может менять роли.")
                return

            target = crud.get_user_by_username(db, target_username)
            if not target:
                await message.reply(f"Пользователь @{target_username} не найден.")
                return

            membership = crud.update_member_role(db, target.id, project.id, new_role)
            if not membership:
                await message.reply(f"@{target_username} не участник проекта.")
                return

            role_name = "руководитель" if new_role == Role.MANAGER else "исполнитель"
            await message.reply(f"✅ @{target_username} теперь {role_name}!")

    async def cmd_remind(self, message: Message):
        """Отправить напоминания (для РП)"""
        if not message.from_user:
            return

        with get_db_session() as db:
            result = await self._get_project_for_dm(message, db)
            if not result:
                return
            project, user = result

            role = self._get_user_role_in_project(db, user.id, project.id)

            if not self._can_create_tasks(role):
                await message.reply("⛔ Только руководитель может отправлять напоминания.")
                return

            # Получаем участников с активными задачами
            members = crud.get_project_members(db, project.id)
            members_with_tasks = []
            for m in members:
                tasks = crud.get_user_tasks(db, m.user_id, project.id)
                if tasks:
                    members_with_tasks.append(m)

            if not members_with_tasks:
                await message.reply("Нет участников с активными задачами.")
                return

            await message.reply(
                "📢 <b>Отправить напоминания</b>\n\nВыбери кому:",
                reply_markup=get_remind_keyboard(project.id, members_with_tasks)
            )

    async def cmd_weblogin(self, message: Message):
        """Получить код для входа в веб"""
        if not message.from_user:
            return

        with get_db_session() as db:
            user = crud.get_or_create_user(
                db,
                message.from_user.id,
                message.from_user.username,
                message.from_user.full_name
            )

            auth_code = create_auth_code(db, user.id)

            await message.reply(
                f"🔑 <b>Код для входа в веб-интерфейс:</b>\n\n"
                f"<code>{auth_code.code}</code>\n\n"
                f"Код действителен 5 минут.\n"
                f"Введи его на странице входа.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🌐 Открыть сайт", url=WEBAPP_URL or "http://127.0.0.1:3010")]
                ])
            )

    # ============ Callbacks ============

    async def callback_task_action(self, callback: CallbackQuery):
        """Действия с задачей"""
        parts = callback.data.split("_")
        action = parts[1]
        task_id = int(parts[2])

        with get_db_session() as db:
            task = crud.get_task(db, task_id)
            if not task:
                await callback.answer("Задача не найдена", show_alert=True)
                return

            if action in ["info", "show"]:
                p_emoji = PRIORITY_EMOJI.get(task.priority, "")
                s_emoji = STATUS_EMOJI.get(task.status, "")
                assignee = f"@{task.assignee.username}" if task.assignee.username else task.assignee.full_name
                creator = f"@{task.creator.username}" if task.creator.username else task.creator.full_name

                # Получаем роль для правильной клавиатуры
                is_manager = False
                if callback.from_user:
                    user = crud.get_or_create_user(db, callback.from_user.id, callback.from_user.username)
                    role = self._get_user_role_in_project(db, user.id, task.project_id)
                    is_manager = self._can_see_all_tasks(role)

                due_info = ""
                if task.due_date:
                    due_info = f"\n⏰ Дедлайн: {task.due_date.strftime('%d.%m.%Y')}"

                text = (
                    f"{p_emoji} <b>Задача #{task.id}</b> {s_emoji}\n\n"
                    f"📝 {task.description}\n\n"
                    f"👤 Исполнитель: {assignee}\n"
                    f"📋 Создал: {creator}\n"
                    f"📅 {task.created_at.strftime('%d.%m.%Y %H:%M')}"
                    f"{due_info}"
                )

                # Показываем последние 3 комментария
                comments = crud.get_task_comments(db, task_id)
                if comments:
                    last_comments = comments[-3:]
                    text += "\n\n💬 <b>Комментарии:</b>"
                    for c in last_comments:
                        c_name = f"@{c.user.username}" if c.user.username else c.user.full_name or "?"
                        c_text = c.text[:100] + "..." if len(c.text) > 100 else c.text
                        text += f"\n{c_name}: {c_text}"
                    if len(comments) > 3:
                        text += f"\n<i>...и ещё {len(comments) - 3}</i>"

                keyboard = get_task_keyboard(task_id, task.status, is_manager)

                # Добавляем кнопку "К списку" если есть контекст
                if callback.from_user and callback.message.chat.type == "private":
                    menu_ctx = self.user_menu_context.get(callback.from_user.id)
                    if menu_ctx:
                        menu_labels = {"mytasks": "📋 К моим задачам", "tasks": "📊 К списку", "review": "📝 К проверке"}
                        label = menu_labels.get(menu_ctx["action"], "🔙 К списку")
                        keyboard.inline_keyboard.append([
                            InlineKeyboardButton(text=label, callback_data=f"dm_{menu_ctx['action']}_{menu_ctx['project_id']}")
                        ])

                await callback.message.edit_text(text, reply_markup=keyboard)
                await callback.answer()

            elif action in ["done", "progress", "pending", "review"]:
                if not callback.from_user:
                    return

                user = crud.get_or_create_user(db, callback.from_user.id, callback.from_user.username)
                role = self._get_user_role_in_project(db, user.id, task.project_id)
                is_manager = self._can_see_all_tasks(role)

                logger.info(f"Task action: user={user.username}, role={role}, is_manager={is_manager}, task_id={task_id}, action={action}, task_status={task.status}")

                # Проверяем права
                if task.assignee_id != user.id and not is_manager:
                    await callback.answer("⛔ Нет прав", show_alert=True)
                    return

                # Для done из PENDING_REVIEW нужно быть manager
                if action == "done" and task.status == TaskStatus.PENDING_REVIEW and not is_manager:
                    await callback.answer("⛔ Только руководитель может принять задачу", show_alert=True)
                    return

                status_map = {
                    "done": TaskStatus.DONE,
                    "progress": TaskStatus.IN_PROGRESS,
                    "pending": TaskStatus.PENDING,
                    "review": TaskStatus.PENDING_REVIEW
                }
                new_status = status_map[action]

                # Для значимых смен статуса спрашиваем комментарий
                if action in ["progress", "review", "done"]:
                    self.user_status_comment[callback.from_user.id] = {
                        "task_id": task_id,
                        "new_status": new_status,
                    }
                    prompts = {
                        "progress": "Что планируешь сделать?",
                        "review": "Что сделано?",
                        "done": "Итоговый комментарий?",
                    }
                    await callback.message.answer(
                        f"💬 {prompts[action]}\n"
                        f"<i>Напиши комментарий к задаче #{task_id} или /skip</i>",
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text="⏩ Пропустить", callback_data=f"skipstatus_{task_id}")]
                        ])
                    )
                    await callback.answer()
                    return

                # Для "pending" меняем сразу без вопросов
                crud.update_task_status_with_history(db, task_id, new_status, user.id)

                status_text = {
                    "done": "✅ Принято!",
                    "progress": "🔄 В работе",
                    "pending": "⏳ Отложено",
                    "review": "📝 На проверку!"
                }
                await callback.answer(status_text[action])

                # Уведомляем менеджеров если задача отправлена на проверку
                if new_status == TaskStatus.PENDING_REVIEW:
                    await self.notify_managers_review(task, task.project_id)

                # Проверяем контекст меню для возврата к списку
                menu_ctx = self.user_menu_context.get(callback.from_user.id)
                if menu_ctx and callback.message.chat.type == "private":
                    project_id = menu_ctx["project_id"]
                    menu_action = menu_ctx["action"]
                    project = crud.get_project(db, project_id)

                    back_button = InlineKeyboardButton(text="🔙 Назад", callback_data=f"project_select_{project_id}")

                    if menu_action == "mytasks":
                        tasks = crud.get_user_tasks(db, user.id, project_id)
                        if not tasks:
                            text = f"🎉 <b>{project.name}</b>\n\nУ тебя нет активных задач!"
                            await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[back_button]]))
                        else:
                            text = f"📋 <b>{project.name}</b> — Мои задачи ({len(tasks)})"
                            keyboard = get_tasks_list_keyboard(tasks)
                            keyboard.inline_keyboard.append([back_button])
                            await callback.message.edit_text(text, reply_markup=keyboard)

                    elif menu_action == "tasks":
                        tasks = crud.get_project_tasks(db, project_id)
                        active = [t for t in tasks if t.status in [TaskStatus.PENDING, TaskStatus.IN_PROGRESS, TaskStatus.PENDING_REVIEW]]
                        if not active:
                            text = f"✅ <b>{project.name}</b>\n\nВсе задачи выполнены!"
                            await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[back_button]]))
                        else:
                            text = f"📊 <b>{project.name}</b> — Все задачи ({len(active)})"
                            keyboard = get_tasks_list_keyboard(active)
                            keyboard.inline_keyboard.append([back_button])
                            await callback.message.edit_text(text, reply_markup=keyboard)

                    elif menu_action == "review":
                        tasks = crud.get_project_tasks(db, project_id)
                        review_tasks = [t for t in tasks if t.status == TaskStatus.PENDING_REVIEW]
                        if not review_tasks:
                            text = f"✅ <b>{project.name}</b>\n\nНет задач на проверке!"
                            await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[back_button]]))
                        else:
                            text = f"📝 <b>{project.name}</b> — На проверке ({len(review_tasks)})"
                            keyboard = get_tasks_list_keyboard(review_tasks)
                            keyboard.inline_keyboard.append([back_button])
                            await callback.message.edit_text(text, reply_markup=keyboard)
                else:
                    # Без контекста — показываем обновлённую задачу
                    task = crud.get_task(db, task_id)
                    p_emoji = PRIORITY_EMOJI.get(task.priority, "")
                    s_emoji = STATUS_EMOJI.get(task.status, "")
                    text = f"{p_emoji} <b>Задача #{task.id}</b> {s_emoji}\n\n{task.description}"

                    if task.status == TaskStatus.DONE:
                        await callback.message.edit_text(f"{text}\n\n✅ <i>Выполнено!</i>")
                    elif task.status == TaskStatus.PENDING_REVIEW:
                        await callback.message.edit_text(
                            f"{text}\n\n📝 <i>Ожидает проверки руководителя</i>",
                            reply_markup=get_task_keyboard(task_id, task.status, is_manager)
                        )
                    else:
                        await callback.message.edit_text(text, reply_markup=get_task_keyboard(task_id, task.status, is_manager))

    async def callback_tasks_page(self, callback: CallbackQuery):
        """Навигация по задачам"""
        page = int(callback.data.split("_")[2])

        with get_db_session() as db:
            # В DM-only — используем контекст проекта
            if callback.from_user:
                result = await self._get_project_for_callback(callback, db)
                if result:
                    project, user = result
                    tasks = crud.get_project_tasks(db, project.id)
                    active = [t for t in tasks if t.status in [TaskStatus.PENDING, TaskStatus.IN_PROGRESS, TaskStatus.PENDING_REVIEW]]
                    await callback.message.edit_reply_markup(reply_markup=get_tasks_list_keyboard(active, page))

        await callback.answer()

    async def callback_project_select(self, callback: CallbackQuery):
        """Выбор проекта"""
        parts = callback.data.split("_")
        # project_select_123
        if len(parts) < 3:
            await callback.answer("Ошибка", show_alert=True)
            return

        project_id = int(parts[2])

        if not callback.from_user:
            return

        with get_db_session() as db:
            project = crud.get_project(db, project_id)
            if not project:
                await callback.answer("Проект не найден", show_alert=True)
                return

            user = crud.get_or_create_user(
                db,
                callback.from_user.id,
                callback.from_user.username,
                callback.from_user.full_name
            )

            # Проверяем что пользователь член проекта
            membership = crud.get_membership(db, user.id, project_id)
            if not membership and not user.is_superadmin:
                await callback.answer("Нет доступа к проекту", show_alert=True)
                return

            # Сохраняем выбранный проект в БД
            crud.set_active_project(db, user.id, project_id)

            role = self._get_user_role_in_project(db, user.id, project_id)
            is_manager = self._can_see_all_tasks(role)
            flags = self._get_menu_flags(db, user, project)

            # Показываем меню проекта
            stats = crud.get_project_stats(db, project_id)

            if flags["is_superadmin"]:
                role_emoji, role_text = "👑", "Суперадмин"
            elif is_manager:
                role_emoji, role_text = "📋", "Руководитель"
            else:
                role_emoji, role_text = "👤", "Исполнитель"

            members = crud.get_project_members(db, project_id)

            text = (
                f"📁 <b>{project.name}</b>\n\n"
                f"{role_emoji} Роль: {role_text}\n"
                f"📊 Задач: {stats['pending_tasks'] + stats['in_progress_tasks']} активных\n"
                f"👥 Участников: {len(members)}\n\n"
                f"Выбери действие:"
            )

            buttons = [
                [InlineKeyboardButton(text="📋 Мои задачи", callback_data=f"dm_mytasks_{project_id}")],
            ]

            if is_manager:
                buttons.append([InlineKeyboardButton(text="🎯 Создать задачу", callback_data=f"dm_newtask_{project_id}")])
                buttons.append([InlineKeyboardButton(text="📊 Все задачи", callback_data=f"dm_tasks_{project_id}")])
                buttons.append([InlineKeyboardButton(text="📝 На проверке", callback_data=f"dm_review_{project_id}")])
                buttons.append([InlineKeyboardButton(text="📢 Напоминания", callback_data=f"dm_remind_{project_id}")])

            buttons.append([InlineKeyboardButton(text="📈 Статистика", callback_data=f"dm_stats_{project_id}")])

            # Управление проектом — для manager+ или создателя
            if is_manager or (project.created_by_user_id == user.id):
                buttons.append([InlineKeyboardButton(text="👥 Участники", callback_data=f"dm_members_{project_id}")])

            buttons.append([InlineKeyboardButton(text="🔑 Войти в веб", callback_data="dm_weblogin")])
            buttons.append([InlineKeyboardButton(text="🔙 К проектам", callback_data="dm_projects")])

            await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

        await callback.answer()

    async def callback_dm_action(self, callback: CallbackQuery):
        """Действия в меню проекта (ЛС)"""
        parts = callback.data.split("_")
        action = parts[1]

        if not callback.from_user:
            return

        with get_db_session() as db:
            user = crud.get_or_create_user(
                db,
                callback.from_user.id,
                callback.from_user.username,
                callback.from_user.full_name
            )

            if action == "projects":
                # Вернуться к списку проектов
                projects = crud.get_user_projects(db, user.id)
                if projects:
                    text = "📁 <b>Твои проекты:</b>\n\n"
                    for p in projects:
                        stats = crud.get_project_stats(db, p.id)
                        active = stats['pending_tasks'] + stats['in_progress_tasks']
                        text += f"📁 <b>{p.name}</b> — {active} активных\n"
                    text += "\nВыбери проект:"
                    await callback.message.edit_text(text, reply_markup=get_projects_keyboard(projects, "select"))
                else:
                    await callback.message.edit_text(
                        "У тебя нет проектов.\nСоздай: /newproject Название"
                    )
                await callback.answer()
                return

            if action == "weblogin":
                # Получить код для входа в веб
                auth_code = create_auth_code(db, user.id)
                text = (
                    f"🔑 <b>Код для входа:</b>\n\n"
                    f"<code>{auth_code.code}</code>\n\n"
                    f"Код действителен 5 минут."
                )
                back_buttons = [[InlineKeyboardButton(text="🌐 Открыть сайт", url=WEBAPP_URL or "http://127.0.0.1:3010")]]
                active_proj = crud.get_active_project(db, user.id)
                if active_proj:
                    back_buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data=f"project_select_{active_proj.id}")])
                else:
                    back_buttons.append([InlineKeyboardButton(text="🔙 К проектам", callback_data="dm_projects")])

                await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=back_buttons))
                await callback.answer()
                return

            # Для остальных действий нужен project_id
            if len(parts) < 3:
                await callback.answer("Ошибка", show_alert=True)
                return

            project_id = int(parts[2])
            project = crud.get_project(db, project_id)
            if not project:
                await callback.answer("Проект не найден", show_alert=True)
                return

            # Сохраняем контекст проекта при любом действии внутри него
            crud.set_active_project(db, user.id, project_id)

            role = self._get_user_role_in_project(db, user.id, project_id)
            is_manager = self._can_see_all_tasks(role)

            back_button = InlineKeyboardButton(text="🔙 Назад", callback_data=f"project_select_{project_id}")

            if action == "newtask":
                # Показать список участников проекта для выбора исполнителя
                if not is_manager:
                    await callback.answer("⛔ Только руководитель может создавать задачи", show_alert=True)
                    return

                members = crud.get_project_members(db, project_id)
                if not members:
                    await callback.message.edit_text(
                        f"👥 В проекте <b>{project.name}</b> нет участников.\n"
                        f"Добавь: /addmember @username",
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[back_button]])
                    )
                    await callback.answer()
                    return

                text = f"🎯 <b>Создать задачу</b> — {project.name}\n\nВыбери исполнителя:"
                buttons = []
                for m in members:
                    u = m.user
                    name = f"@{u.username}" if u.username else u.full_name or f"ID {u.telegram_id}"
                    role_e = ROLE_EMOJI.get(m.role, "👤")
                    buttons.append([
                        InlineKeyboardButton(
                            text=f"{role_e} {name}",
                            callback_data=f"newtask_{project_id}_{u.id}"
                        )
                    ])
                buttons.append([back_button])
                await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

            elif action == "mytasks":
                self.user_menu_context[callback.from_user.id] = {"action": "mytasks", "project_id": project_id}

                tasks = crud.get_user_tasks(db, user.id, project_id)
                if not tasks:
                    text = f"🎉 <b>{project.name}</b>\n\nУ тебя нет активных задач!"
                    await callback.message.edit_text(
                        text,
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[back_button]])
                    )
                else:
                    text = f"📋 <b>{project.name}</b> — Мои задачи ({len(tasks)})"
                    keyboard = get_tasks_list_keyboard(tasks)
                    keyboard.inline_keyboard.append([back_button])
                    await callback.message.edit_text(text, reply_markup=keyboard)

            elif action == "tasks":
                if not is_manager:
                    await callback.answer("⛔ Только руководитель", show_alert=True)
                    return

                self.user_menu_context[callback.from_user.id] = {"action": "tasks", "project_id": project_id}

                tasks = crud.get_project_tasks(db, project_id)
                active = [t for t in tasks if t.status in [TaskStatus.PENDING, TaskStatus.IN_PROGRESS, TaskStatus.PENDING_REVIEW]]

                if not active:
                    text = f"✅ <b>{project.name}</b>\n\nВсе задачи выполнены!"
                    await callback.message.edit_text(
                        text,
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[back_button]])
                    )
                else:
                    text = f"📊 <b>{project.name}</b> — Все задачи ({len(active)})"
                    keyboard = get_tasks_list_keyboard(active)
                    keyboard.inline_keyboard.append([back_button])
                    await callback.message.edit_text(text, reply_markup=keyboard)

            elif action == "review":
                if not is_manager:
                    await callback.answer("⛔ Только руководитель", show_alert=True)
                    return

                self.user_menu_context[callback.from_user.id] = {"action": "review", "project_id": project_id}

                tasks = crud.get_project_tasks(db, project_id)
                review_tasks = [t for t in tasks if t.status == TaskStatus.PENDING_REVIEW]

                if not review_tasks:
                    text = f"✅ <b>{project.name}</b>\n\nНет задач на проверке!"
                    await callback.message.edit_text(
                        text,
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[back_button]])
                    )
                else:
                    text = f"📝 <b>{project.name}</b> — На проверке ({len(review_tasks)})"
                    keyboard = get_tasks_list_keyboard(review_tasks)
                    keyboard.inline_keyboard.append([back_button])
                    await callback.message.edit_text(text, reply_markup=keyboard)

            elif action == "stats":
                stats = crud.get_project_stats(db, project_id)
                rate = (stats["completed_tasks"] / stats["total_tasks"] * 100) if stats["total_tasks"] > 0 else 0
                filled = int(rate / 10)
                bar = "█" * filled + "░" * (10 - filled)

                text = f"""
📈 <b>{project.name}</b>

{bar} {rate:.0f}%

📊 Всего: {stats['total_tasks']}
⏳ Ожидают: {stats['pending_tasks']}
🔄 В работе: {stats['in_progress_tasks']}
📝 На проверке: {stats.get('pending_review_tasks', 0)}
✅ Выполнено: {stats['completed_tasks']}
👥 Участников: {stats['members_count']}
"""
                await callback.message.edit_text(
                    text,
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[[back_button]])
                )

            elif action == "remind":
                if not is_manager:
                    await callback.answer("⛔ Только руководитель", show_alert=True)
                    return

                sent_count = await self.send_project_reminders(project_id)

                text = f"📢 <b>Напоминания отправлены!</b>\n\n✅ Отправлено: {sent_count} пользователям"
                await callback.message.edit_text(
                    text,
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[[back_button]])
                )

            elif action == "members":
                members = crud.get_project_members(db, project_id)
                text = f"👥 <b>Участники проекта {project.name}</b>\n\n"
                for m in members:
                    u = m.user
                    name = f"@{u.username}" if u.username else u.full_name or f"ID {u.telegram_id}"
                    r_emoji = ROLE_EMOJI.get(m.role, "")
                    r_name = "руководитель" if m.role == Role.MANAGER else "исполнитель"
                    text += f"{r_emoji} {name} — {r_name}\n"

                text += (
                    "\n<b>Управление:</b>\n"
                    "/addmember @nick [manager|executor]\n"
                    "/removemember @nick\n"
                    "/role @nick manager|executor\n"
                    "/deleteproject — удалить проект"
                )
                await callback.message.edit_text(
                    text,
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[[back_button]])
                )

        await callback.answer()

    async def callback_menu(self, callback: CallbackQuery):
        """Обработка меню"""
        action = callback.data.replace("menu_", "")

        if action == "mytasks":
            if not callback.from_user:
                await callback.answer()
                return

            with get_db_session() as db:
                result = await self._get_project_for_callback(callback, db)
                if not result:
                    await callback.answer()
                    return
                project, user = result

                tasks = crud.get_user_tasks(db, user.id, project.id)

                if not tasks:
                    await callback.message.answer("🎉 Нет активных задач!")
                else:
                    await callback.message.answer(
                        f"📋 <b>Твои задачи</b> ({len(tasks)})",
                        reply_markup=get_tasks_list_keyboard(tasks)
                    )

        elif action == "tasks":
            if not callback.from_user:
                await callback.answer()
                return

            with get_db_session() as db:
                result = await self._get_project_for_callback(callback, db)
                if not result:
                    await callback.answer()
                    return
                project, user = result

                role = self._get_user_role_in_project(db, user.id, project.id)
                if not self._can_see_all_tasks(role):
                    await callback.message.answer("⛔ Только руководитель может видеть все задачи.\nИспользуй /mytasks")
                    await callback.answer()
                    return

                tasks = crud.get_project_tasks(db, project.id)
                active_tasks = [t for t in tasks if t.status in [TaskStatus.PENDING, TaskStatus.IN_PROGRESS, TaskStatus.PENDING_REVIEW]]

                if not active_tasks:
                    await callback.message.answer(f"✅ <b>{project.name}</b>\nВсе задачи выполнены!")
                else:
                    await callback.message.answer(
                        f"📊 <b>{project.name}</b> — Задачи ({len(active_tasks)})",
                        reply_markup=get_tasks_list_keyboard(active_tasks)
                    )

        elif action == "stats":
            with get_db_session() as db:
                result = await self._get_project_for_callback(callback, db)
                if not result:
                    await callback.answer()
                    return
                project, user = result

                stats = crud.get_project_stats(db, project.id)
                rate = (stats["completed_tasks"] / stats["total_tasks"] * 100) if stats["total_tasks"] > 0 else 0
                filled = int(rate / 10)
                bar = "█" * filled + "░" * (10 - filled)

                text = (
                    f"📈 <b>{project.name}</b>\n\n"
                    f"{bar} {rate:.0f}%\n\n"
                    f"📊 Всего: {stats['total_tasks']}\n"
                    f"⏳ Ожидают: {stats['pending_tasks']}\n"
                    f"🔄 В работе: {stats['in_progress_tasks']}\n"
                    f"✅ Выполнено: {stats['completed_tasks']}\n"
                    f"👥 Участников: {stats['members_count']}"
                )
                await callback.message.answer(text)

        elif action == "remind":
            if not callback.from_user:
                await callback.answer()
                return

            with get_db_session() as db:
                result = await self._get_project_for_callback(callback, db)
                if not result:
                    await callback.answer()
                    return
                project, user = result

                role = self._get_user_role_in_project(db, user.id, project.id)
                if self._can_create_tasks(role):
                    members = crud.get_project_members(db, project.id)
                    await callback.message.answer(
                        "📢 Выбери кому отправить:",
                        reply_markup=get_remind_keyboard(project.id, members)
                    )
                else:
                    await callback.message.answer("⛔ Только для руководителей")

        elif action == "weblogin":
            if callback.from_user:
                with get_db_session() as db:
                    user = crud.get_or_create_user(db, callback.from_user.id, callback.from_user.username)
                    auth_code = create_auth_code(db, user.id)
                    await callback.message.answer(
                        f"🔑 Код: <code>{auth_code.code}</code>\n(5 минут)",
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text="🌐 Открыть", url=WEBAPP_URL or "http://127.0.0.1:3010")]
                        ])
                    )

        elif action == "show":
            # Показать главное меню (из кнопки)
            if callback.from_user:
                with get_db_session() as db:
                    user = crud.get_or_create_user(db, callback.from_user.id, callback.from_user.username)
                    projects = crud.get_user_projects(db, user.id)
                    project = None
                    if len(projects) == 1:
                        project = projects[0]
                    else:
                        project = crud.get_active_project(db, user.id)
                    flags = self._get_menu_flags(db, user, project)
                    await callback.message.answer(
                        "📱 <b>Главное меню</b>",
                        reply_markup=get_main_menu_keyboard(**flags)
                    )

        elif action == "myprojects":
            # Список проектов пользователя (admin+)
            if callback.from_user:
                with get_db_session() as db:
                    user = crud.get_or_create_user(db, callback.from_user.id, callback.from_user.username)
                    projects = crud.get_user_projects(db, user.id)

                    if not projects:
                        await callback.message.answer("У тебя нет проектов.\nСоздай: /newproject Название")
                    else:
                        text = "📁 <b>Твои проекты:</b>\n\n"
                        for p in projects:
                            stats = crud.get_project_stats(db, p.id)
                            active = stats['pending_tasks'] + stats['in_progress_tasks']
                            text += f"📁 <b>{p.name}</b> — {active} активных / {stats['members_count']} участников\n"
                        text += "\nВыбери проект:"
                        await callback.message.answer(text, reply_markup=get_projects_keyboard(projects, "select"))

        elif action == "newtask":
            # Создать задачу — показать список участников активного проекта
            if callback.from_user:
                with get_db_session() as db:
                    user = crud.get_or_create_user(db, callback.from_user.id, callback.from_user.username)
                    # Определяем активный проект
                    projects = crud.get_user_projects(db, user.id)
                    project = None
                    if len(projects) == 1:
                        project = projects[0]
                    else:
                        project = crud.get_active_project(db, user.id)

                    if not project:
                        await callback.message.answer(
                            "📁 <b>Сначала выбери проект:</b>",
                            reply_markup=get_projects_keyboard(projects, "select")
                        )
                    else:
                        role = self._get_user_role_in_project(db, user.id, project.id)
                        if not self._can_create_tasks(role):
                            await callback.message.answer("⛔ Только руководитель может создавать задачи.")
                        else:
                            members = crud.get_project_members(db, project.id)
                            if not members:
                                await callback.message.answer(
                                    f"👥 В проекте <b>{project.name}</b> нет участников.\n"
                                    f"Добавь: /addmember @username"
                                )
                            else:
                                text = f"🎯 <b>Создать задачу</b> — {project.name}\n\nВыбери исполнителя:"
                                buttons = []
                                for m in members:
                                    u = m.user
                                    name = f"@{u.username}" if u.username else u.full_name or f"ID {u.telegram_id}"
                                    role_e = ROLE_EMOJI.get(m.role, "👤")
                                    buttons.append([
                                        InlineKeyboardButton(
                                            text=f"{role_e} {name}",
                                            callback_data=f"newtask_{project.id}_{u.id}"
                                        )
                                    ])
                                buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data=f"newtask_cancel_{project.id}")])
                                await callback.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

        elif action == "newproject":
            # Подсказка создания проекта
            if callback.from_user:
                with get_db_session() as db:
                    user = crud.get_or_create_user(db, callback.from_user.id, callback.from_user.username)
                    if user.can_create_projects or user.is_superadmin:
                        await callback.message.answer(
                            "📁 <b>Создание проекта</b>\n\n"
                            "Отправь команду:\n"
                            "<code>/newproject Название проекта</code>"
                        )
                    else:
                        await callback.message.answer("⛔ У тебя нет прав на создание проектов.")

        elif action == "switchproject":
            # Переключить проект
            if callback.from_user:
                with get_db_session() as db:
                    user = crud.get_or_create_user(db, callback.from_user.id, callback.from_user.username)
                    projects = crud.get_user_projects(db, user.id)

                    if not projects:
                        await callback.message.answer("У тебя нет проектов.")
                    elif len(projects) == 1:
                        crud.set_active_project(db, user.id, projects[0].id)
                        await callback.message.answer(f"📁 Активный проект: <b>{projects[0].name}</b>")
                    else:
                        active_proj = crud.get_active_project(db, user.id)
                        current_id = active_proj.id if active_proj else None
                        text = "📁 <b>Выбери проект:</b>\n\n"
                        for p in projects:
                            marker = " ← текущий" if p.id == current_id else ""
                            text += f"• {p.name}{marker}\n"
                        await callback.message.answer(text, reply_markup=get_projects_keyboard(projects, "select"))

        elif action == "admin":
            # Панель суперадмина
            if callback.from_user:
                with get_db_session() as db:
                    user = crud.get_or_create_user(db, callback.from_user.id, callback.from_user.username)
                    if not user.is_superadmin:
                        await callback.message.answer("⛔ Только для суперадмина.")
                    else:
                        # Показываем список пользователей с правами
                        all_users = db.query(crud.User).filter(crud.User.telegram_id != 0).all()
                        admins = [u for u in all_users if u.can_create_projects or u.is_superadmin]

                        text = "👑 <b>Управление правами</b>\n\n"
                        text += "<b>Пользователи с правами:</b>\n"
                        for u in admins:
                            badge = "👑" if u.is_superadmin else "⚙️"
                            name = f"@{u.username}" if u.username else u.full_name or f"ID {u.telegram_id}"
                            text += f"{badge} {name}\n"

                        text += (
                            "\n<b>Команды:</b>\n"
                            "/allow @nick — дать право создавать проекты\n"
                            "/disallow @nick — забрать право"
                        )
                        await callback.message.answer(text)

        elif action == "help":
            help_text = """📖 <b>Справка Task Tracker</b>

<b>📁 Проекты:</b>
/newproject &lt;название&gt; — создать проект
/addmember @nick [manager|executor] — добавить участника
/removemember @nick — удалить участника
/deleteproject — удалить проект
/project — переключить проект

<b>🎯 Создание задач (РП):</b>
/task @username описание задачи
<code>@username, описание задачи</code>

<b>📱 Команды:</b>
/menu — главное меню
/mytasks — мои задачи
/tasks — все задачи (для РП)
/stats — статистика
/done #123 — выполнить задачу
/remind — напоминания (РП)
/role @user manager|executor — сменить роль (РП)
/weblogin — код для входа в веб

<b>👑 Админ:</b>
/allow @nick — дать права
/disallow @nick — забрать права

<b>🎨 Приоритеты:</b>
<code>срочно</code>, <code>!!</code> → 🔴 Срочно
<code>важно</code>, <code>!</code> → 🟠 Важно

<b>👥 Роли:</b>
👑 Superadmin — всё + управление правами
⚙️ Admin — создание проектов, управление
📋 Manager (РП) — управляет проектом
👤 Executor — видит только свои задачи"""
            await callback.message.answer(help_text)

        await callback.answer()

    async def callback_newtask_assignee(self, callback: CallbackQuery):
        """Выбран исполнитель для новой задачи: newtask_{project_id}_{user_id} или newtask_cancel_{project_id}"""
        parts = callback.data.split("_")
        if len(parts) < 3:
            await callback.answer("Ошибка", show_alert=True)
            return

        # Обработка отмены: newtask_cancel_{project_id}
        if parts[1] == "cancel":
            if callback.from_user:
                self.user_task_draft.pop(callback.from_user.id, None)
            project_id = int(parts[2])
            await callback.message.edit_text("❌ Создание задачи отменено.")
            await callback.answer()
            return

        project_id = int(parts[1])
        assignee_id = int(parts[2])

        if not callback.from_user:
            return

        with get_db_session() as db:
            user = crud.get_or_create_user(
                db, callback.from_user.id,
                callback.from_user.username, callback.from_user.full_name
            )
            project = crud.get_project(db, project_id)
            assignee = crud.get_user(db, assignee_id)

            if not project or not assignee:
                await callback.answer("Не найдено", show_alert=True)
                return

            role = self._get_user_role_in_project(db, user.id, project_id)
            if not self._can_create_tasks(role):
                await callback.answer("⛔ Нет прав", show_alert=True)
                return

            assignee_name = f"@{assignee.username}" if assignee.username else assignee.full_name or f"ID {assignee.telegram_id}"

            # Сохраняем черновик — ждём текст задачи
            self.user_task_draft[callback.from_user.id] = {
                "project_id": project_id,
                "assignee_id": assignee_id,
                "assignee_name": assignee_name,
            }

            back_button = InlineKeyboardButton(text="❌ Отмена", callback_data=f"newtask_cancel_{project_id}")

            await callback.message.edit_text(
                f"🎯 <b>Новая задача</b>\n\n"
                f"📁 Проект: {project.name}\n"
                f"👤 Исполнитель: {assignee_name}\n\n"
                f"✏️ <b>Напиши описание задачи</b> следующим сообщением:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[back_button]])
            )

        await callback.answer()

    async def callback_confirm_delete(self, callback: CallbackQuery):
        """Подтверждение удаления проекта"""
        parts = callback.data.split("_")
        if len(parts) < 2:
            await callback.answer("Ошибка", show_alert=True)
            return
        project_id = int(parts[1])

        if not callback.from_user:
            return

        with get_db_session() as db:
            user = crud.get_or_create_user(db, callback.from_user.id, callback.from_user.username)
            project = crud.get_project(db, project_id)
            if not project:
                await callback.answer("Проект не найден", show_alert=True)
                return

            is_creator = project.created_by_user_id == user.id
            if not user.is_superadmin and not is_creator:
                await callback.answer("⛔ Нет прав", show_alert=True)
                return

            name = project.name
            crud.delete_project(db, project_id)

            # Очищаем контекст если удалили текущий проект
            if user.active_project_id == project_id:
                user.active_project_id = None
                db.commit()

            await callback.message.edit_text(f"🗑 Проект <b>{name}</b> удалён.")

        await callback.answer()

    async def callback_cancel_delete(self, callback: CallbackQuery):
        """Отмена удаления проекта"""
        await callback.message.edit_text("❌ Удаление отменено.")
        await callback.answer()

    async def callback_comment(self, callback: CallbackQuery):
        """Кнопка 'Комментарий' — начать написание комментария"""
        parts = callback.data.split("_")
        # comment_add_{task_id}
        if len(parts) < 3 or parts[1] != "add":
            await callback.answer("Ошибка", show_alert=True)
            return

        task_id = int(parts[2])

        if not callback.from_user:
            return

        with get_db_session() as db:
            task = crud.get_task(db, task_id)
            if not task:
                await callback.answer("Задача не найдена", show_alert=True)
                return

        self.user_comment_draft[callback.from_user.id] = {"task_id": task_id}
        await callback.message.answer(
            f"✏️ Напиши комментарий к задаче <b>#{task_id}</b>:"
        )
        await callback.answer()

    async def callback_skip_status_comment(self, callback: CallbackQuery):
        """Пропустить комментарий при смене статуса"""
        parts = callback.data.split("_")
        # skipstatus_{task_id}
        if len(parts) < 2:
            await callback.answer("Ошибка", show_alert=True)
            return

        if not callback.from_user:
            return

        draft = self.user_status_comment.pop(callback.from_user.id, None)
        if not draft:
            await callback.answer("Нет активной смены статуса", show_alert=True)
            return

        task_id = draft["task_id"]
        new_status = draft["new_status"]

        with get_db_session() as db:
            user = crud.get_or_create_user(db, callback.from_user.id, callback.from_user.username)
            crud.update_task_status_with_history(db, task_id, new_status, user.id)

            task = crud.get_task(db, task_id)
            status_names = {
                TaskStatus.IN_PROGRESS: "🔄 В работе",
                TaskStatus.PENDING_REVIEW: "📝 На проверке",
                TaskStatus.DONE: "✅ Выполнено",
                TaskStatus.PENDING: "⏳ Ожидает",
            }
            status_text = status_names.get(new_status, str(new_status))

            await callback.message.edit_text(
                f"{status_text} — задача <b>#{task_id}</b>"
            )

            if new_status == TaskStatus.PENDING_REVIEW:
                await self.notify_managers_review(task, task.project_id)

        await callback.answer()

    async def notify_comment(self, db, task: Task, commenter_user_id: int, comment_text: str):
        """Уведомить о новом комментарии: исполнителя или менеджеров"""
        commenter = crud.get_user(db, commenter_user_id)
        commenter_name = f"@{commenter.username}" if commenter and commenter.username else (commenter.full_name if commenter else "?")
        notify_text = (
            f"💬 <b>Новый комментарий к задаче #{task.id}</b>\n\n"
            f"{commenter_name}: {comment_text[:200]}\n\n"
            f"📝 {task.description[:60]}"
        )

        if task.assignee_id == commenter_user_id:
            # Комментарий от исполнителя — уведомляем менеджеров
            managers = crud.get_project_managers(db, task.project_id)
            for manager in managers:
                if manager.telegram_id != 0 and manager.id != commenter_user_id:
                    try:
                        await self.bot.send_message(
                            manager.telegram_id, notify_text,
                            reply_markup=get_task_keyboard(task.id, task.status, is_manager=True)
                        )
                    except Exception as e:
                        logger.warning(f"Failed to notify manager about comment: {e}")
        else:
            # Комментарий от менеджера — уведомляем исполнителя
            if task.assignee and task.assignee.telegram_id != 0 and task.assignee_id != commenter_user_id:
                try:
                    await self.bot.send_message(
                        task.assignee.telegram_id, notify_text,
                        reply_markup=get_task_keyboard(task.id, task.status)
                    )
                except Exception as e:
                    logger.warning(f"Failed to notify assignee about comment: {e}")

    async def callback_remind(self, callback: CallbackQuery):
        """Обработка напоминаний"""
        parts = callback.data.split("_")
        action = parts[1]

        if action == "cancel":
            await callback.message.edit_text("❌ Отменено")
            await callback.answer()
            return

        if len(parts) < 3:
            await callback.answer("Ошибка", show_alert=True)
            return

        project_id = int(parts[2])

        if not callback.from_user:
            return

        with get_db_session() as db:
            project = crud.get_project(db, project_id)
            if not project:
                await callback.answer("Проект не найден", show_alert=True)
                return

            # Проверяем права — напоминания только для менеджеров
            sender = crud.get_or_create_user(db, callback.from_user.id, callback.from_user.username)
            sender_role = self._get_user_role_in_project(db, sender.id, project_id)
            if not self._can_create_tasks(sender_role):
                await callback.answer("⛔ Только руководитель", show_alert=True)
                return

            if action == "all":
                sent_count = await self.send_project_reminders(project_id)
                await callback.message.edit_text(f"✅ Напоминания отправлены {sent_count} пользователям!")

            elif action == "user" and len(parts) >= 4:
                user_id = int(parts[3])
                user = crud.get_user(db, user_id)
                if user and user.telegram_id != 0:
                    tasks = crud.get_user_tasks(db, user_id, project_id)
                    if tasks:
                        await self.send_reminder_to_user(user, tasks, project.name)
                        await callback.message.edit_text("✅ Напоминание отправлено!")
                    else:
                        await callback.answer("У пользователя нет задач", show_alert=True)
                else:
                    await callback.answer("Пользователь не найден", show_alert=True)

        await callback.answer()

    # ============ Message Handler ============

    async def handle_message(self, message: Message):
        """Обработка сообщений — черновик задачи или парсинг @username паттерна в DM"""
        # DM-only: игнорируем группы
        if message.chat.type != "private":
            return

        if not message.from_user or not message.text:
            return

        # Проверяем черновик комментария к смене статуса
        status_draft = self.user_status_comment.get(message.from_user.id)
        if status_draft:
            text = message.text.strip()
            if text.lower() == "/skip":
                # Пропустить — просто сменить статус
                self.user_status_comment.pop(message.from_user.id, None)
                with get_db_session() as db:
                    user = crud.get_or_create_user(db, message.from_user.id, message.from_user.username)
                    crud.update_task_status_with_history(db, status_draft["task_id"], status_draft["new_status"], user.id)
                    task = crud.get_task(db, status_draft["task_id"])
                    status_names = {
                        TaskStatus.IN_PROGRESS: "🔄 В работе",
                        TaskStatus.PENDING_REVIEW: "📝 На проверке",
                        TaskStatus.DONE: "✅ Выполнено",
                        TaskStatus.PENDING: "⏳ Ожидает",
                    }
                    await message.reply(f"{status_names.get(status_draft['new_status'], '✓')} — задача <b>#{status_draft['task_id']}</b>")
                    if status_draft["new_status"] == TaskStatus.PENDING_REVIEW:
                        await self.notify_managers_review(task, task.project_id)
                return
            else:
                # Сохраняем комментарий и меняем статус
                self.user_status_comment.pop(message.from_user.id, None)
                with get_db_session() as db:
                    user = crud.get_or_create_user(db, message.from_user.id, message.from_user.username, message.from_user.full_name)
                    crud.create_comment(db, status_draft["task_id"], user.id, text)
                    crud.update_task_status_with_history(db, status_draft["task_id"], status_draft["new_status"], user.id)
                    task = crud.get_task(db, status_draft["task_id"])
                    status_names = {
                        TaskStatus.IN_PROGRESS: "🔄 В работе",
                        TaskStatus.PENDING_REVIEW: "📝 На проверке",
                        TaskStatus.DONE: "✅ Выполнено",
                        TaskStatus.PENDING: "⏳ Ожидает",
                    }
                    await message.reply(
                        f"{status_names.get(status_draft['new_status'], '✓')} — задача <b>#{status_draft['task_id']}</b>\n"
                        f"💬 Комментарий сохранён"
                    )
                    if status_draft["new_status"] == TaskStatus.PENDING_REVIEW:
                        await self.notify_managers_review(task, task.project_id)
                    await self.notify_comment(db, task, user.id, text)
                return

        # Проверяем черновик комментария
        comment_draft = self.user_comment_draft.pop(message.from_user.id, None)
        if comment_draft:
            text = message.text.strip()
            if not text:
                self.user_comment_draft[message.from_user.id] = comment_draft
                await message.reply("✏️ Напиши текст комментария:")
                return

            task_id = comment_draft["task_id"]
            with get_db_session() as db:
                user = crud.get_or_create_user(db, message.from_user.id, message.from_user.username, message.from_user.full_name)
                crud.create_comment(db, task_id, user.id, text)
                task = crud.get_task(db, task_id)
                await message.reply(f"💬 Комментарий к задаче <b>#{task_id}</b> добавлен!")
                if task:
                    await self.notify_comment(db, task, user.id, text)
            return

        # Проверяем черновик задачи (пользователь выбрал исполнителя через кнопку)
        draft = self.user_task_draft.pop(message.from_user.id, None)
        if draft:
            task_description = message.text.strip()
            if not task_description:
                self.user_task_draft[message.from_user.id] = draft  # вернуть черновик
                await message.reply("✏️ Напиши описание задачи:")
                return

            with get_db_session() as db:
                user = crud.get_or_create_user(
                    db, message.from_user.id,
                    message.from_user.username, message.from_user.full_name
                )
                project = crud.get_project(db, draft["project_id"])
                assignee = crud.get_user(db, draft["assignee_id"])

                if not project or not assignee:
                    await message.reply("Ошибка: проект или исполнитель не найдены.")
                    return

                # Добавляем исполнителя в проект если его нет
                crud.ensure_project_membership(db, assignee, project.id, Role.EXECUTOR)

                priority = self._detect_priority(task_description)

                task = crud.create_task(
                    db,
                    project_id=project.id,
                    creator_id=user.id,
                    assignee_id=assignee.id,
                    description=task_description,
                    message_id=message.message_id,
                    priority=priority
                )

                crud.log_task_history(
                    db, task.id, user.id,
                    TaskHistoryAction.CREATED,
                    None, f"Создана для {draft['assignee_name']}"
                )

                p_emoji = PRIORITY_EMOJI.get(priority, "")

                await message.reply(
                    f"{p_emoji} <b>Задача #{task.id}</b> создана!\n\n"
                    f"📝 {task_description}\n\n"
                    f"👤 Исполнитель: {draft['assignee_name']}\n"
                    f"📁 Проект: {project.name}",
                    reply_markup=get_task_keyboard(task.id, task.status, is_manager=True)
                )

                await self.notify_assignee(task, project.name)
            return

        match = TASK_PATTERN.match(message.text)
        if not match:
            return

        assignee_username = match.group(1)
        task_description = match.group(2).strip()

        if not task_description:
            return

        with get_db_session() as db:
            user = crud.get_or_create_user(
                db,
                telegram_id=message.from_user.id,
                username=message.from_user.username,
                full_name=message.from_user.full_name
            )

            projects = crud.get_user_projects(db, user.id)
            if not projects:
                await message.reply("У тебя нет проектов. Создай: /newproject Название")
                return

            # Определяем проект
            project = None
            if len(projects) == 1:
                project = projects[0]
            else:
                active_proj = crud.get_active_project(db, user.id)
                if active_proj and active_proj in projects:
                    project = active_proj

            if not project:
                await message.reply(
                    "📁 <b>Выбери проект:</b>",
                    reply_markup=get_projects_keyboard(projects, "select")
                )
                return

            # Проверяем права
            role = self._get_user_role_in_project(db, user.id, project.id)
            if not self._can_create_tasks(role):
                await message.reply("⛔ Только руководитель может создавать задачи.")
                return

            await self._create_task_in_project(
                message, db, project, user, assignee_username, task_description
            )

    # ============ Reminders ============

    async def send_morning_reminders(self):
        """Утренние автоматические напоминания"""
        with get_db_session() as db:
            tasks = crud.get_pending_tasks_for_reminders(db)

            # Группируем по пользователям
            by_user = {}
            for task in tasks:
                if task.assignee.telegram_id == 0:
                    continue
                if task.assignee_id not in by_user:
                    by_user[task.assignee_id] = {"user": task.assignee, "tasks": []}
                by_user[task.assignee_id]["tasks"].append(task)

            for data in by_user.values():
                user = data["user"]
                user_tasks = data["tasks"]
                project_name = user_tasks[0].project.name if user_tasks[0].project else "Проект"
                try:
                    await self.send_reminder_to_user(user, user_tasks, project_name)
                except Exception as e:
                    logger.error(f"Failed morning reminder for user {user.id}: {e}")

    async def send_reminder_to_user(self, user: User, tasks: List[Task], project_name: str):
        """Публичный метод для отправки напоминания пользователю (вызывается из API)"""
        if not tasks or user.telegram_id == 0:
            return

        mention = f"@{user.username}" if user.username else user.full_name
        today = date.today()
        tomorrow = today + timedelta(days=1)

        # Разделяем задачи: горящие сверху
        burning = []
        tomorrow_tasks = []
        regular = []

        for t in tasks:
            if t.due_date:
                due = t.due_date.date() if isinstance(t.due_date, datetime) else t.due_date
                if due <= today:
                    burning.append(t)
                elif due == tomorrow:
                    tomorrow_tasks.append(t)
                else:
                    regular.append(t)
            else:
                regular.append(t)

        text = f"📢 <b>{mention}</b>, напоминание о задачах ({project_name}):\n\n"

        if burning:
            text += "🔥 <b>Горит сегодня:</b>\n"
            for t in burning:
                emoji = PRIORITY_EMOJI.get(t.priority, "")
                text += f"{emoji} #{t.id}: {t.description[:50]}\n"
            text += "\n"

        if tomorrow_tasks:
            text += "⏰ <b>Дедлайн завтра:</b>\n"
            for t in tomorrow_tasks:
                emoji = PRIORITY_EMOJI.get(t.priority, "")
                text += f"{emoji} #{t.id}: {t.description[:50]}\n"
            text += "\n"

        if regular:
            if burning or tomorrow_tasks:
                text += "📋 <b>Остальные:</b>\n"
            for t in regular:
                emoji = PRIORITY_EMOJI.get(t.priority, "")
                text += f"{emoji} #{t.id}: {t.description[:50]}\n"

        text += f"\n📊 Всего: {len(tasks)}"

        try:
            await self.bot.send_message(user.telegram_id, text, reply_markup=get_tasks_list_keyboard(tasks))
        except Exception as e:
            logger.error(f"Failed to send reminder to user {user.id}: {e}")

    async def send_project_reminders(self, project_id: int) -> int:
        """Публичный метод для отправки напоминаний всем участникам проекта (из API)"""
        sent_count = 0

        with get_db_session() as db:
            project = crud.get_project(db, project_id)
            if not project:
                return 0

            tasks = crud.get_pending_tasks_for_reminders(db, project_id)

            # Группируем по пользователям
            by_user = {}
            for task in tasks:
                if task.assignee_id not in by_user:
                    by_user[task.assignee_id] = {"user": task.assignee, "tasks": []}
                by_user[task.assignee_id]["tasks"].append(task)

            for data in by_user.values():
                user = data["user"]
                user_tasks = data["tasks"]

                if user.telegram_id == 0:
                    continue

                try:
                    await self.send_reminder_to_user(user, user_tasks, project.name)
                    sent_count += 1
                except Exception as e:
                    logger.error(f"Failed to send reminder: {e}")

        return sent_count

    async def start(self):
        """Запуск бота"""
        logger.info("Starting bot...")
        await self.setup_commands()
        await self.dp.start_polling(self.bot)
