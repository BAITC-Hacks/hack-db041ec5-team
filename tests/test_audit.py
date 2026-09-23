"""Независимые проверки формул и ошибочных входных данных."""
import warnings
from time import perf_counter

import numpy as np
import pandas as pd
import pytest

from moneygraph.features import structural_features
from moneygraph.flow import attribute_sources
from moneygraph.io import validate
from moneygraph.prepare import prepare
from run import run_pipeline


def test_attribution_against_linear_system():
    rng = np.random.default_rng(123)
    for _ in range(15):
        n = 12
        weights = rng.uniform(1, 1000, (n, n))
        weights[rng.random((n, n)) < 0.75] = 0
        np.fill_diagonal(weights, 0)
        src, dst = np.nonzero(weights)
        edges = pd.DataFrame({'src': src, 'dst': dst, 'sum_kzt': weights[src, dst], 'n_tx': 1})
        nodes = pd.DataFrame({'gid': range(n), 'depth': 1, 'is_seed': np.arange(n) < 3})
        F = structural_features(nodes, edges, {})
        denom = np.maximum(F.in_sum, F.out_sum).to_numpy()
        denom[denom == 0] = 1
        transfer = weights.T / denom[None, :]
        external = np.zeros((n, 4))
        external[np.arange(n), np.where(np.arange(n) < 3, np.arange(n), 3)] = (F.out_sum - F.in_sum).clip(lower=0)
        expected = np.linalg.solve(np.eye(n) - transfer, transfer @ external)
        result = attribute_sources(F, edges, {'attribution': {'max_iter': 10000, 'tol_kzt': 1e-10}})
        np.testing.assert_allclose(result.seed_kzt, expected[:, :3].sum(axis=1), atol=1e-6)
        np.testing.assert_allclose(result.ext_kzt, expected[:, 3], atol=1e-6)
        np.testing.assert_allclose(result.seed_kzt + result.ext_kzt, F.in_sum, atol=1e-6)


def test_prepare_rejects_negative_transactions(tmp_path):
    nodes = pd.DataFrame({'gid': [1, 2], 'depth': [0, 1], 'is_seed': [True, False]})
    edges = pd.DataFrame({'src': [1], 'dst': [2], 'depth': [1], 'sum_kzt': [100], 'n_tx': [1]})
    tx = pd.DataFrame({'src': [1], 'dst': [2], 'date': ['2026-07-01'], 'sum_kzt': [-100]})
    for name, frame in [('nodes', nodes), ('edges', edges), ('transactions', tx)]:
        frame.to_parquet(tmp_path / f'{name}.parquet')
    with pytest.warns(UserWarning), pytest.raises(ValueError, match='transactions.sum_kzt'):
        prepare(tmp_path, tmp_path / 'out')


def test_nullable_invalid_amount_is_reported():
    nodes = pd.DataFrame({'gid': [1, 2], 'depth': [0, 1], 'is_seed': [True, False]})
    edges = pd.DataFrame({'src': [1], 'dst': [2], 'depth': [1], 'sum_kzt': [100], 'n_tx': [1]})
    tx = pd.DataFrame({'src': [1], 'dst': [2], 'date': ['2026-07-01'],
                       'sum_kzt': pd.Series([pd.NA], dtype='Float64')})
    with pytest.warns(UserWarning):
        checks = validate(nodes, edges, tx)
    row = next(c for c in checks if c['check'] == 'transactions.sum_kzt: невалидные значения')
    assert row['actual'] == 1 and not row['ok']


def test_representative_size_pipeline(tmp_path):
    rng = np.random.default_rng(42)
    n = 2248
    pairs = {(i % 81, i) for i in range(81, n)}
    while len(pairs) < 3119:
        a, b = sorted(rng.choice(n, size=2, replace=False))
        pairs.add((int(a), int(b)))
    edges = pd.DataFrame(sorted(pairs), columns=['src', 'dst'])
    edges['sum_kzt'], edges['n_tx'], edges['depth'] = 10000.0, 1, 1
    tx = edges[['src', 'dst', 'sum_kzt']].assign(date='2026-07-01')
    # Match the task's transaction count while retaining identical edge totals.
    split = tx.iloc[:1721].copy()
    split['sum_kzt'] /= 2
    tx.loc[:1720, 'sum_kzt'] /= 2
    tx = pd.concat([tx, split], ignore_index=True)
    edges.loc[:1720, 'n_tx'] = 2
    nodes = pd.DataFrame({'gid': range(n), 'depth': np.where(np.arange(n) < 81, 0, 2),
                          'is_seed': np.arange(n) < 81})
    for name, frame in [('nodes', nodes), ('edges', edges), ('transactions', tx)]:
        frame.to_parquet(tmp_path / f'{name}.parquet')
    start = perf_counter()
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', UserWarning)
        report = run_pipeline(tmp_path, tmp_path / 'out')
    print(f'\nFull A/B: synthetic 2248 nodes / 3119 edges / 4840 tx: {perf_counter() - start:.2f}s')
    assert report['status'] == 'ok'
    assert len(pd.read_csv(tmp_path / 'out' / 'nodes_roles.csv')) == n
    assert len(pd.read_csv(tmp_path / 'out' / 'top_nodes.csv')) == 50
    assert len(pd.read_csv(tmp_path / 'out' / 'resilience.csv')) == 12
    assert report['attribution']['converged']
    assert report['attribution']['unattributed_kzt'] < 0.1
