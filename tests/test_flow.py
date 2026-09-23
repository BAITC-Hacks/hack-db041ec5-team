import pandas as pd
import pytest

from moneygraph.flow import attribute_sources


def fixture(rows, seeds):
    edges = pd.DataFrame(rows, columns=['src', 'dst', 'sum_kzt'])
    gids = sorted(set(edges.src) | set(edges.dst) | set(seeds))
    f = pd.DataFrame(index=pd.Index(gids, name='gid'))
    f['is_seed'] = f.index.isin(seeds)
    f['in_sum'] = edges.groupby('dst').sum_kzt.sum().reindex(gids, fill_value=0)
    f['out_sum'] = edges.groupby('src').sum_kzt.sum().reindex(gids, fill_value=0)
    return f, edges


CFG = {'attribution': {'min_source_kzt': 1, 'tol_kzt': 1e-8, 'max_iter': 1000}}


def test_chain_and_external_source():
    f, edges = fixture([('S', 'B', 100), ('B', 'C', 100), ('D', 'C', 50)], ['S'])
    before = f.copy(deep=True)
    result = attribute_sources(f, edges, CFG)
    assert result.loc['C', 'seed_kzt'] == pytest.approx(100)
    assert result.loc['C', 'ext_kzt'] == pytest.approx(50)
    assert result.loc['C', 'seed_sources'] == 1
    assert result.loc['S', 'seed_kzt'] == 0
    pd.testing.assert_frame_equal(f, before)


def test_cycle_with_retention_converges():
    f, edges = fixture([('S', 'A', 100), ('A', 'B', 100), ('B', 'A', 50)], ['S'])
    result = attribute_sources(f, edges, CFG)
    assert result.attrs['converged']
    assert result.loc['A', 'seed_kzt'] == pytest.approx(150)
    assert result.loc['B', 'seed_kzt'] == pytest.approx(100)


def test_closed_cycle_has_unknown_origin():
    f, edges = fixture([('A', 'B', 100), ('B', 'A', 100)], ['A'])
    with pytest.warns(RuntimeWarning, match='не атрибутировано'):
        result = attribute_sources(f, edges, CFG)
    assert result.seed_kzt.sum() == 0
    assert result.ext_kzt.sum() == 0
    assert result.attrs['unattributed_kzt'] == pytest.approx(200)


def test_iteration_limit_is_reported():
    f, edges = fixture([('S', 'A', 100), ('A', 'B', 100)], ['S'])
    with pytest.warns(RuntimeWarning):
        result = attribute_sources(f, edges, {'attribution': {'max_iter': 1}})
    assert not result.attrs['converged']


def test_no_seed_and_isolated_node():
    f, edges = fixture([('A', 'B', 50)], [])
    result = attribute_sources(f, edges, CFG)
    assert result.loc['B', 'ext_kzt'] == 50
    assert result.seed_sources.sum() == 0
    empty_f, empty_edges = fixture([], ['S'])
    assert attribute_sources(empty_f, empty_edges, CFG).loc['S', 'seed_kzt'] == 0
