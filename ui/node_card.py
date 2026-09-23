"""Карточка, объяснения и AI-справка на одном экране."""

import math
from dataclasses import asdict
from html import escape

import altair as alt
import pandas as pd
import streamlit as st
from assistant.agent import brief
from assistant.tools import get_node

from ui.constants import METRIC_LABELS, ROLE_COLORS, ROLE_LABELS, fmt_number


def daily_transactions(ctx, gid):
    if ctx.tx.empty:
        return pd.DataFrame()
    parts = []
    for column, label in (("dst", "Входящие"), ("src", "Исходящие")):
        part = (
            ctx.tx[ctx.tx[column] == gid]
            .groupby("date", as_index=False)["sum_kzt"]
            .sum()
        )
        part["Поток"] = label
        parts.append(part)
    return pd.concat(parts, ignore_index=True).rename(
        columns={"date": "Дата", "sum_kzt": "KZT"}
    )


def _counterparty_table(rows):
    if not rows:
        st.caption("В выборке не найдены.")
        return
    df = pd.DataFrame(rows)
    df["role"] = df.role.map(lambda r: ROLE_LABELS.get(r, "Нет роли"))
    st.dataframe(
        df[["gid", "role", "sum_kzt", "n_tx"]].rename(
            columns={"role": "Роль", "sum_kzt": "Сумма, KZT", "n_tx": "Операций"}
        ),
        hide_index=True,
        width="stretch",
    )


def show_node_card(ctx, gid, *, key="card", model="", online=False):
    if gid not in ctx.graph:
        st.warning("Узел не найден.")
        return
    record = get_node(ctx, gid)
    role = record["role"]
    color, label = (
        ROLE_COLORS.get(role, "#A0A8B5"),
        ROLE_LABELS.get(role, "Роль пока не рассчитана"),
    )
    st.markdown(
        f'<div class="node-heading"><span>КЛИЕНТ</span><h2>gid {gid}</h2>'
        f'<b style="color:{color};border-color:{color}">{escape(label)}</b></div>',
        unsafe_allow_html=True,
    )
    cols = st.columns(4)
    cols[0].metric("Приоритет", fmt_number(record["priority_score"], 3))
    cols[1].metric("Место в топе", fmt_number(record["rank"]))
    cols[2].metric("Оценка роли", fmt_number(record["role_score"], 3))
    cols[3].metric("Кластер", fmt_number(record["cluster_id"]))
    if record["metrics"].get("is_frontier"):
        st.warning(
            "Граница выборки: исходящие переводы могут быть обрезаны. Отсутствие исходящих не означает, что деньги остались на счёте."
        )
    left, right = st.columns([1, 1.2], gap="large")
    with left:
        st.markdown("**Баллы шести ролей**")
        values = []
        for role, score in record["scores"].items():
            try:
                if score is not None and math.isfinite(float(score)):
                    values.append(
                        {
                            "Роль": ROLE_LABELS[role],
                            "Балл": float(score),
                            "Цвет": ROLE_COLORS[role],
                        }
                    )
            except (ValueError, TypeError):
                pass
        if values:
            chart = (
                alt.Chart(pd.DataFrame(values))
                .mark_bar(cornerRadiusEnd=4)
                .encode(
                    x=alt.X("Балл:Q", scale=alt.Scale(domain=[0, 1])),
                    y=alt.Y("Роль:N", sort=list(ROLE_LABELS.values()), title=None),
                    color=alt.Color("Цвет:N", scale=None, legend=None),
                    tooltip=["Роль", "Балл"],
                )
                .properties(height=200)
            )
            st.altair_chart(chart, width="stretch")
            if len(values) < 6:
                st.caption(
                    "Часть score_* отсутствует в выгрузке; пропуски не заменяются нулями."
                )
        else:
            st.info("Баллы score_* ещё не переданы в node_features.csv.")
    with right:
        st.markdown("**Почему такая роль**")
        st.write(record["evidence"])
        st.markdown("**Сработавшее правило**")
        st.code(
            record["rule_fired"] or "Правило ещё не передано в node_features.csv.",
            language=None,
            wrap_lines=True,
        )
        if record["why"]:
            st.markdown("**Почему проверять в первую очередь**")
            st.write(record["why"])
    frequency = record.get("freq_top20")
    if isinstance(frequency, (int, float)) and 0 <= frequency <= 1:
        st.success(
            f"В топ-20 при {frequency:.0%} вариантов весов — устойчивость ранжирования, не вероятность виновности."
        )
    with st.expander("Все метрики и источники", expanded=False):
        rows = []
        for name, label in METRIC_LABELS.items():
            value = record["metrics"].get(name)
            text = (
                ("Да" if value else "Нет")
                if isinstance(value, bool)
                else ("Нет данных" if value is None else str(value))
            )
            rows.append({"Метрика": label, "Значение": text})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    left, right = st.columns(2)
    with left:
        st.markdown("**Топ-5 входящих контрагентов**")
        _counterparty_table(record["incoming"])
    with right:
        st.markdown("**Топ-5 исходящих контрагентов**")
        _counterparty_table(record["outgoing"])
    st.markdown("**Переводы по дням**")
    daily = daily_transactions(ctx, gid)
    if not daily.empty:
        chart = (
            alt.Chart(daily)
            .mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
            .encode(
                x=alt.X("Дата:T", title=None),
                y=alt.Y("KZT:Q", title="Сумма, KZT"),
                xOffset="Поток:N",
                color=alt.Color(
                    "Поток:N",
                    scale=alt.Scale(
                        domain=["Входящие", "Исходящие"], range=["#168577", "#426DAD"]
                    ),
                ),
                tooltip=[alt.Tooltip("Дата:T", format="%d.%m.%Y"), "Поток", "KZT"],
            )
            .properties(height=200)
        )
        st.altair_chart(chart, width="stretch")
    else:
        st.caption(
            "Нет операций для этого gid или ещё не загружен data/transactions.parquet."
        )
    cache_key = f"{ctx.fingerprint}:{gid}:{model}:{online}"
    if st.button("AI-справка", key=f"{key}_brief_{gid}", type="secondary"):
        cached = st.session_state.setdefault("briefs", {}).get(cache_key)
        # Успешную справку переиспользуем; после сбоя API кнопка позволяет повторить запрос.
        if cached is None or (online and cached["mode"] != "онлайн"):
            with st.spinner("Готовлю справку…"):
                answer = brief(ctx, gid, model, online=online)
            st.session_state["briefs"][cache_key] = asdict(answer)
    saved = st.session_state.get("briefs", {}).get(cache_key)
    if saved:
        st.caption("Справка · " + saved["mode"])
        if saved["notice"]:
            st.info(saved["notice"])
        st.write(saved["text"])
        with st.expander("Данные для справки"):
            st.json(saved["calls"])
