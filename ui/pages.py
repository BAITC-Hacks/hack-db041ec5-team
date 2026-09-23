"""Семь вкладок приложения."""

from dataclasses import asdict
from html import escape

import altair as alt
import pandas as pd
import streamlit as st
from assistant.agent import ask
from assistant.tools import top_nodes

from ui.constants import ROLE_COLORS, ROLE_LABELS, fmt_kzt, fmt_number
from ui.graph_view import graph_records, legend, render_graph
from ui.node_card import show_node_card
from ui.dashboard import network_health, transactions_dashboard


def role_table(df, **kwargs):
    display = df.copy()
    if 'role' in display:
        display['role'] = display.role.map(lambda value: ROLE_LABELS.get(value, value))
    colors = {ROLE_LABELS.get(role, role): color for role, color in ROLE_COLORS.items()}
    def role_style(value):
        return f"color: {colors.get(value, '#526375')}; font-weight: 600"
    styled = display.style.map(role_style, subset=['role']) if 'role' in display else display
    config = {'gid': st.column_config.NumberColumn('ID клиента', format='%d'),
              'role': 'Роль', 'rank': 'Место', 'priority_score': st.column_config.ProgressColumn('Приоритет', min_value=0, max_value=1, format='%.2f'),
              'why': 'Почему в приоритете'}
    return st.dataframe(styled, hide_index=True, width='stretch', column_config=config, **kwargs)


def overview(ctx):
    st.markdown('<div class="section-heading"><h2>Обзор сети</h2><span>Вся загруженная выборка</span></div>', unsafe_allow_html=True)
    volume = sum(d['sum_kzt'] for _, _, d in ctx.graph.edges(data=True))
    amount = f'{volume / 1_000_000:,.2f} млн ₸'.replace(',', ' ') if volume >= 1_000_000 else f'{volume:,.0f} ₸'.replace(',', ' ')
    high = sum((n.get('priority_score') or 0) >= .8 for _, n in ctx.nodes(data=True))
    clusters = {n.get('cluster_id') for _, n in ctx.nodes(data=True) if n.get('cluster_id') is not None}
    cards = [('Участников сети', fmt_number(len(ctx.graph)), f'{ctx.graph.number_of_edges()} направленных связей', ''),
             ('Объём переводов', amount, 'Сумма рёбер в выборке', ''),
             ('Высокий приоритет', str(high), 'Оценка узла ≥ 0,8', 'attention'),
             ('Кластеров', str(len(clusters)), 'Связанные группы участников', '')]
    html = ''.join(f'<div class="kpi {kind}"><div class="kpi-label">{label}</div><div class="kpi-value">{value}</div><div class="kpi-note">{note}</div></div>' for label, value, note, kind in cards)
    st.markdown(f'<div class="kpi-grid">{html}</div>', unsafe_allow_html=True)
    left, right = st.columns([1.5, 1], gap='large')
    with left:
        st.markdown('<div class="panel-title">Структура сети</div><div class="panel-note">Ключевые узлы с приоритетом от 0,5 · стрелки показывают направление</div>', unsafe_allow_html=True)
        nodes, edges = graph_records(ctx, min_priority=.5)
        render_graph(nodes, edges, height=300)
        legend(ctx, 'role')
    with right:
        st.markdown('<div class="panel-title">В фокусе аналитика</div><div class="panel-note">Пять участников с наибольшим приоритетом</div>', unsafe_allow_html=True)
        records = top_nodes(ctx, n=5)['nodes']
        if records:
            rows = []
            for rank, row in enumerate(records, 1):
                score = float(row['priority_score'] or 0)
                label = escape(ROLE_LABELS.get(row.get('role'), 'Роль не задана'))
                rows.append(f'<div class="priority-row"><div class="priority-rank">{rank:02}</div><div><div class="priority-name">Клиент {int(row["gid"])}</div><div class="priority-role">{label}</div></div><div class="priority-score">{score:.2f}<div class="microbar"><i style="width:{score*100:.0f}%"></i></div></div></div>')
            st.markdown('<div class="priority-list">' + ''.join(rows) + '</div>', unsafe_allow_html=True)
            st.caption('Карточки и объяснения — во вкладке «Приоритеты».')
        else:
            st.info('Приоритеты появятся после загрузки результатов анализа.')
    st.divider()
    transactions_dashboard(ctx)
    with st.expander('Состав сети и качество данных'):
        network_health(ctx)
        counts = pd.Series([ROLE_LABELS.get(n.get('role'), 'Не определена') for _, n in ctx.nodes(data=True)], dtype='object').value_counts()
        if not counts.empty:
            st.bar_chart(counts.rename('Участников'), color='#168577', height=220)
    st.caption('Приоритеты и роли — результаты расчётного модуля. Они помогают выбрать направление проверки.')


