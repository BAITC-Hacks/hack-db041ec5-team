import json

import numpy as np
import pandas as pd
import pytest

from moneygraph.clusters import cluster, cluster_stability, cluster_summary
from moneygraph.features import add_cluster_features, compute_features
from moneygraph.graph import build_graph, build_graph_json, compute_layout
from moneygraph.io import load, validate, write_quality_report
from moneygraph.patterns import detect_patterns
from moneygraph.prepare import prepare
from moneygraph.resilience import compare_strategies, simulate_removal


@pytest.fixture
def network():
    nodes = pd.DataFrame({'gid': ['S', 'A', 'B', 'Z'], 'depth': [0, 1, 4, 0],
                          'is_seed': [True, False, False, True]})
    tx = pd.DataFrame([('S', 'A', '2026-07-01', 100), ('A', 'B', '2026-07-02', 60),
                       ('A', 'B', '2026-07-05', 40)], columns=['src', 'dst', 'date', 'sum_kzt'])
    edges = tx.groupby(['src', 'dst']).agg(sum_kzt=('sum_kzt', 'sum'), n_tx=('sum_kzt', 'size')).reset_index()
    edges['depth'] = 1
    cfg = {'attribution': {'min_source_kzt': 1}, 'clusters': {'stability_runs': 3},
           'resilience': {'sizes': [1], 'random_runs': 3}}
    return nodes, edges, tx, cfg


def test_complete_contract_and_purity(network):
    nodes, edges, tx, cfg = network
    originals = [table.copy(deep=True) for table in (nodes, edges, tx)]
    G = build_graph(nodes, edges)
    F = compute_features(G, nodes, edges, tx, cfg)
    assert F.loc['A', 'fast_pass_share'] == pytest.approx(0.6)
    assert F.loc['A', 'pass_ratio'] == 1
    assert np.isnan(F.loc['S', 'pass_ratio']) and np.isnan(F.loc['B', 'pass_ratio'])
    assert F.loc['Z', 'in_sum'] == 0 and F.loc['Z', 'seed_kzt'] == 0
    assert F.loc['B', 'seed_reach'] == 1
    groups = cluster(G, cfg)
    assert groups.loc['Z'] == 0
    F = add_cluster_features(F, G, groups)
    F, cycles = detect_patterns(G, F, cfg)
    assert cycles.empty and not F.in_cycle.any()
    assert F.n_clusters_touched.notna().all()
    stability = cluster_stability(G, groups, cfg)
    assert stability.between(0, 1).all()
    summary = cluster_summary(groups, F, edges, stability)
    assert summary.n_nodes.sum() == len(nodes)
    pos = compute_layout(G)
    payload = build_graph_json(G, pos, F, clusters=groups)
    json.dumps(payload, allow_nan=False)
    assert len(payload['nodes']) == 4
    for before, after in zip(originals, (nodes, edges, tx)):
        pd.testing.assert_frame_equal(before, after)
    pd.testing.assert_series_equal(groups, cluster(G, cfg))
    for gid, point in compute_layout(G).items():
        np.testing.assert_array_equal(point, pos[gid])


def test_removal_recomputes_flows_and_does_not_mutate(network):
    nodes, edges, tx, cfg = network
    G = build_graph(nodes, edges)
    F = compute_features(G, nodes, edges, tx, cfg)
    assert simulate_removal(G, F, edges, [], cfg)['flow_share'] == 1
    result = simulate_removal(G, F, edges, ['A'], cfg)
    assert result['flow_share'] == 0
    assert len(G) == 4 and G.number_of_edges() == 2
    scores = pd.Series([0, 1, 0, 0], index=F.index)
    first = compare_strategies(G, F, edges, scores, cfg)
    pd.testing.assert_frame_equal(first, compare_strategies(G, F, edges, scores, cfg))
    assert set(first.strategy) == {'priority', 'degree', 'random'}


def test_parquet_roundtrip_and_quality_report(network, tmp_path):
    nodes, edges, tx, _ = network
    for name, frame in [('nodes', nodes), ('edges', edges), ('transactions', tx)]:
        frame.to_parquet(tmp_path / f'{name}.parquet')
    loaded = load(tmp_path)
    pd.testing.assert_frame_equal(loaded[0], nodes)
    with pytest.warns(UserWarning):
        checks = validate(*loaded)
    assert next(row for row in checks if row['check'] == 'несогласованные пары edges/tx')['ok']
    write_quality_report(checks, tmp_path)
    assert 'Качество данных' in (tmp_path / 'data_quality.md').read_text(encoding='utf-8')
    with pytest.warns(UserWarning):
        bad = validate(nodes, edges.iloc[:0], tx)
    assert not next(row for row in bad if row['check'] == 'несогласованные пары edges/tx')['ok']


