"""
load_fundamentals.py
Загружает фундаментальные показатели акций с smart‑lab.ru (включая дивидендную доходность).
"""
import requests
import pandas as pd
from sqlalchemy import create_engine
from datetime import datetime
import urllib3

# ===== ТВОЙ URI SUPABASE =====
DATABASE_URL = "postgresql://postgres.lxqmkvbtazjfqzkoumuk:17Vfylfdjitr@aws-1-eu-west-1.pooler.supabase.com:5432/postgres"
# ==============================

engine = create_engine(DATABASE_URL)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def load_fundamentals():
    print(f"Начинаем загрузку фундаментальных показателей {datetime.now()}")
    stocks_info = pd.read_sql("SELECT secid FROM staging.securities_info WHERE type = 'stock'", engine)
    moex_tickers = set(stocks_info['secid'].tolist())
    print(f"Акций в справочнике: {len(moex_tickers)}")

    url = "https://smart-lab.ru/q/shares_fundamental/"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    try:
        session = requests.Session()
        session.verify = False
        response = session.get(url, headers=headers)
        response.raise_for_status()

        dfs = pd.read_html(response.text, decimal=',')
        if not dfs:
            print("Таблицы не найдены")
            return

        df = None
        for tbl in dfs:
            if any('тикер' in str(c).lower() or 'ticker' in str(c).lower() for c in tbl.columns):
                df = tbl
                break
        if df is None:
            print("Не найдена таблица с тикером.")
            return

        print("Исходные столбцы:", df.columns.tolist())

        # Сначала выделим дивидендный столбец (ДД ао, %), чтобы избежать дублирования
        div_col_name = None
        for col in df.columns:
            if 'дд ао' in str(col).lower():
                div_col_name = col
                break
        # Если не нашли "ДД ао", берём любой столбец, содержащий "дд"
        if div_col_name is None:
            for col in df.columns:
                if 'дд' in str(col).lower():
                    div_col_name = col
                    break

        # Переименовываем только нужные столбцы, дивидендный столбец переименуем отдельно
        col_map = {}
        for col in df.columns:
            col_lower = str(col).lower().replace(' ', '')
            if 'тикер' in col_lower or 'ticker' in col_lower:
                col_map[col] = 'ticker'
            elif 'p/e' in col_lower or 'p_e' in col_lower or col_lower == 'pe':
                col_map[col] = 'pe'
            elif 'p/b' in col_lower or 'p_b' in col_lower or col_lower == 'pb':
                col_map[col] = 'pb'
            elif 'roe' in col_lower or 'рентабельность' in col_lower:
                col_map[col] = 'roe'
            elif 'выруч' in col_lower or 'reven' in col_lower:
                col_map[col] = 'revenue_growth'
            elif 'капит' in col_lower or 'market' in col_lower:
                col_map[col] = 'market_cap'

        # Применяем основной маппинг
        df = df.rename(columns=col_map)

        # Переименовываем выбранный дивидендный столбец
        if div_col_name:
            df = df.rename(columns={div_col_name: 'div_yield'})

        needed = ['ticker', 'pe', 'pb', 'roe', 'div_yield', 'revenue_growth', 'market_cap']
        available = [c for c in needed if c in df.columns]
        print("Найдены столбцы:", available)

        if 'ticker' not in available:
            print("Не найден столбец с тикером.")
            return

        # Оставляем только нужные столбцы, при этом если есть несколько div_yield – берём первый
        df = df[available].copy()
        # Если получилось несколько колонок с одинаковым именем, оставляем первую
        if 'div_yield' in df.columns and isinstance(df['div_yield'], pd.DataFrame):
            # Такое возможно при дублировании имён, берём первый столбец
            df['div_yield'] = df['div_yield'].iloc[:, 0]

        df['ticker'] = df['ticker'].astype(str).str.upper().str.strip()
        df = df[df['ticker'].isin(moex_tickers)]

        # Приведение чисел к float
        for col in ['pe', 'pb', 'roe', 'div_yield', 'revenue_growth', 'market_cap']:
            if col in df.columns:
                df[col] = df[col].astype(str).str.replace(',', '.').str.replace('%', '').str.replace(' ', '')
                df[col] = pd.to_numeric(df[col], errors='coerce')

        df = df.rename(columns={'ticker': 'secid'})
        print(f"Загружено {len(df)} записей с фундаментальными показателями")

        df['updated'] = datetime.now().date()
        df.to_sql('fundamentals', engine, schema='staging', if_exists='replace', index=False, method='multi')
        print("Данные успешно загружены в staging.fundamentals")

    except Exception as e:
        print(f"Ошибка при загрузке данных: {e}")

if __name__ == "__main__":
    load_fundamentals()