def graph_page(ctx, filters, model, online):
    st.subheader("Куда движутся деньги")
    left, right = st.columns([3, 1])
    query = left.text_input(
        "Поиск по gid", placeholder="Например, 900", key="gid_query"
    )
    hops = right.selectbox("Шагов от узла", [1, 2, 3], key="ego_hops")
    highlight = None
    if query.strip():
        try:
            highlight = int(query.strip())
        except ValueError:
            st.warning("Введите целочисленный gid.")
            return
        if highlight not in ctx.graph:
            st.warning("Узел не найден. Проверь gid и загруженную выборку.")
            return
        st.caption(
            "Поиск показывает окружение узла независимо от боковых фильтров. Направления рёбер сохранены."
        )
    nodes, edges = graph_records(ctx, highlight=highlight, hops=hops, **filters)
    render_graph(nodes, edges, highlight=highlight, edge_labels=highlight is not None)
    legend(ctx, filters["color_by"])
    if highlight is not None:
        st.divider()
        show_node_card(ctx, highlight, key="graph", model=model, online=online)


def priorities(ctx, model, online):
    st.subheader("Кого проверить первым")
    data = ctx.frames["top_nodes"].copy()
    if data.empty:
        st.info("Ожидается top_nodes.csv от B.")
        return
    data = data.sort_values("rank", kind="stable").reset_index(drop=True)
    st.caption(
        "Выбери строку, чтобы открыть карточку. Приоритет — оценка для проверки, не вероятность виновности."
    )
    event = role_table(
        data,
        key=f"priority_table_{ctx.fingerprint}",
        on_select="rerun",
        selection_mode="single-row",
    )
    choices = data.gid.tolist()
    selected = event.selection.rows
    gid = choices[selected[0]] if selected and selected[0] < len(choices) else None
    manual = st.selectbox(
        "Или выбери gid из топ-листа",
        [None] + choices,
        format_func=lambda x: "Не выбран" if x is None else str(x),
        key="priority_gid",
    )
    if gid is None:
        gid = manual
    if gid is not None and gid in ctx.graph:
        nodes, edges = graph_records(ctx, highlight=int(gid), hops=1)
        with st.expander("Связи выбранного клиента", expanded=True):
            render_graph(nodes, edges, height=340, highlight=int(gid), edge_labels=True)
        show_node_card(ctx, int(gid), key="priority", model=model, online=online)


def clusters_page(ctx):
    st.subheader("Группы и их назначение")
    data = ctx.frames["clusters"]
    if data.empty:
        st.info("Ожидается clusters.csv от B.")
        return
    data = data.sort_values("cluster_id").reset_index(drop=True)
    event = st.dataframe(
        data,
        key=f"cluster_table_{ctx.fingerprint}",
        on_select="rerun",
        selection_mode="single-row",
        hide_index=True,
        width="stretch",
    )
    selected = event.selection.rows
    cid = (
        int(data.iloc[selected[0]].cluster_id)
        if selected and selected[0] < len(data)
        else None
    )
    manual = st.selectbox(
        "Кластер для просмотра",
        [None] + data.cluster_id.tolist(),
        format_func=lambda x: "Не выбран" if x is None else str(x),
        key="cluster_detail",
    )
    cid = cid if cid is not None else manual
    if cid is not None:
        row = data[data.cluster_id == cid].iloc[0]
        st.markdown(f"**Кластер {cid} · гипотеза**")
        st.write(row.hypothesis)
        nodes, edges = graph_records(
            ctx, cluster_id=int(cid), show_all=True, color_by="cluster"
        )
        render_graph(nodes, edges, height=500)
        legend(ctx, "cluster")


