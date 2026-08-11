"""
load_moex.py
Ежедневная загрузка дневных свечей ВСЕХ акций с MOEX + справочник названий.
"""
import apimoex
import requests
import pandas as pd
from sqlalchemy import create_engine
from datetime import datetime
import urllib3

# ===== ТВОЙ URI ИЗ SUPABASE (Direct connection) =====
DATABASE_URL = "postgresql://postgres.lxqmkvbtazjfqzkoumuk:17Vfylfdjitr@aws-1-eu-west-1.pooler.supabase.com:5432/postgres"
# ===================================================

engine = create_engine(DATABASE_URL)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def load_shares():
    """Загружает дневные свечи для ВСЕХ акций с MOEX в staging.stocks."""
    session = requests.Session()
    session.verify = False
    print(f"Начинаем загрузку акций {datetime.now()}")

    try:
        # 1. Получаем список всех бумаг на рынке акций
        securities = apimoex.get_board_securities(session, board='TQBR')
        df_sec = pd.DataFrame(securities)

        # 2. Берём все строки с непустым SECID
        shares = df_sec[df_sec['SECID'].notna()][['SECID', 'SHORTNAME']]
        print(f"Найдено акций: {len(shares)}")

        # 3. Сохраняем справочник названий (если ещё не сохраняли)
        info = shares[['SECID', 'SHORTNAME']].copy()
        info['type'] = 'stock'
        # Чтобы не дублировать записи, удаляем существующие
        existing_ids = pd.read_sql("SELECT secid FROM staging.securities_info", engine)
        info = info[~info['SECID'].isin(existing_ids['secid'])]
        if not info.empty:
            info.to_sql('securities_info', engine, schema='staging',
                        if_exists='append', index=False, method='multi')
            print(f"Добавлено {len(info)} новых названий в справочник")

        # 4. Загружаем свечи для всех тикеров
        all_tickers = shares['SECID'].tolist()
        print(f"Загружаем свечи для {len(all_tickers)} тикеров...")

        for ticker in all_tickers:
            try:
                candles = apimoex.get_board_candles(
                    session,
                    security=ticker,
                    board='TQBR',
                    interval=24,
                    start='2026-07-01',
                    end=None
                )
                if not candles:
                    continue

                df = pd.DataFrame(candles)
                df = df.rename(columns={
                    'begin': 'tradedate',
                    'open': 'open',
                    'high': 'high',
                    'low': 'low',
                    'close': 'close',
                    'volume': 'volume'
                })
                df = df[['tradedate', 'open', 'high', 'low', 'close', 'volume']]
                df.insert(0, 'secid', ticker)
                df['tradedate'] = pd.to_datetime(df['tradedate']).dt.date

                # Проверяем дубликаты
                existing = pd.read_sql(
                    f"SELECT tradedate FROM staging.stocks WHERE secid = '{ticker}'", engine
                )
                existing_dates = set(existing['tradedate'])
                new_df = df[~df['tradedate'].isin(existing_dates)]

                if not new_df.empty:
                    new_df.to_sql(
                        'stocks', engine, schema='staging',
                        if_exists='append', index=False, method='multi'
                    )
            except Exception as e:
                print(f"  Ошибка для {ticker}: {e}")
                continue

    except Exception as e:
        print(f"Ошибка при получении списка акций: {e}")

    print(f"Загрузка акций завершена {datetime.now()}")


if __name__ == "__main__":
    load_shares()