"""Граф pyvis: автономный HTML, фиксированная раскладка и единая палитра."""

import math
import re
from html import escape

import networkx as nx
import streamlit as st
import streamlit.components.v1 as components
from pyvis.network import Network

from ui.constants import ROLE_COLORS, ROLE_LABELS, cluster_color, fmt_kzt


def graph_records(
    ctx,
    *,
    highlight=None,
    hops=1,
    roles=None,
    min_priority=0.5,
    cluster_id=None,
    show_all=False,
    color_by="role",
):
    if highlight is not None:
        if highlight not in ctx.graph:
            raise ValueError("Узел не найден.")
        visible = set(nx.ego_graph(ctx.graph, highlight, radius=hops, undirected=True))
    else:
        visible = {
            gid
            for gid, n in ctx.nodes(data=True)
            if (
                show_all
                or (
                    n.get("priority_score") is not None
                    and n["priority_score"] >= min_priority
                )
            )
            and (roles is None or n.get("role") in roles)
            and (cluster_id is None or n.get("cluster_id") == cluster_id)
        }
    ranked = sorted(
        ctx.graph, key=lambda g: (-(ctx.nodes[g].get("priority_score") or 0), g)
    )
    labeled = set(ranked[:50])
    nodes = []
    for gid in sorted(visible):
        n = ctx.nodes[gid]
        role, priority = n.get("role"), n.get("priority_score")
        label = ROLE_LABELS.get(role, "Роль ещё не рассчитана")
        tooltip = f"gid {gid}\n{label}\nПриоритет: {priority if priority is not None else 'нет данных'}"
        if n.get("evidence"):
            tooltip += "\n" + str(n["evidence"])
        if n.get("is_frontier"):
            tooltip += "\nГраница выборки: исходящие могут быть обрезаны."
        nodes.append(
            dict(
                id=gid,
                x=float(n["x"]),
                y=float(n["y"]),
                is_seed=bool(n.get("is_seed")),
                show_label=gid in labeled or gid == highlight,
                size=8 + 30 * (priority or 0),
                color=cluster_color(n.get("cluster_id"))
                if color_by == "cluster"
                else ROLE_COLORS.get(role, "#A0A8B5"),
                tooltip=escape(tooltip).replace("\n", "<br>"),
            )
        )
    edges = [
        dict(source=a, target=b, sum_kzt=d["sum_kzt"], n_tx=d["n_tx"])
        for a, b, d in ctx.graph.edges(data=True)
        if a in visible and b in visible
    ]
    return nodes, edges


@st.cache_data(show_spinner=False, max_entries=16)
def graph_html(nodes, edges, height=620, highlight=None, edge_labels=False):
    net = Network(
        height=f"{height}px",
        width="100%",
        directed=True,
        bgcolor="#F7FAFC",
        font_color="#273746",
        cdn_resources="in_line",
    )
    net.toggle_physics(False)
    net.set_options("""{"physics":{"enabled":false},"interaction":{"hover":true,"navigationButtons":true,"keyboard":true},
                       "edges":{"smooth":{"enabled":false},"color":{"color":"#A5B4C4","highlight":"#203F52"},"scaling":{"min":1,"max":7}},
                       "nodes":{"font":{"size":13},"borderWidth":1}}""")
    for n in nodes:
        net.add_node(
            int(n["id"]),
            label=str(n["id"]) if n["show_label"] else " ",
            x=n["x"],
            y=n["y"],
            physics=False,
            color=n["color"],
            size=n["size"],
            shape="diamond" if n["is_seed"] else "dot",
            borderWidth=5 if n["id"] == highlight else 1,
            title=n["tooltip"],
        )
    for e in edges:
        extra = {"label": fmt_kzt(e["sum_kzt"])} if edge_labels else {}
        net.add_edge(
            int(e["source"]),
            int(e["target"]),
            arrows="to",
            value=math.log1p(e["sum_kzt"]),
            title=f"{fmt_kzt(e['sum_kzt'])} · {e['n_tx']} операций",
            **extra,
        )
    html = net.generate_html()
    # В шаблоне pyvis 0.3.2 даже при in_line есть Bootstrap CDN. Меню Bootstrap
    # не используются; удаляем эти ссылки, чтобы весь граф работал без сети.
    html = re.sub(
        r'<script\b[^>]*\bsrc=["\']https?://[^>]*>\s*</script>',
        "",
        html,
        flags=re.IGNORECASE,
    )
    html = re.sub(
        r'<link\b[^>]*\bhref=["\']https?://[^>]*>', "", html, flags=re.IGNORECASE
    )
    html = html.replace(
        "</head>",
        "<style>body{margin:0;background:#F7FAFC}.card{border:0!important}#mynetwork{border:0!important;border-radius:16px}</style></head>",
    )
    return html


def render_graph(nodes, edges, height=620, highlight=None, edge_labels=False):
    if not nodes:
        st.info("Нет узлов для выбранных фильтров. Уменьши порог или включи весь граф.")
        return
    components.html(
        graph_html(nodes, edges, height, highlight, edge_labels),
        height=height + 12,
        scrolling=False,
    )
    st.caption(
        f"Показано узлов: {len(nodes)} · связей: {len(edges)}. Масштаб — колёсиком; перемещение — перетаскиванием."
    )


def legend(ctx, color_by="role"):
    if color_by == "role":
        items = [(label, ROLE_COLORS[role]) for role, label in ROLE_LABELS.items()]
    else:
        clusters = sorted(
            {
                n["cluster_id"]
                for _, n in ctx.nodes(data=True)
                if n.get("cluster_id") is not None
            }
        )
        items = [(f"Кластер {cid}", cluster_color(cid)) for cid in clusters]
    st.markdown(
        " ".join(
            f'<span class="legend-item"><i style="background:{color}"></i>{escape(label)}</span>'
            for label, color in items
        ),
        unsafe_allow_html=True,
    )
    st.caption(
        "Ромб — seed · размер — приоритет проверки · стрелка — направление денег."
    )
