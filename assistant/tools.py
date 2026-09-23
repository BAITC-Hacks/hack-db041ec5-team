"""Семь ограниченных инструментов. Только чтение данных и адаптер к модулю A."""

import importlib
import math
from collections import defaultdict
from copy import deepcopy

import networkx as nx
import pandas as pd
from ui.constants import METRIC_LABELS, ROLE_COLORS, STABILITY_COLUMNS
from ui.data import clean, gid_int


def _gid(ctx, gid):
    gid = gid_int(gid)
    if gid not in ctx.graph:
        raise ValueError(f"Узел gid={gid} не найден в загруженном графе.")
    return gid


def _integer(value, default, lo, hi, name):
    value = default if value is None else gid_int(value)
    if not lo <= value <= hi:
        raise ValueError(f"{name}: допустимо от {lo} до {hi}.")
    return value


def _summary(ctx, gid):
    n = ctx.nodes[gid]
    return clean(
        {
            "gid": gid,
            "role": n.get("role"),
            "priority_score": n.get("priority_score"),
            "cluster_id": n.get("cluster_id"),
        }
    )


def _counterparties(ctx, gid, direction):
    pairs = (
        ctx.graph.in_edges(gid, data=True)
        if direction == "in"
        else ctx.graph.out_edges(gid, data=True)
    )
    rows = []
    for src, dst, attrs in pairs:
        other = src if direction == "in" else dst
        rows.append(
            {
                **_summary(ctx, other),
                "sum_kzt": round(attrs["sum_kzt"], 2),
                "n_tx": attrs["n_tx"],
            }
        )
    return sorted(rows, key=lambda x: (-x["sum_kzt"], x["gid"]))[:5]


def get_node(ctx, gid):
    gid = _gid(ctx, gid)
    n = ctx.nodes[gid]
    result = {
        **_summary(ctx, gid),
        "role_score": n.get("role_score"),
        "rank": n.get("rank"),
        "evidence": str(n.get("evidence") or "Обоснование от B пока не загружено.")[
            :700
        ],
        "why": str(n.get("why") or "")[:700],
        "rule_fired": str(n.get("rule_fired") or "")[:1000],
        "metrics": {k: n.get(k) for k in METRIC_LABELS},
        "scores": {r: n.get(f"score_{r}") for r in ROLE_COLORS},
        "incoming": _counterparties(ctx, gid, "in"),
        "outgoing": _counterparties(ctx, gid, "out"),
        "freq_top20": next(
            (n[k] for k in STABILITY_COLUMNS if n.get(k) is not None), None
        ),
    }
    return clean(result)


def neighbors(ctx, gid, direction="both", hops=1, min_kzt=0):
    gid = _gid(ctx, gid)
    direction = direction or "both"
    if direction not in ("in", "out", "both"):
        raise ValueError("direction: in, out или both.")
    hops = _integer(hops, 1, 1, 3, "hops")
    min_kzt = float(min_kzt or 0)
    if not math.isfinite(min_kzt) or min_kzt < 0:
        raise ValueError("min_kzt должно быть неотрицательным числом.")
    filtered = nx.DiGraph()
    filtered.add_nodes_from(ctx.graph)
    filtered.add_edges_from(
        (a, b, d) for a, b, d in ctx.graph.edges(data=True) if d["sum_kzt"] >= min_kzt
    )
    walk = (
        filtered.reverse(copy=False)
        if direction == "in"
        else (filtered.to_undirected(as_view=True) if direction == "both" else filtered)
    )
    distances = nx.single_source_shortest_path_length(walk, gid, cutoff=hops)
    rows = []
    for other, distance in distances.items():
        if other == gid:
            continue
        rows.append(
            {
                **_summary(ctx, other),
                "hops": distance,
                "direct_out_kzt": filtered.get_edge_data(gid, other, {}).get(
                    "sum_kzt", 0
                ),
                "direct_in_kzt": filtered.get_edge_data(other, gid, {}).get(
                    "sum_kzt", 0
                ),
            }
        )
    rows.sort(
        key=lambda r: (r["hops"], -(r["direct_in_kzt"] + r["direct_out_kzt"]), r["gid"])
    )
    return clean(
        {
            "gid": gid,
            "direction": direction,
            "hops": hops,
            "total": len(rows),
            "nodes": rows[:15],
            "truncated": len(rows) > 15,
            "note": "Суммы относятся только к прямым рёбрам; для непрямых соседей это не сумма по цепочке.",
        }
    )


