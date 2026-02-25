/**
 * Russian localization for Task Tracker
 */
export const ru = {
  // Navigation
  nav: {
    dashboard: 'Панель',
    tasks: 'Задачи',
    logout: 'Выйти',
  },

  // Status labels
  status: {
    pending: 'Ожидает',
    in_progress: 'В работе',
    pending_review: 'На проверке',
    done: 'Выполнено',
    cancelled: 'Отменено',
    all: 'Все статусы',
  },

  // Priority labels
  priority: {
    urgent: 'Срочный',
    high: 'Высокий',
    normal: 'Обычный',
    low: 'Низкий',
  },

  // Role labels
  role: {
    superadmin: 'Суперадмин',
    manager: 'Руководитель',
    executor: 'Исполнитель',
  },

  // Actions
  actions: {
    start: 'Начать',
    done: 'Готово',
    toReview: 'На проверку',
    approve: 'Принять',
    reject: 'Вернуть',
    comment: 'Комментировать',
    sendReminders: 'Отправить напоминания',
    reset: 'Сбросить',
    save: 'Сохранить',
    cancel: 'Отмена',
    delete: 'Удалить',
    copy: 'Копировать',
    generate: 'Сгенерировать',
    createTask: 'Создать задачу',
    edit: 'Редактировать',
    deleteTask: 'Удалить задачу',
    addMember: 'Добавить участника',
    removeMember: 'Удалить',
    changeRole: 'Сменить роль',
  },

  // Dashboard page
  dashboard: {
    title: 'Панель управления',
    welcome: 'Добро пожаловать',
    totalTasks: 'Всего задач',
    completed: 'Выполнено',
    inProgress: 'В работе',
    completionRate: 'Выполнение',
    recentTasks: 'Последние задачи',
    noProjects: 'Нет проектов. Добавьте бота в группу Telegram.',
    noTasks: 'Нет задач.',
    projects: 'Проекты',
    viewAll: 'Смотреть все',
  },

  // Project page
  project: {
    members: 'Участники',
    tasks: 'Задачи',
    stats: 'Статистика',
    settings: 'Настройки',
    backToDashboard: 'Назад',
    notFound: 'Проект не найден',
    allTasks: 'Все задачи',
    pendingReview: 'На проверке',
    addMemberPlaceholder: '@username',
    removeConfirm: 'Удалить участника?',
    memberAdded: 'Участник добавлен',
    memberRemoved: 'Участник удалён',
    roleChanged: 'Роль изменена',
  },

  // Tasks page
  tasksPage: {
    title: 'Все задачи',
    allProjects: 'Все проекты',
    noTasksFound: 'Задачи не найдены',
    filterByProject: 'Фильтр по проекту',
    filterByStatus: 'Фильтр по статусу',
  },

  // Task card
  task: {
    assignee: 'Исполнитель',
    creator: 'Создал',
    created: 'Создано',
    updated: 'Обновлено',
    dueDate: 'Срок',
    waitingReview: 'Ожидает проверки',
    description: 'Описание',
    priority: 'Приоритет',
    selectAssignee: 'Выберите исполнителя',
    newTask: 'Новая задача',
    editTask: 'Редактирование задачи',
    deleteConfirm: 'Вы уверены, что хотите удалить эту задачу?',
  },

  // Login page
  login: {
    title: 'Трекер задач',
    subtitle: 'Введите код из Telegram бота',
    codePlaceholder: 'Код авторизации',
    button: 'Войти',
    checking: 'Проверка...',
    getCode: 'Получите код командой',
    inBot: 'в боте Telegram',
    invalidCode: 'Неверный или просроченный код',
  },

  // Comments
  comments: {
    title: 'Комментарии',
    add: 'Добавить комментарий',
    placeholder: 'Напишите комментарий...',
    noComments: 'Нет комментариев',
    send: 'Отправить',
  },

  // History
  history: {
    title: 'История изменений',
    actions: {
      created: 'Создана',
      status_changed: 'Статус изменён',
      assigned: 'Назначена',
      reassigned: 'Переназначена',
      comment_added: 'Добавлен комментарий',
      priority_changed: 'Приоритет изменён',
      due_date_changed: 'Срок изменён',
    },
  },

  // Settings
  settings: {
    title: 'Настройки проекта',
    reminders: 'Напоминания',
    reminderEnabled: 'Напоминания включены',
    reminderTime: 'Время напоминаний',
    accessToken: 'Токен доступа',
    generateToken: 'Сгенерировать токен',
    copyLink: 'Скопировать',
    linkCopied: 'Скопировано!',
    tokenDescription: 'Изолированный доступ к проекту по ссылке',
    accessTokens: 'Токены доступа',
    tokensDescription: 'Создайте ссылки с разным уровнем доступа',
    regenerateToken: 'Перегенерировать',
    revokeToken: 'Отозвать',
    revokeConfirm: 'Отозвать этот токен? Ссылка перестанет работать.',
    tokenRevoked: 'Токен отозван',
    tokenCreated: 'Токен создан',
    noTokens: 'Нет токенов',
  },

  // Token roles
  tokenRole: {
    observer: 'Наблюдатель',
    executor: 'Исполнитель',
    manager: 'Руководитель',
    observerDesc: 'Только просмотр — статистика, задачи, участники',
    executorDesc: 'Может менять статус задач (Начать, На проверку)',
    managerDesc: 'Полный доступ — создание задач, одобрение, отклонение',
  },

  // Errors
  errors: {
    loadFailed: 'Не удалось загрузить данные',
    saveFailed: 'Не удалось сохранить',
    accessDenied: 'Доступ запрещён',
    notFound: 'Не найдено',
    serverError: 'Ошибка сервера',
  },

  // Common
  common: {
    loading: 'Загрузка...',
    noData: 'Нет данных',
    confirm: 'Подтвердить',
    back: 'Назад',
    next: 'Далее',
    of: 'из',
  },
};

export default ru;
