import json
import sys
from types import SimpleNamespace

import pytest
from assistant import tools
from assistant.fallback import ask
from ui.data import assemble
from ui.graph_view import graph_html, graph_records
from ui.node_card import daily_transactions


def test_convergence_ceil_threshold_duplicates_direction(ctx):
    result = tools.common_downstream(ctx, [101, 102, 103, 104, 105, 105])
    assert result["min_sources"] == 3
    by_id = {n["gid"]: n for n in result["nodes"]}
    assert by_id[900]["source_count"] == 5
    assert by_id[900]["hops_by_source"] == {
        "101": 1,
        "102": 1,
        "103": 2,
        "104": 2,
        "105": 1,
    }
    assert tools.common_downstream(ctx, [920])["nodes"] == []
    assert (
        tools.common_downstream(
            ctx, [101, 102, 103, 104, 105], max_hops=1, min_sources=5
        )["nodes"]
        == []
    )


def test_unknown_source_is_not_silently_dropped(ctx):
    result = tools.execute(ctx, "common_downstream", {"gids": [101, 102, 999999]})
    assert "error" in result and "999999" in result["error"]


def test_path_cutoff_direction_and_amount_semantics(ctx):
    assert tools.money_path(ctx, 101, 920, max_len=3)["paths"] == []
    result = tools.money_path(ctx, 101, 920, max_len=4)
    assert result["paths"][0]["gids"] == [101, 900, 901, 910, 920]
    assert result["paths"][0]["min_edge_kzt"] == 120000
    assert result["paths"][0]["min_edge_kzt"] != sum(
        e["sum_kzt"] for e in result["paths"][0]["edges"]
    )
    assert tools.money_path(ctx, 920, 101)["paths"] == []


def test_neighbors_direction_threshold_and_isolated_node(ctx):
    incoming = tools.neighbors(ctx, 900, direction="in", min_kzt=100000)
    assert {n["gid"] for n in incoming["nodes"]} == {101, 202}
    assert tools.neighbors(ctx, 940)["nodes"] == []
    assert {n["gid"] for n in tools.neighbors(ctx, 900, direction="out")["nodes"]} == {
        901
    }


@pytest.mark.parametrize(
    "name,args",
    [
        ("unknown", {}),
        ("get_node", {"gid": True}),
        ("neighbors", {"gid": 900, "hops": 99}),
        ("money_path", {"src": 101, "dst": 920, "max_len": 0}),
        ("common_downstream", {"gids": []}),
        ("top_nodes", {"n": -1}),
        ("get_node", {"gid": 900, "extra": "ignored?"}),
    ],
)
def test_invalid_tool_arguments_are_safe(ctx, name, args):
    assert "error" in tools.execute(ctx, name, args)


def test_node_missing_metrics_are_null_not_invented(ctx):
    record = tools.get_node(ctx, 900)
    assert record["metrics"]["seed_kzt"] is None
    assert record["incoming"][0]["role"] == "peripheral"
    json.dumps(record, allow_nan=False)


def test_priority_role_and_cluster_filters(ctx):
    ranked = tools.top_nodes(ctx, role="consolidator", cluster_id=1, n=3)
    assert [r["gid"] for r in ranked["nodes"]] == [900]


@pytest.mark.parametrize(
    "question,tool",
    [
        ("Кому платил 900?", "neighbors"),
        ("От кого получал 900?", "neighbors"),
        (
            "Кто собирает деньги с этих пятерых: 101,102,103,104,105?",
            "common_downstream",
        ),
        ("Путь от 101 до 920", "money_path"),
        ("Топ-5 консолидаторов кластера 1", "top_nodes"),
        ("Кластер 1", "cluster_info"),
        ("Карточка 900", "get_node"),
        ("Что будет если заблокировать топ-3?", "simulate_removal"),
    ],
)
def test_offline_intents(ctx, question, tool):
    text, calls = ask(question, ctx)
    assert text and calls[-1]["tool"] == tool
    assert "error" not in calls[-1]["result"]


def test_single_digit_gid_is_supported():
    ctx = assemble({}, {"nodes": [dict(id=1, x=0, y=0)], "edges": []})
    text, calls = ask("Карточка 1", ctx)
    assert calls[0]["args"] == {"gid": 1}


def test_simulation_adapter_calls_a_without_mutating_context(ctx, monkeypatch):
    ctx.demo = False
    ctx.cfg = {"seed": 42}
    original_nodes = set(ctx.graph)
    original_metric = ctx.frames["node_features"].iloc[0].in_sum

    def simulate(G, F, edges, removed, cfg):
        assert F.index.name == "gid" and removed == [900]
        G.remove_node(900)
        F.iloc[0, F.columns.get_loc("in_sum")] = 999
        cfg["seed"] = 0
        return {"lcc_share": 0.5, "flow_share": 0.3}

    monkeypatch.setitem(sys.modules, "moneygraph", SimpleNamespace())
    monkeypatch.setitem(
        sys.modules, "moneygraph.resilience", SimpleNamespace(simulate_removal=simulate)
    )
    result = tools.simulate_removal(ctx, [900])
    assert result["available"] and result["result"]["flow_share"] == 0.3
    assert set(ctx.graph) == original_nodes and ctx.cfg["seed"] == 42
    assert ctx.frames["node_features"].iloc[0].in_sum == original_metric


def test_ego_preserves_edges_and_overrides_filters(ctx):
    nodes, edges = graph_records(
        ctx, highlight=900, hops=1, roles=[], min_priority=1, cluster_id=99
    )
    assert 900 in {n["id"] for n in nodes}
    assert (101, 900) in {(e["source"], e["target"]) for e in edges}
    assert (900, 101) not in {(e["source"], e["target"]) for e in edges}


def test_graph_is_offline_and_text_is_escaped(ctx):
    import re

    ctx.nodes[900]["evidence"] = '<script>alert("x")</script>'
    nodes, edges = graph_records(ctx, highlight=900)
    assert "&lt;script&gt;" in next(n["tooltip"] for n in nodes if n["id"] == 900)
    html = graph_html(nodes, edges)
    assert not re.search(
        r'<(?:script|link)\b[^>]+(?:src|href)=["\']https?://', html, re.IGNORECASE
    )


def test_daily_aggregation_reconciles_with_edges(ctx):
    df = daily_transactions(ctx, 900)
    assert df[df["Поток"] == "Входящие"]["KZT"].sum() == 464000
    assert df[df["Поток"] == "Исходящие"]["KZT"].sum() == 410000


def test_paths_stay_simple_when_graph_contains_cycle(ctx):
    ctx.graph.add_edge(901, 900, sum_kzt=6000, n_tx=1)
    result = tools.money_path(ctx, 101, 920, max_len=8)
    assert result["paths"]
    assert all(len(p["gids"]) == len(set(p["gids"])) for p in result["paths"])