def common_downstream(ctx, gids, max_hops=4, min_sources=None):
    if not isinstance(gids, list) or not gids or len(gids) > 50:
        raise ValueError("Нужен список от 1 до 50 gid.")
    sources = list(dict.fromkeys(_gid(ctx, g) for g in gids))
    max_hops = _integer(max_hops, 4, 1, 8, "max_hops")
    threshold = _integer(
        min_sources, math.ceil(0.6 * len(sources)), 1, len(sources), "min_sources"
    )
    reached = defaultdict(dict)
    for source in sources:
        for node, distance in nx.single_source_shortest_path_length(
            ctx.graph, source, cutoff=max_hops
        ).items():
            if distance and node not in sources:
                reached[node][source] = distance
    rows = []
    for gid, distances in reached.items():
        if len(distances) >= threshold:
            rows.append(
                {
                    **_summary(ctx, gid),
                    "source_count": len(distances),
                    "source_gids": sorted(distances),
                    "hops_by_source": distances,
                    "min_hops": min(distances.values()),
                    "max_hops": max(distances.values()),
                }
            )
    rows.sort(
        key=lambda r: (
            -r["source_count"],
            -(r["priority_score"] or 0),
            r["max_hops"],
            r["gid"],
        )
    )
    return clean(
        {
            "source_gids": sources,
            "min_sources": threshold,
            "max_hops": max_hops,
            "total": len(rows),
            "nodes": rows[:10],
            "truncated": len(rows) > 10,
            "note": "Это направленная достижимость в графе, не доказанная атрибуция конкретных денег и не вывод о виновности.",
        }
    )


def money_path(ctx, src, dst, max_len=5):
    src, dst = _gid(ctx, src), _gid(ctx, dst)
    max_len = _integer(max_len, 5, 1, 8, "max_len")
    if src == dst:
        raise ValueError("Для пути укажи два разных gid.")
    # Ограничены и результаты, и перебор ветвей: islice(all_simple_paths) сам по себе
    # не ограничивает время поиска на густом графе без подходящих маршрутов.
    distance_to_dst = nx.single_source_shortest_path_length(
        ctx.graph.reverse(copy=False), dst, cutoff=max_len
    )
    paths, stack, expansions = [], [(src, [src])], 0
    while stack and expansions < 20000 and len(paths) < 200:
        node, path = stack.pop()
        expansions += 1
        if node == dst:
            amounts = [ctx.graph[a][b]["sum_kzt"] for a, b in zip(path, path[1:])]
            paths.append(
                {
                    "gids": path,
                    "hops": len(path) - 1,
                    "min_edge_kzt": round(min(amounts), 2),
                    "edges": [
                        {"src": a, "dst": b, "sum_kzt": ctx.graph[a][b]["sum_kzt"]}
                        for a, b in zip(path, path[1:])
                    ],
                }
            )
            continue
        if len(path) - 1 >= max_len:
            continue
        for nxt in sorted(ctx.graph.successors(node), reverse=True):
            if (
                nxt not in path
                and len(path) + distance_to_dst.get(nxt, max_len + 1) <= max_len
            ):
                stack.append((nxt, path + [nxt]))
    paths.sort(key=lambda r: (-r["min_edge_kzt"], r["hops"], r["gids"]))
    return clean(
        {
            "src": src,
            "dst": dst,
            "paths": paths[:3],
            "candidates_checked": len(paths),
            "search_truncated": bool(stack),
            "max_len": max_len,
            "note": "min_edge_kzt — минимальный агрегированный оборот ребра, не установленная сумма перевода по всей цепочке. Временной порядок не проверяется.",
        }
    )


