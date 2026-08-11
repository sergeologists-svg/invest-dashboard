

"""
Инвестиционный дашборд на Streamlit.
Акции + Облигации с названиями компаний.
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from sqlalchemy import create_engine

# ===== ТВОЙ URI =====
DATABASE_URL = "postgresql://postgres.lxqmkvbtazjfqzkoumuk:17Vfylfdjitr@aws-1-eu-west-1.pooler.supabase.com:5432/postgres"
# =====================

engine = create_engine(DATABASE_URL)

st.set_page_config(page_title="Инвестиционный дашборд", layout="wide")
st.title("📈 Инвестиционный дашборд (MOEX)")

# ======================
# Загрузка данных
# ======================
@st.cache_data(ttl=3600)
def load_data():
    """Читает все свечи и справочник."""
    stocks_df = pd.read_sql("SELECT * FROM staging.stocks ORDER BY tradedate", engine)
    bonds_df = pd.read_sql("SELECT * FROM staging.bonds ORDER BY tradedate", engine)
    info_df = pd.read_sql("SELECT * FROM staging.securities_info", engine)
    return stocks_df, bonds_df, info_df

stocks_df, bonds_df, info_df = load_data()

if stocks_df.empty and bonds_df.empty:
    st.warning("Данные ещё не загружены. Запустите load_moex.py и load_bonds.py.")
    st.stop()

# ======================
# Вкладки
# ======================
tab1, tab2 = st.tabs(["📊 Акции", "🏦 Облигации"])

# ---------- АКЦИИ ----------
with tab1:
    st.subheader("Акции")

    # Выбор тикера с названием
    stock_info = info_df[info_df['type'] == 'stock']
    ticker_map = dict(zip(stock_info['secid'], stock_info['shortname']))
    ticker_list = sorted(stock_info['secid'].tolist())

    selected_stock = st.sidebar.selectbox(
        "Тикер акции",
        ticker_list,
        format_func=lambda x: f"{x} — {ticker_map.get(x, x)}"
    )

    # Фильтр по дате
    df_stock = stocks_df[stocks_df['secid'] == selected_stock]
    if not df_stock.empty:
        min_date = df_stock['tradedate'].min().date()
        max_date = df_stock['tradedate'].max().date()
        date_range = st.sidebar.date_input("Диапазон дат", value=(min_date, max_date))
        if len(date_range) == 2:
            df_stock = df_stock[
                (df_stock['tradedate'].dt.date >= date_range[0]) &
                (df_stock['tradedate'].dt.date <= date_range[1])
            ]

        # График свечей
        fig = go.Figure(data=[go.Candlestick(
            x=df_stock['tradedate'], open=df_stock['open'],
            high=df_stock['high'], low=df_stock['low'],
            close=df_stock['close'], name=selected_stock
        )])
        fig.update_layout(xaxis_title="Дата", yaxis_title="Цена (₽)", template="plotly_white")
        st.plotly_chart(fig, use_container_width=True)

        # Статистика
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Последняя цена", f"{df_stock['close'].iloc[-1]:.2f} ₽")
        with col2:
            st.metric("Средний объём", f"{df_stock['volume'].mean():,.0f}")
        with col3:
            change = df_stock['close'].iloc[-1] - df_stock['close'].iloc[0]
            st.metric("Изменение за период", f"{change:+.2f} ₽")

    # Топ-10 роста
    st.subheader("🏆 Топ-10 роста за период")
    growth = stocks_df.groupby('secid').apply(
        lambda g: (g[g['tradedate'] == g['tradedate'].max()]['close'].values[0] /
                   g[g['tradedate'] == g['tradedate'].min()]['close'].values[0] - 1) * 100
        if len(g) > 1 else None
    ).dropna().sort_values(ascending=False).head(10)
    growth = growth.reset_index()
    growth.columns = ['Тикер', 'Рост, %']
    fig = px.bar(growth, x='Тикер', y='Рост, %', text_auto='.2f')
    st.plotly_chart(fig, use_container_width=True)

# ---------- ОБЛИГАЦИИ ----------
with tab2:
    st.subheader("Облигации")

    # Таблица со списком облигаций
    bond_info = info_df[info_df['type'] == 'bond']
    # Получим последние данные для каждой облигации
    latest_bonds = bonds_df.groupby('secid').last().reset_index()
    # Присоединим названия
    bond_table = latest_bonds.merge(bond_info, on='secid', how='left')
    bond_table = bond_table[['secid', 'shortname', 'close', 'coupon', 'yield', 'duration', 'volume']]
    bond_table.columns = ['Тикер', 'Название', 'Цена', 'Купон', 'Доходность', 'Дюрация', 'Объём']
    st.dataframe(bond_table.sort_values('Тикер'))

st.caption("Данные предоставлены Московской биржей (MOEX). Обновление ежедневное.")