def resilience_page(ctx):
    st.subheader("Что изменится при изъятии узлов")
    data = ctx.frames["resilience"]
    if data.empty:
        st.info(
            "Ожидается resilience.csv от A. Симуляция не выполняет реальных блокировок."
        )
        return
    # Среднее для повторных прогонов одной стратегии; не скрываем агрегацию.
    if data.duplicated(["n_removed", "strategy"]).any():
        st.caption("Повторные прогоны одинаковой стратегии усреднены.")
    for metric, label in (
        ("lcc_share", "Доля крупнейшей связной компоненты"),
        ("flow_share", "Доля потока — метрика из выгрузки A"),
    ):
        st.markdown(f"**{label}**")
        chart = data.pivot_table(
            index="n_removed", columns="strategy", values=metric, aggfunc="mean"
        ).sort_index()
        st.line_chart(
            chart, x_label="Число удалённых узлов", y_label="Доля", height=240
        )
    st.caption(
        "Определение flow_share должно совпадать с документацией A; интерфейс показывает переданные значения без пересчёта."
    )
    with st.expander("Числа из выгрузки"):
        st.dataframe(data, hide_index=True, width="stretch")


def gaps_page(ctx):
    st.subheader("Каких данных не хватает")
    data = ctx.frames["next_requests"]
    if data.empty:
        st.info("Список следующих запросов появится после next_requests.csv от B.")
        return
    st.dataframe(data, hide_index=True, width="stretch")
    st.download_button(
        "Скачать список запросов",
        data.to_csv(index=False).encode("utf-8-sig"),
        file_name="next_requests.csv",
        mime="text/csv",
    )


def assistant_page(ctx, model, online):
    st.subheader("Спроси о связях и потоках")
    st.caption(
        "Режим: "
        + (
            "онлайн с переходом в офлайн при ошибке"
            if online
            else "офлайн · ответы по данным без LLM"
        )
    )
    with st.expander("Примеры вопросов", expanded=False):
        if ctx.demo:
            st.code(
                "Кто собирает деньги с этих пятерых: 101, 102, 103, 104, 105?\nПуть от 101 до 920\nКому платил 900?\nКарточка 900\nТоп-5 консолидаторов\nКластер 1\nЧто будет, если удалить топ-3?",
                language=None,
            )
        else:
            st.write(
                "Указывай gid из своей выборки: «Карточка …», «Кто собирает деньги с …», «Путь от … до …», «Кластер …», «Топ-10 консолидаторов»."
            )
    if st.button("Очистить диалог", key="clear_chat"):
        st.session_state["chat_history"] = []
    history = st.session_state.setdefault("chat_history", [])
    for message in history:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if message["role"] == "assistant":
                st.caption(message.get("mode", ""))
                if message.get("notice"):
                    st.info(message["notice"])
                with st.expander("Вызванные инструменты"):
                    st.json(message.get("calls", []))
    question = st.chat_input(
        "Например: кто собирает деньги с этих клиентов?", max_chars=4000
    )
    if question:
        with st.chat_message("user"):
            st.markdown(question)
        with st.chat_message("assistant"):
            with st.spinner("Проверяю данные графа…"):
                answer = ask(question, ctx, history, model, online=online)
            st.markdown(answer.text)
            st.caption(answer.mode)
            if answer.notice:
                st.info(answer.notice)
            with st.expander("Вызванные инструменты", expanded=False):
                st.json(answer.calls)
        history.extend(
            [
                {"role": "user", "content": question},
                {
                    "role": "assistant",
                    "content": answer.text,
                    **{k: v for k, v in asdict(answer).items() if k != "text"},
                },
            ]
        )
        del history[:-40]
