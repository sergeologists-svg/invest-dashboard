"""
Инвестиционный дашборд на Streamlit.
Акции, Облигации, Скринер акций, Ключевая ставка ЦБ, Депозиты.
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from sqlalchemy import create_engine
from datetime import datetime, timedelta
import subprocess
import sys

DATABASE_URL = "postgresql://postgres.lxqmkvbtazjfqzkoumuk:17Vfylfdjitr@aws-1-eu-west-1.pooler.supabase.com:5432/postgres"
engine = create_engine(DATABASE_URL)

st.set_page_config(page_title="Инвестиционный дашборд", layout="wide")
st.title("📈 Инвестиционный монитор (MOEX)")

# Блок с информацией о последнем обновлении и кнопкой
col_info, col_btn = st.columns([3, 1])
with col_info:
    try:
        last_stock_date = pd.read_sql("SELECT MAX(tradedate) as max_date FROM staging.stocks", engine).iloc[0]['max_date']
        last_bond_date = pd.read_sql("SELECT MAX(tradedate) as max_date FROM staging.bonds", engine).iloc[0]['max_date']
        latest_date = max(last_stock_date, last_bond_date) if last_stock_date and last_bond_date else None
        if latest_date:
            st.markdown(f"🕒 **Данные актуальны на:** {latest_date.strftime('%d.%m.%Y')}")
        else:
            st.markdown("🕒 **Данные ещё не загружены**")
    except:
        st.markdown("🕒 **Ошибка получения даты обновления**")
with col_btn:
    if st.button("🔄 Обновить все данные"):
        with st.spinner("Загружаем свежие данные с MOEX... Это может занять пару минут."):
            try:
                subprocess.run([sys.executable, "load_moex.py"], check=True)
                subprocess.run([sys.executable, "load_bonds.py"], check=True)
                st.success("Данные обновлены! Обновите страницу.")
            except Exception as e:
                st.error(f"Ошибка при обновлении: {e}")

@st.cache_data(ttl=3600)
def load_data():
    today = datetime.now().date()
    start = today - timedelta(days=10)
    stocks_df = pd.read_sql(f"SELECT * FROM staging.stocks WHERE tradedate >= '{start}' ORDER BY tradedate", engine)
    bonds_df = pd.read_sql(f"SELECT * FROM staging.bonds WHERE tradedate >= '{start}' ORDER BY tradedate", engine)
    info_df = pd.read_sql("SELECT * FROM staging.securities_info", engine)
    fundamentals_df = pd.read_sql("SELECT * FROM staging.fundamentals", engine)
    key_rate_df = pd.read_sql("SELECT * FROM staging.key_rates ORDER BY date DESC LIMIT 1", engine)
    return stocks_df, bonds_df, info_df, fundamentals_df, key_rate_df

stocks_df, bonds_df, info_df, fundamentals_df, key_rate_df = load_data()

if stocks_df.empty and bonds_df.empty:
    st.warning("Нет данных. Запустите скрипты загрузки.")
    st.stop()

if not key_rate_df.empty:
    rate = key_rate_df.iloc[0]['rate']
    st.sidebar.metric("Ключевая ставка ЦБ", f"{rate}%")

tab1, tab2, tab3, tab4 = st.tabs(["📊 Акции", "🏦 Облигации", "🔎 Скринер акций", "💰 Депозиты"])

# ---------- АКЦИИ ----------
with tab1:
    st.subheader("Акции – последние 10 дней")
    if not stocks_df.empty:
        last_date = stocks_df['tradedate'].max()
        prev_date = stocks_df['tradedate'].unique()[-2]
        today_data = stocks_df[stocks_df['tradedate'] == last_date]
        prev_data = stocks_df[stocks_df['tradedate'] == prev_date]
        merged = today_data.merge(prev_data, on='secid', suffixes=('_today', '_prev'))
        merged['change_pct'] = (merged['close_today'] - merged['close_prev']) / merged['close_prev'] * 100
        merged = merged.merge(info_df[info_df['type']=='stock'], on='secid', how='left')

        def color_negative_red(val):
            color = 'red' if val < 0 else 'black'
            return f'color: {color}'

        col1, col2 = st.columns(2)
        with col1:
            st.subheader("🔺 Лидеры роста")
            top_gainers = merged.nlargest(5, 'change_pct')
            fig = px.bar(top_gainers, x='secid', y='change_pct', text='shortname', title="Рост за день, %")
            st.plotly_chart(fig, use_container_width=True)
        with col2:
            st.subheader("🔻 Лидеры падения")
            top_losers = merged.nsmallest(5, 'change_pct')
            fig = px.bar(top_losers, x='secid', y='change_pct', text='shortname', title="Падение за день, %")
            st.plotly_chart(fig, use_container_width=True)

        st.subheader("Динамика цены")
        tickers = sorted(info_df[info_df['type']=='stock']['secid'].unique())
        selected = st.selectbox("Выберите акцию", tickers,
                                format_func=lambda x: f"{x} — {info_df[info_df['secid']==x]['shortname'].values[0]}")
        df_plot = stocks_df[stocks_df['secid'] == selected]
        if not df_plot.empty:
            fig = px.line(df_plot, x='tradedate', y='close', title=f"Цена закрытия {selected}")
            st.plotly_chart(fig, use_container_width=True)

        st.subheader("Все акции")
        styled_df = merged[['secid', 'shortname', 'close_today', 'change_pct', 'volume_today']].rename(
            columns={'close_today':'Цена', 'change_pct':'Изм.%', 'volume_today':'Объём'}
        ).style.map(color_negative_red, subset=['Изм.%'])
        st.dataframe(styled_df, hide_index=True)

# ---------- ОБЛИГАЦИИ ----------
with tab2:
    st.subheader("Облигации – анализ доходности")
    try:
        bonds_analytics = pd.read_sql("SELECT * FROM staging.bonds_analytics", engine)
    except:
        bonds_analytics = pd.DataFrame()
    key_rate_value = key_rate_df.iloc[0]['rate'] if not key_rate_df.empty else None

    if bonds_analytics.empty:
        st.warning("Аналитика по облигациям ещё не загружена.")
    else:
        bonds_info = info_df[info_df['type'] == 'bond']
        merged = bonds_analytics.merge(bonds_info, on='secid', how='left')
        last_bond_prices = bonds_df.sort_values('tradedate').groupby('secid').last().reset_index()[['secid', 'close']]
        merged = merged.merge(last_bond_prices, on='secid', how='left')
        merged = merged.rename(columns={'close': 'price'})

        st.subheader("Основные параметры")
        display = merged[['secid', 'shortname', 'price', 'coupon_rate', 'maturity_date', 'nkd']].copy()
        display.columns = ['Тикер', 'Название', 'Цена', 'Купон, %', 'Погашение', 'НКД']
        display = display.sort_values('Купон, %', ascending=False)
        st.dataframe(display, hide_index=True)

        if key_rate_value:
            st.metric("Ключевая ставка ЦБ", f"{key_rate_value}%")
            st.caption("Сравнивайте купон облигации с ключевой ставкой.")

        st.subheader("🏆 Топ-5 по купонной доходности")
        top_coupon = merged.nlargest(5, 'coupon_rate')[['secid', 'shortname', 'coupon_rate', 'maturity_date']]
        st.dataframe(top_coupon.rename(columns={
            'secid':'Тикер','shortname':'Название','coupon_rate':'Купон, %','maturity_date':'Погашение'
        }), hide_index=True)

# ---------- СКРИНЕР АКЦИЙ (РЕКОМЕНДАТЕЛЬНЫЙ МОДУЛЬ) ----------
with tab3:
    st.subheader("⭐ Рекомендации по акциям")
    st.markdown("Акции, отобранные по фундаментальным показателям для долгосрочного инвестора.")

    if fundamentals_df.empty:
        st.warning("Фундаментальные данные ещё не загружены.")
    else:
        has_div = 'div_yield' in fundamentals_df.columns
        last_prices = stocks_df.sort_values('tradedate').groupby('secid').last().reset_index()[['secid', 'close']]
        screen_df = fundamentals_df.merge(info_df[info_df['type']=='stock'], on='secid', how='left')
        screen_df = screen_df.merge(last_prices, on='secid', how='left')
        screen_df = screen_df.rename(columns={'close': 'price'})

        screen_df['score'] = 0
        screen_df.loc[screen_df['pe'] < 10, 'score'] += 2
        screen_df.loc[(screen_df['pe'] >= 10) & (screen_df['pe'] < 15), 'score'] += 1
        if has_div:
            screen_df.loc[screen_df['div_yield'] > 6, 'score'] += 2
            screen_df.loc[(screen_df['div_yield'] > 4) & (screen_df['div_yield'] <= 6), 'score'] += 1
        screen_df.loc[screen_df['pb'] < 1, 'score'] += 1

        def signal_text(s):
            if s >= 4:
                return '🟢 Сильная рекомендация'
            elif s >= 2:
                return '🟡 Присмотреться'
            else:
                return '🔴 Пока нет'

        screen_df['Сигнал'] = screen_df['score'].apply(signal_text)
        recommended = screen_df[screen_df['score'] > 0].sort_values('score', ascending=False).head(10).copy()

        st.subheader("🏆 Топ-10 акций для рассмотрения")
        if recommended.empty:
            st.info("Нет акций, соответствующих критериям.")
        else:
            display_cols = {
                'secid': 'Тикер', 'shortname': 'Название', 'price': 'Цена, ₽',
                'pe': 'P/E', 'pb': 'P/B', 'div_yield': 'Дивдоходность, %',
                'score': 'Баллы', 'Сигнал': 'Рекомендация'
            }
            if not has_div:
                del display_cols['div_yield']
            available_display = {k: v for k, v in display_cols.items() if k in recommended.columns}
            display_df = recommended[list(available_display.keys())].rename(columns=available_display)

            def color_row(row):
                if '🟢' in str(row.get('Рекомендация', '')):
                    return ['background-color: #d4edda'] * len(row)
                elif '🟡' in str(row.get('Рекомендация', '')):
                    return ['background-color: #fff3cd'] * len(row)
                return [''] * len(row)

            styled = display_df.style.apply(color_row, axis=1).format(precision=2)
            st.dataframe(styled, hide_index=True)
            st.markdown("🟢 – сильные показатели, 🟡 – есть плюсы, 🔴 – не проходит.")

        with st.expander("🔧 Расширенные фильтры"):
            max_pe = st.slider("Максимальный P/E", 0.0, 100.0, 15.0, key='pe_filter')
            if has_div:
                min_div = st.slider("Минимальная дивдоходность, %", 0.0, 20.0, 4.0, key='div_filter')
            else:
                min_div = None

            mask = (screen_df['pe'].notna()) & (screen_df['pe'] <= max_pe)
            if has_div and min_div is not None:
                mask = mask & (screen_df['div_yield'].notna()) & (screen_df['div_yield'] >= min_div)

            filtered = screen_df[mask].sort_values('pe')
            st.metric("Найдено акций", len(filtered))
            if not filtered.empty:
                st.dataframe(filtered[['secid', 'shortname', 'price', 'pe', 'pb', 'div_yield', 'score', 'Сигнал']]
                             .rename(columns={'secid':'Тикер','shortname':'Название','price':'Цена'}),
                             hide_index=True)

# ---------- ДЕПОЗИТЫ ----------
with tab4:
    st.subheader("💰 Депозиты – сравнение с облигациями")
    deposit_df = pd.read_sql("SELECT * FROM staging.deposit_rates ORDER BY published DESC", engine)
    if deposit_df.empty:
        st.warning("Данные по депозитам ещё не загружены. Запустите load_deposits.py")
    else:
        st.subheader("Средние максимальные ставки топ-10 банков")
        display_dep = deposit_df[['bank_name', 'rate', 'term_days', 'published']].rename(
            columns={'bank_name':'Банк', 'rate':'Ставка, %', 'term_days':'Срок (дней)', 'published':'Дата'}
        )
        st.dataframe(display_dep, hide_index=True)

        if not key_rate_df.empty:
            key_rate = key_rate_df.iloc[0]['rate']
            deposit_rate = deposit_df.iloc[0]['rate']
            comp_data = pd.DataFrame({
                'Инструмент': ['Ключевая ставка', 'Депозит (средний)'],
                'Ставка, %': [key_rate, deposit_rate]
            })
            fig = px.bar(comp_data, x='Инструмент', y='Ставка, %', title="Сравнение доходности", color='Инструмент')
            st.plotly_chart(fig, use_container_width=True)
            st.caption("Сравните депозит с доходностью облигаций на соседней вкладке.")

st.caption("Данные предоставлены Московской биржей (MOEX). Фундаментальные показатели – smart‑lab.ru.")