def test_duplicate_edges_and_unknown_nodes(network):
    nodes, edges, tx, cfg = network
    duplicate = pd.concat([edges, edges], ignore_index=True)
    G = build_graph(nodes, duplicate)
    F = compute_features(G, nodes, duplicate, pd.concat([tx, tx]), cfg)
    assert G['S']['A']['sum_kzt'] == 200
    assert F.loc['A', 'eff_payers'] == 1
    with pytest.raises(ValueError, match='отсутствуют'):
        build_graph(nodes.iloc[1:], edges)


def test_empty_graph(network):
    nodes, edges, tx, cfg = network
    nodes, edges, tx = nodes.iloc[:0], edges.iloc[:0], tx.iloc[:0]
    G = build_graph(nodes, edges)
    F = compute_features(G, nodes, edges, tx, cfg)
    assert F.empty and cluster(G, cfg).empty
    assert build_graph_json(G, {}, F) == {'nodes': [], 'edges': []}


def test_temporal_before_after_and_same_day(network):
    nodes, edges, tx, cfg = network
    tx.loc[1, 'date'] = '2026-06-30'
    tx.loc[2, 'date'] = '2026-07-01'
    F = compute_features(build_graph(nodes, edges), nodes, edges, tx, cfg)
    assert F.loc['A', 'fast_pass_share'] == pytest.approx(0.4)


def test_cycles_and_relabeling(network):
    nodes, edges, tx, cfg = network
    edges = pd.concat([edges, pd.DataFrame([{'src': 'B', 'dst': 'A', 'sum_kzt': 50, 'n_tx': 1, 'depth': 2}])])
    G = build_graph(nodes, edges)
    F = compute_features(G, nodes, edges, tx, cfg)
    patterned, cycles = detect_patterns(G, F, cfg)
    assert patterned.loc['A', 'in_cycle'] and patterned.loc['B', 'in_cycle']
    assert len(cycles) == 1 and cycles.iloc[0].min_edge_kzt == 50
    mapping = {'S': 50, 'A': 20, 'B': 80, 'Z': 10}
    renamed_nodes = nodes.assign(gid=nodes.gid.map(mapping))
    renamed_edges = edges.assign(src=edges.src.map(mapping), dst=edges.dst.map(mapping))
    renamed_tx = tx.assign(src=tx.src.map(mapping), dst=tx.dst.map(mapping))
    renamed = compute_features(build_graph(renamed_nodes, renamed_edges), renamed_nodes, renamed_edges, renamed_tx, cfg)
    numeric = F.select_dtypes(include='number').columns
    np.testing.assert_allclose(F[numeric], renamed[numeric], equal_nan=True)


def test_prepare_writes_artifacts(network, tmp_path):
    nodes, edges, tx, cfg = network
    for name, frame in [('nodes', nodes), ('edges', edges), ('transactions', tx)]:
        frame.to_parquet(tmp_path / f'{name}.parquet')
    out = tmp_path / 'output'
    with pytest.warns(UserWarning):
        report = prepare(tmp_path, out, cfg)
    assert report['attribution']['converged']
    assert {path.name for path in out.iterdir()} == {
        'node_features.csv', 'cluster_metrics.csv', 'cycles.csv',
        'graph.json', 'data_quality.md', 'metrics_report.json'}
    assert len(json.loads((out / 'graph.json').read_text(encoding='utf-8'))['nodes']) == 4
    assert pd.read_csv(out / 'node_features.csv').gid.is_unique


def test_microsecond_dates_match_nanosecond_dates(network):
    nodes, edges, tx, cfg = network
    G = build_graph(nodes, edges)
    expected = compute_features(G, nodes, edges, tx, cfg)
    tx['date'] = pd.to_datetime(tx.date).dt.as_unit('us')
    actual = compute_features(G, nodes, edges, tx, cfg)
    pd.testing.assert_frame_equal(expected, actual)


def test_nested_archive_layout_loads(network, tmp_path):
    nodes, edges, tx, _ = network
    nested = tmp_path / 'data'
    nested.mkdir()
    for name, frame in [('nodes', nodes), ('edges', edges), ('transactions', tx)]:
        frame.to_parquet(nested / f'{name}.parquet')
    pd.testing.assert_frame_equal(load(tmp_path)[0], nodes)


def test_graph_json_preserves_large_gid():
    ids = [2 ** 53, 2 ** 53 + 1]
    nodes = pd.DataFrame({'gid': ids, 'depth': [0, 1], 'is_seed': [True, False]})
    edges = pd.DataFrame({'src': [ids[0]], 'dst': [ids[1]], 'sum_kzt': [100], 'n_tx': [1]})
    G = build_graph(nodes, edges)
    payload = build_graph_json(G, {}, nodes.set_index('gid'))
    assert [node['id'] for node in payload['nodes']] == list(map(str, ids))
    assert payload['edges'][0]['source'] == str(ids[0])
    assert payload['edges'][0]['target'] == str(ids[1])
