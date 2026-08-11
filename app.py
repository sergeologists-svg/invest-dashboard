"""
Инвестиционный дашборд на Streamlit.
Отображает данные по акциям и облигациям из облачной БД Supabase.
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from sqlalchemy import create_engine

# ===== ВСТАВЬ СВОЙ URI ИЗ SUPABASE (Direct connection) =====
DATABASE_URL = "postgresql://postgres.lxqmkvbtazjfqzkoumuk:17Vfylfdjitr@aws-1-eu-west-1.pooler.supabase.com:5432/postgres"
# ===========================================================

engine = create_engine(DATABASE_URL)

st.set_page_config(page_title="Инвестиционный дашборд", layout="wide")
st.title("📈 Инвестиционный дашборд (акции MOEX)")

# ======================
# Загрузка данных из БД
# ======================
@st.cache_data(ttl=3600)  # кэшируем данные на 1 час
def load_data():
    """Читает все свечи из staging.stocks."""
    query = """
        SELECT secid, tradedate, open, high, low, close, volume
        FROM staging.stocks
        ORDER BY tradedate
    """
    df = pd.read_sql(query, engine)
    df['tradedate'] = pd.to_datetime(df['tradedate'])
    return df

df = load_data()

if df.empty:
    st.warning("Данные ещё не загружены. Сначала запустите `load_moex.py`.")
    st.stop()

# ======================
# Боковая панель фильтров
# ======================
st.sidebar.header("Фильтры")

# Выбор тикера
tickers = sorted(df['secid'].unique())
selected_ticker = st.sidebar.selectbox("Тикер", tickers)

# Диапазон дат
min_date = df['tradedate'].min().date()
max_date = df['tradedate'].max().date()
date_range = st.sidebar.date_input(
    "Диапазон дат",
    value=(min_date, max_date),
    min_value=min_date,
    max_value=max_date
)

# Фильтрация данных
df_filtered = df[df['secid'] == selected_ticker]
if len(date_range) == 2:
    df_filtered = df_filtered[
        (df_filtered['tradedate'].dt.date >= date_range[0]) &
        (df_filtered['tradedate'].dt.date <= date_range[1])
    ]

# ======================
# Вкладки
# ======================
tab1, tab2, tab3 = st.tabs(["📊 График цен", "📈 Статистика", "🏆 Топ-10 акций"])

with tab1:
    st.subheader(f"Динамика цены закрытия: {selected_ticker}")

    # График свечей (plotly candlestick)
    fig = go.Figure(data=[go.Candlestick(
        x=df_filtered['tradedate'],
        open=df_filtered['open'],
        high=df_filtered['high'],
        low=df_filtered['low'],
        close=df_filtered['close'],
        name=selected_ticker
    )])
    fig.update_layout(xaxis_title="Дата", yaxis_title="Цена (₽)", template="plotly_white")
    st.plotly_chart(fig, use_container_width=True)

with tab2:
    st.subheader("Основные показатели")
    if not df_filtered.empty:
        col1, col2, col3 = st.columns(3)
        with col1:
            last_close = df_filtered['close'].iloc[-1]
            st.metric("Последняя цена закрытия", f"{last_close:.2f} ₽")
        with col2:
            avg_volume = df_filtered['volume'].mean()
            st.metric("Средний объём торгов", f"{avg_volume:,.0f}")
        with col3:
            price_change = df_filtered['close'].iloc[-1] - df_filtered['close'].iloc[0]
            st.metric("Изменение за период", f"{price_change:+.2f} ₽")

        st.dataframe(df_filtered[['tradedate', 'close', 'volume']].tail(10))
    else:
        st.info("Нет данных для выбранного тикера и периода")

with tab3:
    st.subheader("Топ-10 акций по росту за период")

    # Рассчитываем рост для каждого тикера
    growth = df.groupby('secid').apply(
        lambda g: (g[g['tradedate'] == g['tradedate'].max()]['close'].values[0] /
                   g[g['tradedate'] == g['tradedate'].min()]['close'].values[0] - 1) * 100
        if len(g) > 1 else None
    ).dropna().sort_values(ascending=False).head(10)

    growth = growth.reset_index()
    growth.columns = ['Тикер', 'Рост, %']

    fig = px.bar(growth, x='Тикер', y='Рост, %', title="Лидеры роста за период",
                 text_auto='.2f')
    st.plotly_chart(fig, use_container_width=True)

# ======================
# Футер
# ======================
st.caption("Данные предоставлены Московской биржей (MOEX) через API. Обновление ежедневное.")