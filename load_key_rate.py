"""
load_key_rate.py
Загружает ключевую ставку ЦБ РФ (пока тестовое значение) в staging.key_rates.
"""
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime

# ===== ТВОЙ URI SUPABASE =====
DATABASE_URL = "postgresql://postgres.lxqmkvbtazjfqzkoumuk:17Vfylfdjitr@aws-1-eu-west-1.pooler.supabase.com:5432/postgres"
# ==============================

engine = create_engine(DATABASE_URL)

def load_key_rate():
    print(f"Вставляем тестовую ключевую ставку {datetime.now()}")

    with engine.connect() as conn:
        # Создаём таблицу, если её нет
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS staging.key_rates (
                date DATE PRIMARY KEY,
                rate NUMERIC
            )
        """))
        conn.commit()

        # Вставляем тестовую ставку 16% (потом заменим на реальный парсинг)
        conn.execute(
            text("INSERT INTO staging.key_rates (date, rate) VALUES (:date, :rate) ON CONFLICT (date) DO NOTHING"),
            {"date": datetime.now().date(), "rate": 16.0}
        )
        conn.commit()
    print("Тестовая ставка 16% добавлена")

if __name__ == "__main__":
    load_key_rate()