"""
load_moex.py
Ежедневная загрузка дневных свечей акций с Московской биржи (MOEX) в облачную БД Supabase.
"""
import apimoex
import requests
import pandas as pd
from sqlalchemy import create_engine
from datetime import datetime
import urllib3

# ===== ВСТАВЬ СВОЙ URI ИЗ SUPABASE (Direct connection) =====
DATABASE_URL = "postgresql://postgres.lxqmkvbtazjfqzkoumuk:17Vfylfdjitr@aws-1-eu-west-1.pooler.supabase.com:5432/postgres"
# ===========================================================

engine = create_engine(DATABASE_URL)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def load_shares():
    """Загружает дневные свечи для списка акций с MOEX в staging.stocks."""
    session = requests.Session()
    session.verify = False
    print(f"Начинаем загрузку {datetime.now()}")

    try:
        # 1. Получаем все бумаги на рынке акций (board='TQBR')
        securities = apimoex.get_board_securities(session, board='TQBR')
        df_sec = pd.DataFrame(securities)

        # Показываем, какие столбцы пришли (для диагностики, можно потом убрать)
        print("Доступные столбцы:", df_sec.columns.tolist())

        # 2. Отбираем только акции: теперь не привязываемся к BOARDID
        #    Если столбца BOARDID нет, берём все строки, где есть SECID.
        if 'BOARDID' in df_sec.columns:
            shares = df_sec[df_sec['BOARDID'] == 'TQBR'][['SECID', 'SHORTNAME']]
        else:
            # Просто берём все записи с непустым SECID (это и будут акции)
            shares = df_sec[df_sec['SECID'].notna()][['SECID', 'SHORTNAME']]

        print(f"Найдено бумаг: {len(shares)}")

        # Для теста берём первые 10 тикеров (можешь увеличить)
        top_tickers = shares['SECID'].head(10).tolist()
        print(f"Загружаем {len(top_tickers)} тикеров: {', '.join(top_tickers)}")

        for ticker in top_tickers:
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
                    print(f"  {ticker}: нет данных")
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

                if new_df.empty:
                    print(f"  {ticker}: новых данных нет")
                    continue

                new_df.to_sql(
                    'stocks', engine, schema='staging',
                    if_exists='append', index=False, method='multi'
                )
                print(f"  {ticker}: загружено {len(new_df)} строк")
            except Exception as e:
                print(f"  Ошибка для {ticker}: {e}")
                continue

    except Exception as e:
        print(f"Ошибка при получении списка акций: {e}")

    print(f"Загрузка завершена {datetime.now()}")


if __name__ == "__main__":
    load_shares()