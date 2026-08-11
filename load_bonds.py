"""
load_bonds.py
Ежедневная загрузка дневных свечей ОБЛИГАЦИЙ с MOEX через прямой запрос к API.
"""
import requests
import pandas as pd
from sqlalchemy import create_engine
from datetime import datetime
import urllib3

# ===== ТВОЙ URI =====
DATABASE_URL = "postgresql://postgres.lxqmkvbtazjfqzkoumuk:17Vfylfdjitr@aws-1-eu-west-1.pooler.supabase.com:5432/postgres"
# =====================

engine = create_engine(DATABASE_URL)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def load_bonds():
    session = requests.Session()
    session.verify = False
    print(f"Начинаем загрузку облигаций {datetime.now()}")

    try:
        # 1. Получаем список ВСЕХ облигаций через прямой запрос к ISS MOEX
        url = "https://iss.moex.com/iss/engines/stock/markets/bonds/securities.json"
        params = {
            "iss.meta": "off",
            "iss.only": "securities",
            "securities.columns": "SECID,SECNAME,SHORTNAME",
        }
        resp = session.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        
        # Извлекаем данные и заголовки столбцов
        securities_data = data['securities']['data']
        columns = data['securities']['columns']
        df_sec = pd.DataFrame(securities_data, columns=columns)
        print(f"Найдено облигаций: {len(df_sec)}")

        # 2. Сохраняем справочник названий
        info = df_sec[['SECID', 'SHORTNAME']].copy()
        info.columns = ['secid', 'shortname']  # переименовываем для единообразия
        info['type'] = 'bond'
        existing_ids = pd.read_sql("SELECT secid FROM staging.securities_info", engine)
        info = info[~info['secid'].isin(existing_ids['secid'])]
        if not info.empty:
            info.to_sql('securities_info', engine, schema='staging',
                        if_exists='append', index=False, method='multi')
            print(f"Добавлено {len(info)} названий облигаций в справочник")

        # 3. Загружаем свечи для первых 20 облигаций (для теста; потом можно убрать .head(20))
        all_tickers = df_sec['SECID'].tolist()
        print(f"Загружаем свечи для {len(all_tickers)} облигаций...")

        for ticker in all_tickers:
            try:
                # Используем apimoex для свечей; если board='TQOB' не сработает, укажем прямой URL
                # Пробуем прямой запрос к свечам облигаций
                candles_url = f"https://iss.moex.com/iss/engines/stock/markets/bonds/securities/{ticker}/candles.json"
                candles_resp = session.get(candles_url, params={
                    "interval": 24,
                    "from": "2026-07-01",
                    "till": datetime.now().strftime("%Y-%m-%d"),
                })
                if candles_resp.status_code != 200:
                    continue
                candles_data = candles_resp.json()
                if 'candles' not in candles_data:
                    continue
                candles_rows = candles_data['candles']['data']
                candles_cols = candles_data['candles']['columns']
                df = pd.DataFrame(candles_rows, columns=candles_cols)

                # Переименовываем колонки под нашу таблицу bonds
                df = df.rename(columns={
                    'begin': 'tradedate',
                    'open': 'open',
                    'high': 'high',
                    'low': 'low',
                    'close': 'close',
                    'volume': 'volume',
                    'value': 'value'   # объем в деньгах, можно сохранить при желании
                })
                # Оставляем только те столбцы, которые есть в таблице staging.bonds
                # coupon, yield, duration пока будут NULL – добавим их позже
                df['coupon'] = None
                df['yield'] = None
                df['duration'] = None
                df['secid'] = ticker
                df['tradedate'] = pd.to_datetime(df['tradedate']).dt.date

                # Проверяем дубликаты
                existing = pd.read_sql(
                    f"SELECT tradedate FROM staging.bonds WHERE secid = '{ticker}'", engine
                )
                existing_dates = set(existing['tradedate'])
                new_df = df[~df['tradedate'].isin(existing_dates)]

                if not new_df.empty:
                    # Загружаем только те столбцы, которые есть в БД
                    cols_to_save = ['secid', 'tradedate', 'open', 'high', 'low', 'close', 'volume',
                                    'coupon', 'yield', 'duration']
                    new_df = new_df[[c for c in cols_to_save if c in new_df.columns]]
                    new_df.to_sql(
                        'bonds', engine, schema='staging',
                        if_exists='append', index=False, method='multi'
                    )
                    print(f"  {ticker}: загружено {len(new_df)} строк")
                else:
                    # не выводим сообщение для каждой, чтобы не засорять лог
                    pass
            except Exception as e:
                print(f"  Ошибка для {ticker}: {e}")
                continue

    except Exception as e:
        print(f"Ошибка при получении списка облигаций: {e}")

    print(f"Загрузка облигаций завершена {datetime.now()}")

if __name__ == "__main__":
    load_bonds()