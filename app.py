"""Точка входа части C: python -m streamlit run app.py."""

import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from assistant.agent import api_key, provider_name
from ui.constants import ROLE_LABELS
from ui.data import file_signature, load_context
from ui.demo import make_demo
from ui.pages import (
    assistant_page,
    clusters_page,
    gaps_page,
    graph_page,
    overview,
    priorities,
    resilience_page,
)
from ui.style import apply_style

ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = ROOT / 'output'
if not (DEFAULT_OUTPUT / 'nodes_roles.csv').is_file() and (DEFAULT_OUTPUT / 'real' / 'nodes_roles.csv').is_file():
    DEFAULT_OUTPUT = DEFAULT_OUTPUT / 'real'
load_dotenv(ROOT / ".env", override=False)
st.set_page_config(
    page_title="Граф денег · Аналитика сети", page_icon="◉", layout="wide"
)
apply_style()


@st.cache_data(show_spinner="Читаю выгрузки…", max_entries=4)
def cached_context(out_dir, data_dir, cfg_path, signature):
    return load_context(out_dir, data_dir, cfg_path)


with st.sidebar:
    st.markdown('<div class="brand"><span class="brand-icon">↗</span> Money Graph</div>', unsafe_allow_html=True)
    st.caption("РАБОЧЕЕ МЕСТО АНАЛИТИКА")
    demo = st.toggle(
        "Демонстрационный пример",
        value=os.getenv("MONEYGRAPH_DEMO", "0") == "1",
        key="demo_mode",
    )
    with st.expander("Источники данных", expanded=False):
        out_dir = st.text_input(
            "Папка output",
            value=os.getenv("MONEYGRAPH_OUTPUT_DIR", str(DEFAULT_OUTPUT)),
        )
        data_dir = st.text_input(
            "Папка data", value=os.getenv("MONEYGRAPH_DATA_DIR", str(ROOT / "data"))
        )
        cfg_path = st.text_input("Конфигурация B", value=str(ROOT / "config.yaml"))
        if st.button("Обновить данные", width="stretch"):
            cached_context.clear()
    st.divider()

ctx = (
    make_demo()
    if demo
    else cached_context(
        out_dir, data_dir, cfg_path, file_signature(out_dir, data_dir, cfg_path)
    )
)
if st.session_state.get("snapshot") != ctx.fingerprint:
    st.session_state["snapshot"] = ctx.fingerprint
    for key in (
        "chat_history",
        "briefs",
        "gid_query",
        "priority_gid",
        "cluster_detail",
        "filter_cluster",
    ):
        st.session_state.pop(key, None)

with st.sidebar:
    st.markdown("**Отображение графа**")
    color_label = st.radio("Раскраска", ["По роли", "По кластеру"], horizontal=True)
    roles = st.multiselect(
        "Роли",
        list(ROLE_LABELS),
        default=list(ROLE_LABELS),
        format_func=ROLE_LABELS.get,
    )
    threshold = st.slider("Минимальный приоритет", 0.0, 1.0, 0.5, 0.05)
    cluster_ids = sorted(
        {
            n["cluster_id"]
            for _, n in ctx.nodes(data=True)
            if n.get("cluster_id") is not None
        }
    )
    cluster = st.selectbox(
        "Фильтр кластера",
        [None] + cluster_ids,
        format_func=lambda x: "Все кластеры" if x is None else str(x),
        key="filter_cluster",
    )
    show_all = st.checkbox("Весь граф · без порога")
    st.divider()
    st.markdown("**Ассистент**")
    model = st.text_input(
        "Модель LLM",
        value=os.getenv("MONEYGRAPH_LLM_MODEL", ""),
        placeholder="Модель с function calling",
    )
    configured = bool(api_key()) and bool(model.strip())
    st.caption('Провайдер: ' + provider_name().upper())
    online = st.toggle(
        "Использовать онлайн-режим", value=False, disabled=not configured
    )
    if not configured:
        st.caption(
            "Офлайн работает сразу. Для онлайн укажи ключ в .env и доступную модель."
        )
    else:
        st.caption(
            "Онлайн передаёт вопрос, последние сообщения и результаты инструментов выбранному API-провайдеру."
        )
    st.caption("Граф и расчёты доступны без интернета.")

st.markdown('''<div class="workspace-hero"><div><div class="eyebrow">MONEY GRAPH / ANALYTICS WORKSPACE</div><h1>Каждый перевод — часть картины</h1><p>Исследуйте связи, находите приоритеты и проверяйте гипотезы.</p></div><div class="status-pill">● Локальная аналитика</div></div>''', unsafe_allow_html=True)
if demo:
    st.markdown('<div class="demo-note">Демо-режим · Данные вымышлены и используются для показа интерфейса.</div>', unsafe_allow_html=True)
if ctx.missing or ctx.warnings:
    with st.expander("Состояние загрузки данных", expanded=not bool(ctx.graph)):
        if ctx.missing:
            st.info("Ожидаются выгрузки команды: " + ", ".join(ctx.missing))
        for warning in ctx.warnings:
            st.warning(warning)
if not ctx.graph:
    st.info(
        "Положи результаты A/B в output/ или включи «Демонстрационный пример» слева, чтобы проверить все экраны."
    )

filters = dict(
    roles=roles if set(roles) != set(ROLE_LABELS) else None,
    min_priority=threshold,
    cluster_id=cluster,
    show_all=show_all,
    color_by="role" if color_label == "По роли" else "cluster",
)
tabs = st.tabs(
    [
        "Обзор",
        "Граф",
        "Приоритеты",
        "Кластеры",
        "Устойчивость",
        "Белые пятна",
        "Ассистент",
    ]
)
with tabs[0]:
    overview(ctx)
with tabs[1]:
    graph_page(ctx, filters, model.strip(), online)
with tabs[2]:
    priorities(ctx, model.strip(), online)
with tabs[3]:
    clusters_page(ctx)
with tabs[4]:
    resilience_page(ctx)
with tabs[5]:
    gaps_page(ctx)
with tabs[6]:
    assistant_page(ctx, model.strip(), online)
st.caption(
    "Выборка ограничена исходящими переводами, четырьмя коленами и порогом суммы. Роли — гипотезы для проверки."
)