def top_nodes(ctx, role=None, cluster_id=None, n=10):
    n = _integer(n, 10, 1, 50, "n")
    if role is not None and role not in ROLE_COLORS:
        raise ValueError("Неизвестная роль.")
    cluster_id = gid_int(cluster_id) if cluster_id is not None else None
    rows = []
    for gid, node in ctx.nodes(data=True):
        if node.get("priority_score") is None:
            continue
        if role is not None and node.get("role") != role:
            continue
        if cluster_id is not None and node.get("cluster_id") != cluster_id:
            continue
        rows.append(
            {
                **_summary(ctx, gid),
                "rank": node.get("rank"),
                "why": str(node.get("why") or node.get("evidence") or "")[:500],
            }
        )
    rows.sort(
        key=lambda r: (
            -(r["priority_score"] or 0),
            r["rank"] if r["rank"] is not None else math.inf,
            r["gid"],
        )
    )
    return clean(
        {"nodes": rows[:n], "total": len(rows), "role": role, "cluster_id": cluster_id}
    )


def cluster_info(ctx, cluster_id):
    cluster_id = gid_int(cluster_id)
    df = ctx.frames["clusters"]
    found = df[df.cluster_id == cluster_id] if not df.empty else pd.DataFrame()
    if found.empty:
        raise ValueError(f"Кластер {cluster_id} не найден в clusters.csv.")
    result = clean(found.iloc[0].to_dict())
    result["hypothesis"] = str(result.get("hypothesis") or "")[:1200]
    result["top_nodes"] = top_nodes(ctx, cluster_id=cluster_id, n=10)["nodes"]
    return result


def simulate_removal(ctx, gids):
    if not isinstance(gids, list) or not gids or len(gids) > 50:
        raise ValueError("Нужен список от 1 до 50 gid.")
    gids = list(dict.fromkeys(_gid(ctx, g) for g in gids))
    if ctx.demo:
        return {
            "available": False,
            "reason": "В демо нет расчётного модуля A. Переключись на данные команды.",
            "gids": gids,
        }
    if not ctx.cfg or ctx.frames["node_features"].empty:
        return {
            "available": False,
            "reason": "Для симуляции нужны config.yaml и node_features.csv от A/B.",
            "gids": gids,
        }
    try:
        module = importlib.import_module("moneygraph.resilience")
        result = module.simulate_removal(
            deepcopy(ctx.graph),
            ctx.frames["node_features"].set_index("gid").copy(deep=True),
            ctx.edges.copy(deep=True),
            gids,
            deepcopy(ctx.cfg),
        )
    except (ImportError, AttributeError, NotImplementedError):
        return {
            "available": False,
            "reason": "Модуль A moneygraph.resilience.simulate_removal ещё не подключён.",
            "gids": gids,
        }
    except Exception:
        return {
            "available": False,
            "reason": "Модуль A не смог рассчитать сценарий. Проверьте контракт и config.yaml.",
            "gids": gids,
        }
    return {"available": True, "gids": gids, "result": clean(result)}


TOOLS = {
    f.__name__: f
    for f in (
        get_node,
        neighbors,
        common_downstream,
        money_path,
        top_nodes,
        cluster_info,
        simulate_removal,
    )
}


def execute(ctx, name, args):
    """Одинаковая проверка аргументов для модели и офлайн-маршрутизатора."""
    from jsonschema import ValidationError, validate

    from assistant.schemas import PARAMETERS

    if name not in TOOLS:
        return {"error": "Неизвестный инструмент."}
    try:
        validate(args, PARAMETERS[name])
        return clean(TOOLS[name](ctx, **args))
    except (ValidationError, ValueError, TypeError) as exc:
        message = exc.message if isinstance(exc, ValidationError) else str(exc)
        return {"error": message[:350]}
    except Exception:
        return {
            "error": "Инструмент не смог обработать данные. Проверьте формат выгрузок."
        }
