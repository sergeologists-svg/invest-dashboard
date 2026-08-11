"""
load_bonds.py
Ежедневная загрузка дневных свечей ОБЛИГАЦИЙ с MOEX (последние 14 дней) + справочник названий.
"""
import requests
import pandas as pd
from sqlalchemy import create_engine
from datetime import datetime, timedelta
import urllib3

# ===== ТВОЙ URI ИЗ SUPABASE =====
DATABASE_URL = "postgresql://postgres.lxqmkvbtazjfqzkoumuk:17Vfylfdjitr@aws-1-eu-west-1.pooler.supabase.com:5432/postgres"
# ================================

engine = create_engine(DATABASE_URL)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def load_bonds():
    """Загружает дневные свечи для облигаций с MOEX."""
    session = requests.Session()
    session.verify = False
    print(f"Начинаем загрузку облигаций {datetime.now()}")

    try:
        # 1. Список облигаций через прямой запрос к ISS MOEX
        url = "https://iss.moex.com/iss/engines/stock/markets/bonds/boards/TQOB/securities.json"
        params = {
            "iss.meta": "off",
            "iss.only": "securities",
            "securities.columns": "SECID,SECNAME,SHORTNAME",
        }
        resp = session.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

        sec_data = data['securities']['data']
        sec_cols = data['securities']['columns']
        df_sec = pd.DataFrame(sec_data, columns=sec_cols)
        print(f"Найдено облигаций (TQOB): {len(df_sec)}")

        # 2. Сохраняем справочник названий
        info = df_sec[['SECID', 'SHORTNAME']].copy()
        info.columns = ['secid', 'shortname']
        info['type'] = 'bond'
        existing_ids = pd.read_sql("SELECT secid FROM staging.securities_info", engine)
        info = info[~info['secid'].isin(existing_ids['secid'])]
        if not info.empty:
            info.to_sql('securities_info', engine, schema='staging',
                        if_exists='append', index=False, method='multi')
            print(f"Добавлено {len(info)} названий облигаций в справочник")

        # 3. Загружаем свечи за последние 14 дней
        start_date = (datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d')
        all_tickers = df_sec['SECID'].tolist()
        total = len(all_tickers)
        print(f"Загружаем свечи с {start_date} для {total} облигаций...")
        loaded = 0

        for idx, ticker in enumerate(all_tickers, start=1):
            try:
                candles_url = f"https://iss.moex.com/iss/engines/stock/markets/bonds/boards/TQOB/securities/{ticker}/candles.json"
                candles_resp = session.get(candles_url, params={
                    "interval": 24,
                    "from": start_date,
                    "till": datetime.now().strftime("%Y-%m-%d"),
                })
                if candles_resp.status_code != 200:
                    continue
                c_data = candles_resp.json()
                if 'candles' not in c_data:
                    continue
                c_rows = c_data['candles']['data']
                c_cols = c_data['candles']['columns']
                df = pd.DataFrame(c_rows, columns=c_cols)

                # Переименовываем поля в стандартные имена
                rename_map = {
                    'begin': 'tradedate',
                    'open': 'open',
                    'close': 'close',
                    'high': 'high',
                    'low': 'low',
                    'volume': 'volume',
                }
                df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
                df['secid'] = ticker
                if 'tradedate' in df.columns:
                    df['tradedate'] = pd.to_datetime(df['tradedate']).dt.date

                # Добавляем отсутствующие поля coupon, yield, duration (пока не загружаются)
                for col in ['coupon', 'yield', 'duration']:
                    if col not in df.columns:
                        df[col] = None

                # Оставляем только столбцы, которые есть в таблице bonds
                cols_to_save = ['secid', 'tradedate', 'open', 'high', 'low', 'close', 'volume',
                                'coupon', 'yield', 'duration']
                df = df[[c for c in cols_to_save if c in df.columns]]

                if df.empty:
                    continue

                # Проверяем, какие даты уже есть в БД
                existing = pd.read_sql(
                    f"SELECT tradedate FROM staging.bonds WHERE secid = '{ticker}'", engine
                )
                existing_dates = set(existing['tradedate'])
                new_df = df[~df['tradedate'].isin(existing_dates)]

                if not new_df.empty:
                    new_df.to_sql(
                        'bonds', engine, schema='staging',
                        if_exists='append', index=False, method='multi'
                    )
                    rows = len(new_df)
                    loaded += rows
                    print(f"  [{idx}/{total}] {ticker}: +{rows} строк (всего загружено {loaded})")
            except Exception as e:
                print(f"  [{idx}/{total}] {ticker}: ошибка {e}")
                continue

    except Exception as e:
        print(f"Ошибка при получении списка облигаций: {e}")

    print(f"Загрузка облигаций завершена. Всего загружено {loaded} записей.")


if __name__ == "__main__":
    load_bonds()