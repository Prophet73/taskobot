"""
Скрипт миграции базы данных для новых функций:
- Добавляет колонки в таблицу projects
- Создаёт таблицы task_comments и task_history
"""
from sqlalchemy import text
from database import engine, init_db

def _add_column(conn, table, column_def, column_name):
    """Helper: добавить колонку если не существует"""
    try:
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column_def}"))
        print(f"✓ Добавлена колонка {table}.{column_name}")
    except Exception as e:
        if "duplicate column" in str(e).lower():
            print(f"- Колонка {table}.{column_name} уже существует")
        else:
            print(f"- {table}.{column_name}: {e}")


def _rebuild_projects_table(conn):
    """
    SQLite не поддерживает ALTER COLUMN.
    Пересоздаём таблицу projects с chat_id NULLABLE и unique index.
    """
    # Проверяем, нужна ли миграция (chat_id уже nullable?)
    try:
        conn.execute(text("INSERT INTO projects (name, created_at) VALUES ('__migration_test__', datetime('now'))"))
        # Если прошло — уже nullable, откатываем
        conn.execute(text("DELETE FROM projects WHERE name = '__migration_test__'"))
        print("- projects.chat_id уже nullable")
        return
    except Exception:
        # NOT NULL constraint — нужна миграция
        conn.rollback()

    print("Пересоздаю таблицу projects (chat_id -> nullable)...")

    conn.execute(text("""
        CREATE TABLE projects_new (
            id INTEGER PRIMARY KEY,
            chat_id BIGINT UNIQUE,
            name VARCHAR(255) NOT NULL,
            description TEXT,
            is_active BOOLEAN DEFAULT 1,
            created_by_user_id INTEGER REFERENCES users(id),
            created_at DATETIME,
            reminder_enabled BOOLEAN DEFAULT 1,
            reminder_time VARCHAR(5) DEFAULT '09:00',
            access_token VARCHAR(64) UNIQUE
        )
    """))

    conn.execute(text("""
        INSERT INTO projects_new (id, chat_id, name, description, is_active, created_at,
                                  reminder_enabled, reminder_time, access_token)
        SELECT id, chat_id, name, description, is_active, created_at,
               reminder_enabled, reminder_time, access_token
        FROM projects
    """))

    conn.execute(text("DROP TABLE projects"))
    conn.execute(text("ALTER TABLE projects_new RENAME TO projects"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_projects_id ON projects (id)"))
    conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_projects_chat_id ON projects (chat_id)"))

    print("✓ Таблица projects пересоздана с nullable chat_id")


def run_migration():
    print("Начинаю миграцию базы данных...")

    with engine.connect() as conn:
        # Проверяем и добавляем колонки в projects (для старых баз)
        _add_column(conn, "projects", "reminder_enabled BOOLEAN DEFAULT 1", "reminder_enabled")
        _add_column(conn, "projects", "reminder_time VARCHAR(5) DEFAULT '09:00'", "reminder_time")
        _add_column(conn, "projects", "access_token VARCHAR(64) UNIQUE", "access_token")
        _add_column(conn, "projects", "created_by_user_id INTEGER REFERENCES users(id)", "created_by_user_id")

        # DM-mode: can_create_projects на users
        _add_column(conn, "users", "can_create_projects BOOLEAN DEFAULT 0", "can_create_projects")
        _add_column(conn, "users", "active_project_id INTEGER REFERENCES projects(id)", "active_project_id")

        conn.commit()

    # SQLite: пересоздаём projects чтобы chat_id стал nullable
    with engine.connect() as conn:
        _rebuild_projects_table(conn)
        conn.commit()

    # project_tokens.member_id для привязки executor-токенов к участникам
    with engine.connect() as conn:
        _add_column(conn, "project_tokens", "member_id INTEGER REFERENCES users(id)", "member_id")
        conn.commit()

    # Создаём новые таблицы через SQLAlchemy (create_all не трогает существующие)
    print("\nСоздаю новые таблицы...")
    init_db()
    print("✓ Таблицы созданы/обновлены")

    # Миграция существующих access_token → project_tokens
    _migrate_access_tokens_to_project_tokens()

    print("\n✅ Миграция завершена успешно!")


def _migrate_access_tokens_to_project_tokens():
    """Мигрируем старые access_token из projects в новую таблицу project_tokens"""
    import secrets
    with engine.connect() as conn:
        # Проверяем, есть ли проекты с access_token, которых ещё нет в project_tokens
        try:
            rows = conn.execute(text(
                "SELECT id, access_token FROM projects WHERE access_token IS NOT NULL AND access_token != ''"
            )).fetchall()
        except Exception:
            print("- Нет колонки access_token для миграции")
            return

        migrated = 0
        for row in rows:
            project_id, token = row[0], row[1]
            # Проверяем, нет ли уже такого токена в project_tokens
            existing = conn.execute(text(
                "SELECT id FROM project_tokens WHERE token = :token"
            ), {"token": token}).fetchone()
            if not existing:
                conn.execute(text(
                    "INSERT INTO project_tokens (project_id, token, role, is_active, created_at) "
                    "VALUES (:project_id, :token, 'OBSERVER', 1, datetime('now'))"
                ), {"project_id": project_id, "token": token})
                migrated += 1

        conn.commit()
        if migrated:
            print(f"✓ Мигрировано {migrated} токенов из projects.access_token → project_tokens")
        else:
            print("- Нет токенов для миграции")

if __name__ == "__main__":
    run_migration()
