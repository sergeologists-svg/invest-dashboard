"""
load_bonds_analytics.py
Загружает базовую аналитику по облигациям: НКД, купоны, даты погашения.
"""
import requests
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime, date
import urllib3

# ===== ТВОЙ URI SUPABASE =====
DATABASE_URL = "postgresql://postgres.lxqmkvbtazjfqzkoumuk:17Vfylfdjitr@aws-1-eu-west-1.pooler.supabase.com:5432/postgres"
# ==============================

engine = create_engine(DATABASE_URL)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def parse_date_safe(value):
    if value is None:
        return None
    try:
        return pd.to_datetime(value).date()
    except:
        return None

def load_bonds_analytics():
    print(f"Старт загрузки базовой аналитики по облигациям {datetime.now()}")

    bonds_info = pd.read_sql("SELECT secid FROM staging.securities_info WHERE type = 'bond'", engine)
    tickers = bonds_info['secid'].tolist()
    print(f"Облигаций в справочнике: {len(tickers)}")
    tickers = tickers[:50]  # первые 50 для скорости

    results = []
    session = requests.Session()
    session.verify = False

    for idx, ticker in enumerate(tickers, start=1):
        try:
            bond_url = f"https://iss.moex.com/iss/securities/{ticker}.json"
            bond_resp = session.get(bond_url)
            if bond_resp.status_code != 200:
                continue
            bond_data = bond_resp.json()

            maturity = None
            offer = None
            nkd = None
            coupon_rate = None
            next_coupon = None
            coupon_type = None

            for row in bond_data.get('description', {}).get('data', []):
                key = row[0].strip() if row[0] else ''
                val = row[2]
                if key == 'MATDATE':
                    maturity = parse_date_safe(val)
                elif key == 'OFFERDATE':
                    offer = parse_date_safe(val)
                elif key == 'ACCRUEDINT':
                    try:
                        nkd = float(val) if val else None
                    except:
                        pass
                elif key == 'COUPONVALUE':
                    try:
                        coupon_rate = float(val) if val else None
                    except:
                        pass
                elif key == 'COUPONDATE':
                    next_coupon = parse_date_safe(val)
                elif key == 'COUPONTYPE':
                    coupon_type = val

            # Берём даже те облигации, у которых нет maturity или coupon_rate
            results.append({
                'secid': ticker,
                'nkd': nkd,
                'coupon_rate': coupon_rate,
                'next_coupon': next_coupon,
                'maturity_date': maturity,
                'offer_date': offer,
                'coupon_type': coupon_type if coupon_type else 'unknown',
                'updated': datetime.now().date()
            })
            print(f"  [{idx}/{len(tickers)}] {ticker} – OK")

        except Exception as e:
            print(f"  [{idx}/{len(tickers)}] {ticker}: ошибка {e}")
            continue

    if results:
        df = pd.DataFrame(results)
        # Удаляем старые данные и загружаем новые
        with engine.connect() as conn:
            conn.execute(text("DROP TABLE IF EXISTS staging.bonds_analytics"))
            conn.commit()
        df.to_sql('bonds_analytics', engine, schema='staging', index=False, method='multi')
        print(f"Загружено {len(df)} записей в staging.bonds_analytics")
    else:
        print("Нет данных для сохранения")

if __name__ == "__main__":
    load_bonds_analytics()