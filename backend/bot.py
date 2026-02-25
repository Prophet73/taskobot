"""
Telegram Bot for Task Tracking v2
С системой ролей и ручными напоминаниями
"""
import re
import logging
from datetime import datetime
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
        InlineKeyboardButton(text="📋 Подробнее", callback_data=f"task_info_{task_id}")
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


def get_main_menu_keyboard(is_manager: bool = False) -> InlineKeyboardMarkup:
    """Главное меню"""
    from aiogram.types import WebAppInfo

    buttons = [
        [InlineKeyboardButton(text="📋 Мои задачи", callback_data="menu_mytasks")],
        [InlineKeyboardButton(text="📊 Все задачи", callback_data="menu_tasks")],
        [InlineKeyboardButton(text="📈 Статистика", callback_data="menu_stats")],
    ]

    if is_manager:
        buttons.append([
            InlineKeyboardButton(text="📢 Отправить напоминания", callback_data="menu_remind")
        ])

    # WebApp кнопка или обычная авторизация
    if WEBAPP_URL:
        buttons.append([
            InlineKeyboardButton(text="🌐 Открыть панель", web_app=WebAppInfo(url=WEBAPP_URL))
        ])
    else:
        buttons.append([InlineKeyboardButton(text="🔑 Войти в веб", callback_data="menu_weblogin")])

    buttons.append([InlineKeyboardButton(text="❓ Помощь", callback_data="menu_help")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_projects_keyboard(projects: list, action: str = "select") -> InlineKeyboardMarkup:
    """Клавиатура выбора проекта (для ЛС)"""
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
        # Хранилище выбранного проекта для ЛС (user_id -> project_id)
        self.user_project_context = {}
        # Хранилище последнего раздела меню (user_id -> {"action": "mytasks/tasks/review", "project_id": 1})
        self.user_menu_context = {}
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
        self.dp.message.register(self.cmd_role, Command("role"))
        self.dp.message.register(self.cmd_remind, Command("remind"))
        self.dp.message.register(self.cmd_weblogin, Command("weblogin"))

        # Callbacks
        self.dp.callback_query.register(self.callback_task_action, F.data.startswith("task_"))
        self.dp.callback_query.register(self.callback_tasks_page, F.data.startswith("tasks_page_"))
        self.dp.callback_query.register(self.callback_menu, F.data.startswith("menu_"))
        self.dp.callback_query.register(self.callback_remind, F.data.startswith("remind_"))
        self.dp.callback_query.register(self.callback_project_select, F.data.startswith("project_"))
        self.dp.callback_query.register(self.callback_dm_action, F.data.startswith("dm_"))

        # Обычные сообщения
        self.dp.message.register(self.handle_message, F.text)

    async def setup_commands(self):
        """Настройка меню команд"""
        commands = [
            BotCommand(command="menu", description="📱 Главное меню"),
            BotCommand(command="mytasks", description="📋 Мои задачи"),
            BotCommand(command="tasks", description="📊 Все задачи проекта"),
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
            await message.reply("У тебя нет проектов. Сначала добавь бота в группу.")
            return None

        if len(projects) == 1:
            return (projects[0], user)

        # Несколько проектов - проверяем контекст
        saved_project_id = self.user_project_context.get(message.from_user.id)
        if saved_project_id:
            project = crud.get_project(db, saved_project_id)
            if project and project in projects:
                return (project, user)

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
            await callback.message.answer("У тебя нет проектов. Сначала добавь бота в группу.")
            return None

        if len(projects) == 1:
            return (projects[0], user)

        # Несколько проектов - проверяем контекст
        saved_project_id = self.user_project_context.get(callback.from_user.id)
        if saved_project_id:
            project = crud.get_project(db, saved_project_id)
            if project and project in projects:
                return (project, user)

        # Показываем выбор проекта
        await callback.message.answer(
            "📁 <b>Выбери проект:</b>",
            reply_markup=get_projects_keyboard(projects, "select")
        )
        return None

    # ============ DM & Admin Sync ============

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

    async def reply_with_dm_redirect(self, message: Message, dm_text: str, reply_markup=None):
        """Отправить краткий ответ в группу и детали в ЛС"""
        if message.chat.type not in ["group", "supergroup"]:
            # В личке просто отвечаем
            await message.reply(dm_text, reply_markup=reply_markup)
            return True

        if not message.from_user:
            return False

        with get_db_session() as db:
            user = crud.get_or_create_user(
                db,
                message.from_user.id,
                message.from_user.username,
                message.from_user.full_name
            )

            if await self.send_to_dm(user, dm_text, reply_markup):
                await message.reply("✉️ Ответил в личные сообщения")
                return True
            else:
                bot_me = await self.bot.me()
                await message.reply(
                    "❌ Не могу отправить в ЛС. Напиши мне /start в личку.",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="💬 Написать боту", url=f"https://t.me/{bot_me.username}")]
                    ])
                )
                return False

    async def sync_chat_admins(self, chat_id: int, project_id: int):
        """Синхронизация админов чата с ролью MANAGER"""
        try:
            admins = await self.bot.get_chat_administrators(chat_id)
            with get_db_session() as db:
                for admin in admins:
                    if admin.user.is_bot:
                        continue

                    user = crud.get_or_create_user(
                        db,
                        telegram_id=admin.user.id,
                        username=admin.user.username,
                        full_name=admin.user.full_name
                    )

                    membership = crud.get_membership(db, user.id, project_id)
                    if membership and membership.role == Role.EXECUTOR:
                        # Повышаем до MANAGER
                        crud.update_member_role(db, user.id, project_id, Role.MANAGER)
                        logger.info(f"Promoted admin {user.username} to MANAGER in project {project_id}")
                    elif not membership:
                        crud.add_member_to_project(db, user.id, project_id, Role.MANAGER)
                        logger.info(f"Added admin {user.username} as MANAGER to project {project_id}")
        except Exception as e:
            logger.error(f"Failed to sync chat admins: {e}")

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

    # ============ Commands ============

    async def cmd_start(self, message: Message):
        """Команда /start"""
        if message.chat.type not in ["group", "supergroup"]:
            # В ЛС показываем проекты пользователя
            if message.from_user:
                with get_db_session() as db:
                    user = crud.get_or_create_user(
                        db,
                        message.from_user.id,
                        message.from_user.username,
                        message.from_user.full_name
                    )
                    projects = crud.get_user_projects(db, user.id)

                    if projects:
                        text = "👋 Привет! Твои проекты:\n\n"
                        for p in projects:
                            stats = crud.get_project_stats(db, p.id)
                            active = stats['pending_tasks'] + stats['in_progress_tasks']
                            text += f"📁 <b>{p.name}</b> — {active} активных\n"

                        text += "\nВыбери проект:"
                        await message.reply(text, reply_markup=get_projects_keyboard(projects, "select"))
                    else:
                        await message.reply(
                            "👋 Привет! Я бот для трекинга задач.\n\n"
                            "Добавь меня в групповой чат проекта.\n"
                            "Используй /help для справки.",
                            reply_markup=get_main_menu_keyboard()
                        )
            return

        with get_db_session() as db:
            # Создаём/получаем проект
            project = crud.get_or_create_project(
                db,
                chat_id=message.chat.id,
                name=message.chat.title or f"Chat {message.chat.id}"
            )

            # Создаём/получаем пользователя
            if message.from_user:
                user = crud.get_or_create_user(
                    db,
                    telegram_id=message.from_user.id,
                    username=message.from_user.username,
                    full_name=message.from_user.full_name
                )

                # Первый кто написал /start - менеджер
                members = crud.get_project_members(db, project.id)
                if not members:
                    role = Role.MANAGER
                else:
                    role = Role.EXECUTOR

                crud.ensure_project_membership(db, user, project.id, role)

                role_text = "руководитель проекта" if role == Role.MANAGER else "участник"
                is_manager = role == Role.MANAGER

                # Синхронизируем админов чата
                await self.sync_chat_admins(message.chat.id, project.id)

        await message.reply(
            f"✅ Бот активирован для <b>{message.chat.title}</b>!\n"
            f"Ты добавлен как {role_text}.\n\n"
            f"<b>Создать задачу:</b>\n"
            f"<code>@username, описание задачи</code>\n\n"
            f"/menu - главное меню",
            reply_markup=get_main_menu_keyboard(is_manager)
        )

    async def cmd_menu(self, message: Message):
        """Главное меню"""
        is_manager = False
        if message.from_user:
            with get_db_session() as db:
                if message.chat.type in ["group", "supergroup"]:
                    project = crud.get_project_by_chat_id(db, message.chat.id)
                    if project:
                        user = crud.get_or_create_user(db, message.from_user.id, message.from_user.username)
                        role = self._get_user_role_in_project(db, user.id, project.id)
                        is_manager = self._can_create_tasks(role)
                else:
                    # В ЛС — проверяем роль в сохранённом или единственном проекте
                    user = crud.get_or_create_user(db, message.from_user.id, message.from_user.username)
                    projects = crud.get_user_projects(db, user.id)
                    project = None
                    if len(projects) == 1:
                        project = projects[0]
                    else:
                        saved_id = self.user_project_context.get(message.from_user.id)
                        if saved_id:
                            project = crud.get_project(db, saved_id)
                    if project:
                        role = self._get_user_role_in_project(db, user.id, project.id)
                        is_manager = self._can_create_tasks(role)

        await message.reply(
            "📱 <b>Главное меню</b>",
            reply_markup=get_main_menu_keyboard(is_manager)
        )

    async def cmd_help(self, message: Message):
        """Справка"""
        help_text = """
📖 <b>Справка Task Tracker</b>

<b>🎯 Создание задач (только РП):</b>
<code>@username, описание задачи</code>
<code>@ivan, срочно! подготовить отчёт</code>

<b>📱 Команды:</b>
/menu - главное меню
/mytasks - мои задачи
/tasks - все задачи (для РП)
/stats - статистика
/remind - отправить напоминания (РП)
/weblogin - код для входа в веб
/role @user manager|executor - сменить роль (РП)

<b>🎨 Приоритеты:</b>
<code>срочно</code>, <code>!!</code> → 🔴 Срочно
<code>важно</code>, <code>!</code> → 🟠 Важно

<b>👥 Роли:</b>
👑 Superadmin - доступ ко всем проектам
📋 Manager (РП) - управляет проектом
👤 Executor - видит только свои задачи
"""
        await message.reply(help_text)

    async def cmd_tasks(self, message: Message):
        """Все задачи проекта (для РП)"""
        with get_db_session() as db:
            # Поддержка ЛС
            if message.chat.type not in ["group", "supergroup"]:
                result = await self._get_project_for_dm(message, db)
                if not result:
                    return
                project, user = result
            else:
                project = crud.get_project_by_chat_id(db, message.chat.id)
                if not project:
                    await message.reply("Проект не найден. /start")
                    return
                if not message.from_user:
                    return
                user = crud.get_or_create_user(db, message.from_user.id, message.from_user.username)

            role = self._get_user_role_in_project(db, user.id, project.id)

            if not self._can_see_all_tasks(role):
                await message.reply("⛔ Только руководитель может видеть все задачи.\nИспользуй /mytasks")
                return

            tasks = crud.get_project_tasks(db, project.id)
            active_tasks = [t for t in tasks if t.status in [TaskStatus.PENDING, TaskStatus.IN_PROGRESS, TaskStatus.PENDING_REVIEW]]

            if not active_tasks:
                await message.reply(f"✅ <b>{project.name}</b>\nВсе задачи выполнены!")
                return

            # В ЛС отвечаем напрямую, в группе через DM redirect
            text = f"📊 <b>{project.name}</b> — Задачи ({len(active_tasks)})"
            if message.chat.type in ["group", "supergroup"]:
                await self.reply_with_dm_redirect(message, text, get_tasks_list_keyboard(active_tasks))
            else:
                await message.reply(text, reply_markup=get_tasks_list_keyboard(active_tasks))

    async def cmd_mytasks(self, message: Message):
        """Мои задачи"""
        if not message.from_user:
            return

        with get_db_session() as db:
            # Поддержка ЛС
            if message.chat.type not in ["group", "supergroup"]:
                result = await self._get_project_for_dm(message, db)
                if not result:
                    return
                project, user = result
            else:
                project = crud.get_project_by_chat_id(db, message.chat.id)
                if not project:
                    await message.reply("Проект не найден. /start")
                    return
                user = crud.get_or_create_user(
                    db,
                    message.from_user.id,
                    message.from_user.username,
                    message.from_user.full_name
                )
                crud.ensure_project_membership(db, user, project.id)

            tasks = crud.get_user_tasks(db, user.id, project.id)

            if not tasks:
                await message.reply("🎉 У тебя нет активных задач!")
                return

            # Формируем детальный текст для ЛС
            dm_text = f"📋 <b>Твои задачи</b> ({len(tasks)})\n\n"
            for t in tasks:
                emoji = PRIORITY_EMOJI.get(t.priority, "")
                status = STATUS_EMOJI.get(t.status, "")
                dm_text += f"{emoji}{status} #{t.id}: {t.description[:50]}\n"

            await self.reply_with_dm_redirect(
                message,
                dm_text,
                reply_markup=get_tasks_list_keyboard(tasks)
            )

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
            # Поддержка ЛС
            if message.chat.type not in ["group", "supergroup"]:
                result = await self._get_project_for_dm(message, db)
                if not result:
                    return
                project, user = result
            else:
                project = crud.get_project_by_chat_id(db, message.chat.id)
                if not project:
                    await message.reply("Проект не найден.")
                    return

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
            await self.reply_with_dm_redirect(message, text)

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
            project = crud.get_project_by_chat_id(db, message.chat.id)
            if not project:
                await message.reply("Проект не найден.")
                return

            # Проверяем права отправителя
            sender = crud.get_or_create_user(db, message.from_user.id, message.from_user.username)
            sender_role = self._get_user_role_in_project(db, sender.id, project.id)

            if not self._can_create_tasks(sender_role):
                await message.reply("⛔ Только руководитель может менять роли.")
                return

            # Находим целевого пользователя
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
            # Поддержка ЛС
            if message.chat.type not in ["group", "supergroup"]:
                result = await self._get_project_for_dm(message, db)
                if not result:
                    return
                project, user = result
            else:
                project = crud.get_project_by_chat_id(db, message.chat.id)
                if not project:
                    await message.reply("Проект не найден.")
                    return
                user = crud.get_or_create_user(db, message.from_user.id, message.from_user.username)
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

            dm_text = (
                f"🔑 <b>Код для входа в веб-интерфейс:</b>\n\n"
                f"<code>{auth_code.code}</code>\n\n"
                f"Код действителен 5 минут.\n"
                f"Введи его на странице входа."
            )
            dm_markup = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🌐 Открыть сайт", url=WEBAPP_URL or "http://127.0.0.1:3010")]
            ])

            await self.reply_with_dm_redirect(message, dm_text, dm_markup)

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

                text = f"""
{p_emoji} <b>Задача #{task.id}</b> {s_emoji}

📝 {task.description}

👤 Исполнитель: {assignee}
📋 Создал: {creator}
📅 {task.created_at.strftime('%d.%m.%Y %H:%M')}
"""
                keyboard = get_task_keyboard(task_id, task.status, is_manager)

                # Добавляем кнопку "К списку" в ЛС если есть контекст
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

                # Используем функцию с записью в историю
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
                    # В группе или без контекста - показываем обновлённую задачу
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
            project = crud.get_project_by_chat_id(db, callback.message.chat.id)
            if project:
                tasks = crud.get_project_tasks(db, project.id)
                active = [t for t in tasks if t.status in [TaskStatus.PENDING, TaskStatus.IN_PROGRESS, TaskStatus.PENDING_REVIEW]]
                await callback.message.edit_reply_markup(reply_markup=get_tasks_list_keyboard(active, page))

        await callback.answer()

    async def callback_project_select(self, callback: CallbackQuery):
        """Выбор проекта в ЛС"""
        parts = callback.data.split("_")
        # project_select_123
        if len(parts) < 3:
            await callback.answer("Ошибка", show_alert=True)
            return

        action = parts[1]
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
            if not membership:
                await callback.answer("Нет доступа к проекту", show_alert=True)
                return

            # Сохраняем выбранный проект
            self.user_project_context[callback.from_user.id] = project_id

            role = self._get_user_role_in_project(db, user.id, project_id)
            is_manager = self._can_see_all_tasks(role)

            # Показываем меню проекта
            stats = crud.get_project_stats(db, project_id)
            role_emoji = "📋" if is_manager else "👤"
            role_text = "Руководитель" if is_manager else "Исполнитель"

            text = (
                f"📁 <b>{project.name}</b>\n\n"
                f"{role_emoji} Роль: {role_text}\n"
                f"📊 Задач: {stats['pending_tasks'] + stats['in_progress_tasks']} активных\n\n"
                f"Выбери действие:"
            )

            buttons = [
                [InlineKeyboardButton(text="📋 Мои задачи", callback_data=f"dm_mytasks_{project_id}")],
            ]

            if is_manager:
                buttons.append([InlineKeyboardButton(text="📊 Все задачи", callback_data=f"dm_tasks_{project_id}")])
                buttons.append([InlineKeyboardButton(text="📝 На проверке", callback_data=f"dm_review_{project_id}")])
                buttons.append([InlineKeyboardButton(text="📢 Напоминания", callback_data=f"dm_remind_{project_id}")])

            buttons.append([InlineKeyboardButton(text="📈 Статистика", callback_data=f"dm_stats_{project_id}")])
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
                # Кнопка назад к последнему проекту
                back_buttons = [[InlineKeyboardButton(text="🌐 Открыть сайт", url=WEBAPP_URL or "http://127.0.0.1:3010")]]
                saved_project = self.user_project_context.get(callback.from_user.id)
                if saved_project:
                    back_buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data=f"project_select_{saved_project}")])
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

            role = self._get_user_role_in_project(db, user.id, project_id)
            is_manager = self._can_see_all_tasks(role)

            back_button = InlineKeyboardButton(text="🔙 Назад", callback_data=f"project_select_{project_id}")

            if action == "mytasks":
                # Сохраняем контекст меню
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

                # Сохраняем контекст меню
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

                # Сохраняем контекст меню
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

                # Отправляем напоминания всем с активными задачами
                sent_count = await self.send_project_reminders(project_id)

                text = f"📢 <b>Напоминания отправлены!</b>\n\n✅ Отправлено: {sent_count} пользователям"
                await callback.message.edit_text(
                    text,
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[[back_button]])
                )

        await callback.answer()

    async def _resolve_project_for_callback(self, callback: CallbackQuery, db):
        """
        Определить проект для callback: в группе — по chat_id, в ЛС — через контекст.
        Возвращает (project, user) или None.
        """
        is_dm = callback.message.chat.type not in ["group", "supergroup"]

        if is_dm:
            return await self._get_project_for_callback(callback, db)
        else:
            project = crud.get_project_by_chat_id(db, callback.message.chat.id)
            if not project:
                await callback.message.answer("Проект не найден.")
                return None
            user = crud.get_or_create_user(
                db, callback.from_user.id,
                callback.from_user.username,
                callback.from_user.full_name
            )
            crud.ensure_project_membership(db, user, project.id)
            return (project, user)

    async def callback_menu(self, callback: CallbackQuery):
        """Обработка меню"""
        action = callback.data.replace("menu_", "")

        if action == "mytasks":
            if not callback.from_user:
                await callback.answer()
                return

            with get_db_session() as db:
                result = await self._resolve_project_for_callback(callback, db)
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
                result = await self._resolve_project_for_callback(callback, db)
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
                result = await self._resolve_project_for_callback(callback, db)
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
                result = await self._resolve_project_for_callback(callback, db)
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

        elif action == "help":
            help_text = """📖 <b>Справка Task Tracker</b>

<b>🎯 Создание задач (только РП):</b>
<code>@username, описание задачи</code>
<code>@ivan, срочно! подготовить отчёт</code>

<b>📱 Команды:</b>
/menu - главное меню
/mytasks - мои задачи
/tasks - все задачи (для РП)
/stats - статистика
/remind - отправить напоминания (РП)
/weblogin - код для входа в веб
/role @user manager|executor - сменить роль (РП)

<b>🎨 Приоритеты:</b>
<code>срочно</code>, <code>!!</code> → 🔴 Срочно
<code>важно</code>, <code>!</code> → 🟠 Важно

<b>👥 Роли:</b>
👑 Superadmin - доступ ко всем проектам
📋 Manager (РП) - управляет проектом
👤 Executor - видит только свои задачи"""
            await callback.message.answer(help_text)

        await callback.answer()

    async def callback_remind(self, callback: CallbackQuery):
        """Обработка напоминаний"""
        parts = callback.data.split("_")
        action = parts[1]

        if action == "cancel":
            await callback.message.edit_text("❌ Отменено")
            await callback.answer()
            return

        project_id = int(parts[2])

        with get_db_session() as db:
            project = crud.get_project(db, project_id)
            if not project:
                await callback.answer("Проект не найден", show_alert=True)
                return

            if action == "all":
                # Отправить всем
                tasks = crud.get_pending_tasks_for_reminders(db, project_id)
                await self._send_reminders_for_tasks(tasks, project.chat_id)
                await callback.message.edit_text("✅ Напоминания отправлены всем!")

            elif action == "user":
                user_id = int(parts[3])
                tasks = crud.get_user_tasks(db, user_id, project_id)
                if tasks:
                    await self._send_reminder_to_user(db, tasks, project.chat_id)
                    await callback.message.edit_text("✅ Напоминание отправлено!")
                else:
                    await callback.answer("У пользователя нет задач", show_alert=True)

        await callback.answer()

    # ============ Message Handler ============

    async def handle_message(self, message: Message):
        """Обработка сообщений для создания задач"""
        if message.chat.type not in ["group", "supergroup"]:
            return

        if not message.from_user or not message.text:
            return

        match = TASK_PATTERN.match(message.text)
        if not match:
            return

        assignee_username = match.group(1)
        task_description = match.group(2).strip()

        if not task_description:
            return

        # Определяем приоритет
        priority = TaskPriority.NORMAL
        for keyword, prio in PRIORITY_KEYWORDS.items():
            if keyword in task_description.lower():
                priority = prio
                break

        with get_db_session() as db:
            project = crud.get_or_create_project(
                db,
                chat_id=message.chat.id,
                name=message.chat.title or f"Chat {message.chat.id}"
            )

            # Создатель задачи
            creator = crud.get_or_create_user(
                db,
                telegram_id=message.from_user.id,
                username=message.from_user.username,
                full_name=message.from_user.full_name
            )

            # Проверяем права создателя
            role = self._get_user_role_in_project(db, creator.id, project.id)
            if role is None:
                # Первый раз - добавляем как executor
                crud.add_member_to_project(db, creator.id, project.id, Role.EXECUTOR)
                role = Role.EXECUTOR

            if not self._can_create_tasks(role):
                await message.reply("⛔ Только руководитель может ставить задачи.")
                return

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

            # Логируем создание в историю
            crud.log_task_history(
                db, task.id, creator.id,
                TaskHistoryAction.CREATED,
                None, f"Создана для @{assignee_username}"
            )

            p_emoji = PRIORITY_EMOJI.get(priority, "")

            # Краткое подтверждение в группе
            await message.reply(
                f"{p_emoji} Задача #{task.id} создана для @{assignee_username}"
            )

            # Полные детали создателю в ЛС
            dm_text = (
                f"{p_emoji} <b>Задача #{task.id}</b>\n\n"
                f"📝 {task_description}\n\n"
                f"👤 Исполнитель: @{assignee_username}\n"
                f"📁 Проект: {project.name}"
            )
            await self.send_to_dm(creator, dm_text, get_task_keyboard(task.id, task.status))

            # Уведомляем исполнителя в ЛС
            await self.notify_assignee(task, project.name)

    # ============ Reminders ============

    async def _send_reminder_to_user(self, db, tasks: List[Task], chat_id: int):
        """Отправить напоминание одному пользователю в ЛС"""
        if not tasks:
            return

        user = tasks[0].assignee
        if user.telegram_id == 0:
            return

        project = tasks[0].project
        project_name = project.name if project else "Проект"

        text = f"📢 <b>Напоминание о задачах</b>\n📁 {project_name}\n\n"
        for t in tasks:
            emoji = PRIORITY_EMOJI.get(t.priority, "")
            status = STATUS_EMOJI.get(t.status, "")
            text += f"{emoji}{status} #{t.id}: {t.description[:50]}\n"

        text += f"\n📊 Всего: {len(tasks)}"

        try:
            # Отправляем в ЛС пользователю вместо группы
            await self.bot.send_message(
                user.telegram_id,
                text,
                reply_markup=get_tasks_list_keyboard(tasks)
            )
        except Exception as e:
            logger.error(f"Failed to send reminder to user {user.telegram_id}: {e}")

    async def _send_reminders_for_tasks(self, tasks: List[Task], chat_id: int):
        """Отправить напоминания по задачам (группировка по пользователям)"""
        by_user = {}
        for task in tasks:
            if task.assignee_id not in by_user:
                by_user[task.assignee_id] = []
            by_user[task.assignee_id].append(task)

        for user_id, user_tasks in by_user.items():
            with get_db_session() as db:
                await self._send_reminder_to_user(db, user_tasks, chat_id)

    async def send_morning_reminders(self):
        """Утренние автоматические напоминания"""
        with get_db_session() as db:
            tasks = crud.get_pending_tasks_for_reminders(db)

            by_project = {}
            for task in tasks:
                if task.project_id not in by_project:
                    by_project[task.project_id] = {"chat_id": task.project.chat_id, "tasks": []}
                by_project[task.project_id]["tasks"].append(task)

            for data in by_project.values():
                await self._send_reminders_for_tasks(data["tasks"], data["chat_id"])

    async def send_reminder_to_user(self, user: User, tasks: List[Task], project_name: str):
        """Публичный метод для отправки напоминания пользователю (вызывается из API)"""
        if not tasks or user.telegram_id == 0:
            return

        mention = f"@{user.username}" if user.username else user.full_name

        text = f"📢 <b>{mention}</b>, напоминание о задачах ({project_name}):\n\n"
        for t in tasks:
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
