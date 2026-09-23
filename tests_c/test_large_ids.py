import pandas as pd

from ui.data import assemble, load_context
from ui.graph_view import graph_records, graph_html


def test_html_keeps_adjacent_large_ids_distinct():
    a, b = 2 ** 53, 2 ** 53 + 1
    ctx = assemble({}, {'nodes': [dict(id=str(a), x=0, y=0), dict(id=str(b), x=1, y=1)],
                        'edges': [dict(source=str(a), target=str(b), sum_kzt=100, n_tx=1)]})
    nodes, edges = graph_records(ctx, show_all=True)
    html = graph_html(nodes, edges)
    for gid in (a, b):
        assert f'"id": "{gid}"' in html
    assert f'"from": "{a}"' in html and f'"to": "{b}"' in html


def test_nested_data_transactions_are_loaded(tmp_path):
    nested = tmp_path / 'data'
    nested.mkdir()
    pd.DataFrame([dict(src=1, dst=2, date='2026-07-01', sum_kzt=5000)]).to_parquet(nested / 'transactions.parquet')
    ctx = load_context(tmp_path, tmp_path, tmp_path / 'config.yaml')
    assert len(ctx.tx) == 1
