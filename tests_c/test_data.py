import json

import pandas as pd
from ui.data import file_signature, load_context


def test_empty_and_broken_inputs_do_not_crash(tmp_path):
    ctx = load_context(tmp_path, tmp_path, tmp_path / "config.yaml")
    assert not ctx.graph and "graph.json" in ctx.missing
    (tmp_path / "graph.json").write_text("{broken", encoding="utf-8")
    (tmp_path / "nodes_roles.csv").write_text("gid,role\n1,unknown", encoding="utf-8")
    ctx = load_context(tmp_path, tmp_path, tmp_path / "config.yaml")
    assert len(ctx.warnings) == 2 and not ctx.graph


def test_csv_overrides_stale_graph_and_preserves_isolates(tmp_path):
    graph = {
        "nodes": [
            {"id": 1, "x": 0, "y": 0, "role": "peripheral", "priority": 0.1},
            {"id": 2, "x": 1, "y": 0},
        ],
        "edges": [],
    }
    (tmp_path / "graph.json").write_text(json.dumps(graph))
    pd.DataFrame(
        [
            dict(
                gid=1,
                role="consolidator",
                role_score=0.8,
                cluster_id=1,
                priority_score=0.9,
                evidence="example",
            )
        ]
    ).to_csv(tmp_path / "nodes_roles.csv", index=False)
    ctx = load_context(tmp_path, tmp_path, tmp_path / "config.yaml")
    assert set(ctx.graph) == {1, 2}
    assert (
        ctx.nodes[1]["role"] == "consolidator" and ctx.nodes[1]["priority_score"] == 0.9
    )


def test_f_v0_fallback_and_transactions(tmp_path):
    pd.DataFrame(
        [
            dict(gid=1, depth=0, is_seed=True),
            dict(gid=2, depth=4, is_seed=False),
            dict(gid=3, depth=0, is_seed=True),
        ]
    ).to_parquet(tmp_path / "nodes.parquet")
    pd.DataFrame([dict(src=1, dst=2, sum_kzt=8000, n_tx=1)]).to_parquet(
        tmp_path / "edges.parquet"
    )
    pd.DataFrame([dict(src=1, dst=2, sum_kzt=8000, date="invalid")]).to_parquet(
        tmp_path / "transactions.parquet"
    )
    ctx = load_context(tmp_path, tmp_path, tmp_path / "config.yaml")
    assert set(ctx.graph) == {1, 2, 3}
    assert ctx.nodes[2]["is_frontier"] is True
    assert ctx.nodes[2].get("role") is None
    assert ctx.tx.empty and all("x" in n for _, n in ctx.nodes(data=True))


def test_change_signature_when_data_changes(tmp_path):
    before = file_signature(tmp_path, tmp_path, tmp_path / "config.yaml")
    (tmp_path / "graph.json").write_text("{}")
    after = file_signature(tmp_path, tmp_path, tmp_path / "config.yaml")
    assert before != after


def test_unknown_edge_endpoint_is_reported(tmp_path):
    (tmp_path / "graph.json").write_text(
        json.dumps(
            {
                "nodes": [dict(id=1, x=0, y=0)],
                "edges": [dict(source=1, target=2, sum_kzt=6000, n_tx=1)],
            }
        )
    )
    ctx = load_context(tmp_path, tmp_path, tmp_path / "config.yaml")
    assert any("неизвестный узел" in w for w in ctx.warnings)
