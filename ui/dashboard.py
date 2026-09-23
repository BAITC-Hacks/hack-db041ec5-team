"""Dashboard built from the current snapshot, with no external services."""

import altair as alt
import networkx as nx
import pandas as pd
import streamlit as st

from ui.constants import fmt_kzt, fmt_number


def transaction_slice(tx, start, end, gid=None):
    """Inclusive calendar dates; never change the source snapshot."""
    result = tx.copy()
    dates = pd.to_datetime(result.date, utc=True, errors="coerce", format="mixed").dt.date
    mask = dates.between(start, end)
    if gid is not None:
        mask &= (result.src == gid) | (result.dst == gid)
    return result.loc[mask].copy()


def network_health(ctx):
    st.caption("Обзор всей загруженной сети · фильтры слева применяются к вкладке «Граф»")
    columns = st.columns(4)
    columns[0].metric("Направленных связей", fmt_number(ctx.graph.number_of_edges()))
    columns[1].metric("Приоритет ≥ 0,8", sum((n.get("priority_score") or 0) >= .8 for _, n in ctx.nodes(data=True)))
    columns[2].metric("Компонент сети", nx.number_weakly_connected_components(ctx.graph) if ctx.graph else 0)
    columns[3].metric("На границе выборки", sum(bool(n.get("is_frontier")) for _, n in ctx.nodes(data=True)))
    with st.expander("Паспорт данных и экспорт"):
        st.write("Источник: " + ("синтетическое демо" if ctx.demo else "локальные выгрузки A/B"))
        st.code(f"snapshot: {ctx.fingerprint}", language=None)
        st.write(f"Замечания загрузчика: {len(ctx.warnings)} · отсутствующие файлы: {len(ctx.missing)}")
        for name in ("nodes_roles", "top_nodes", "clusters"):
            table = ctx.frames[name]
            if not table.empty:
                st.download_button(f"Скачать {name}.csv", table.to_csv(index=False).encode("utf-8-sig"), file_name=f"{name}.csv", mime="text/csv", key=f"export_{name}")


def transactions_dashboard(ctx):
    st.markdown('<div class="panel-title">Активность переводов</div><div class="panel-note">Объём и операции за выбранный период</div>', unsafe_allow_html=True)
    st.caption("Фильтры этого раздела не меняют граф и рассчитанные приоритеты.")
    if ctx.tx.empty:
        st.info("Для динамики загрузите data/transactions.parquet. Агрегированные связи доступны на графе.")
        return
    dates = pd.to_datetime(ctx.tx.date, utc=True, errors="coerce", format="mixed").dropna().dt.date
    if dates.empty:
        st.info("Нет переводов с корректными датами.")
        return
    left, right = st.columns([2, 1])
    interval = left.date_input("Период переводов", value=(dates.min(), dates.max()), min_value=dates.min(), max_value=dates.max(), key=f"period_{ctx.fingerprint}")
    selected = right.selectbox("Участник переводов", [None] + sorted(ctx.graph), format_func=lambda v: "Все участники" if v is None else f"gid {v}", key=f"tx_gid_{ctx.fingerprint}")
    if not isinstance(interval, (tuple, list)) or len(interval) != 2:
        st.info("Выберите начало и конец периода.")
        return
    tx = transaction_slice(ctx.tx, *interval, selected)
    if tx.empty:
        st.info("За выбранный период переводов нет.")
        return
    a, b, c = st.columns(3)
    a.metric("Операций за период", fmt_number(len(tx)))
    b.metric("Объём за период", fmt_kzt(tx.sum_kzt.sum()))
    c.metric("Средний перевод", fmt_kzt(tx.sum_kzt.mean()))
    daily = tx.assign(day=pd.to_datetime(tx.date, utc=True).dt.floor("D")).groupby("day").sum_kzt.sum()
    chart_data = daily.rename('Сумма, ₸').reset_index()
    chart = alt.Chart(chart_data).mark_area(line={'color': '#168577', 'strokeWidth': 2}, color=alt.Gradient(gradient='linear', stops=[alt.GradientStop(color='#BDE3D7', offset=0), alt.GradientStop(color='#F4F6F9', offset=1)], x1=0, x2=0, y1=0, y2=1)).encode(
        x=alt.X('day:T', title=None, axis=alt.Axis(format='%d.%m', labelColor='#8594A0', grid=False)),
        y=alt.Y('Сумма, ₸:Q', title='Объём, ₸', axis=alt.Axis(format='~s', gridColor='#E8EDF2', labelColor='#8594A0')),
        tooltip=[alt.Tooltip('day:T', title='Дата', format='%d.%m.%Y'), alt.Tooltip('Сумма, ₸:Q', format=',.0f')]
    ).properties(height=210).configure_view(strokeWidth=0)
    st.altair_chart(chart, width='stretch')
    with st.expander("Журнал переводов"):
        st.dataframe(tx.sort_values("date", ascending=False), hide_index=True, width="stretch")
        st.download_button("Скачать выбранные переводы", tx.to_csv(index=False).encode("utf-8-sig"), file_name="transactions_filtered.csv", mime="text/csv")

