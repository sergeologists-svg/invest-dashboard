"""
load_deposits.py
Временно загружает тестовую ставку по депозитам в staging.deposit_rates.
"""
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime

# ===== ТВОЙ URI SUPABASE =====
DATABASE_URL = "postgresql://postgres.lxqmkvbtazjfqzkoumuk:17Vfylfdjitr@aws-1-eu-west-1.pooler.supabase.com:5432/postgres"
# ==============================

engine = create_engine(DATABASE_URL)

def load_deposits():
    print(f"Загружаем тестовую депозитную ставку {datetime.now()}")

    with engine.connect() as conn:
        # Создаём таблицу, если её нет
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS staging.deposit_rates (
                id            SERIAL PRIMARY KEY,
                bank_name     TEXT,
                rate          NUMERIC,
                term_days     INT,
                published     DATE DEFAULT CURRENT_DATE
            )
        """))
        conn.commit()

        # Вставляем тестовую ставку 15% (потом заменим на реальную)
        conn.execute(
            text("INSERT INTO staging.deposit_rates (bank_name, rate, term_days, published) VALUES (:bank, :rate, :term, :pub)"),
            {
                "bank": "Топ-10 банков (средняя, тест)",
                "rate": 15.0,
                "term": 365,
                "pub": datetime.now().date()
            }
        )
        conn.commit()
    print("Тестовая ставка 15% добавлена")

if __name__ == "__main__":
    load_deposits()