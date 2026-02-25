"""
Скрипт миграции базы данных для новых функций:
- Добавляет колонки в таблицу projects
- Создаёт таблицы task_comments и task_history
"""
from sqlalchemy import text
from database import engine, init_db

def run_migration():
    print("Начинаю миграцию базы данных...")

    with engine.connect() as conn:
        # Проверяем и добавляем колонки в projects
        try:
            conn.execute(text("ALTER TABLE projects ADD COLUMN reminder_enabled BOOLEAN DEFAULT 1"))
            print("✓ Добавлена колонка reminder_enabled")
        except Exception as e:
            if "duplicate column" in str(e).lower():
                print("- Колонка reminder_enabled уже существует")
            else:
                print(f"- reminder_enabled: {e}")

        try:
            conn.execute(text("ALTER TABLE projects ADD COLUMN reminder_time VARCHAR(5) DEFAULT '09:00'"))
            print("✓ Добавлена колонка reminder_time")
        except Exception as e:
            if "duplicate column" in str(e).lower():
                print("- Колонка reminder_time уже существует")
            else:
                print(f"- reminder_time: {e}")

        try:
            conn.execute(text("ALTER TABLE projects ADD COLUMN access_token VARCHAR(64) UNIQUE"))
            print("✓ Добавлена колонка access_token")
        except Exception as e:
            if "duplicate column" in str(e).lower():
                print("- Колонка access_token уже существует")
            else:
                print(f"- access_token: {e}")

        conn.commit()

    # Создаём новые таблицы через SQLAlchemy (create_all не трогает существующие)
    print("\nСоздаю новые таблицы...")
    init_db()
    print("✓ Таблицы task_comments и task_history созданы")

    print("\n✅ Миграция завершена успешно!")

if __name__ == "__main__":
    run_migration()
