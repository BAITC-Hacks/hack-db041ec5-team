import networkx as nx
import numpy as np
import pandas as pd
import pytest

from moneygraph.roles import assign_roles


def features():
    f = pd.DataFrame(0.0, index=pd.Index(range(8), name='gid'), columns=[
        'depth', 'in_deg', 'out_deg', 'in_sum', 'out_sum', 'eff_payers', 'eff_receivers',
        'seed_sources', 'seed_kzt', 'betweenness', 'n_clusters_touched', 'fast_pass_share'])
    f['is_seed'] = False
    f['is_frontier'] = False
    f['pass_ratio'] = np.nan
    f.loc[0, ['in_deg', 'in_sum', 'eff_payers']] = [8, 100000, 8]
    f.loc[0, ['out_sum', 'pass_ratio']] = [50000, 0.5]
    f.loc[1, ['out_deg', 'out_sum', 'eff_receivers']] = [60, 100000, 60]
    f.loc[2, ['in_deg', 'out_deg', 'in_sum', 'out_sum', 'pass_ratio']] = [1, 1, 100000, 100000, 1]
    f.loc[3, ['in_deg', 'in_sum', 'depth']] = [1, 100000, 4]
    f.loc[3, 'is_frontier'] = True
    f.loc[4, 'is_seed'] = True
    f.loc[5, ['in_deg', 'in_sum', 'pass_ratio']] = [1, 100000, 0]
    f.loc[6, ['in_deg', 'in_sum']] = [1, 100000]
    f.loc[6, 'is_seed'] = True
    return f


def assign(f, cfg, graph=None):
    g = graph if graph is not None else nx.empty_graph(f.index, create_using=nx.DiGraph)
    return assign_roles(f, pd.Series(1, index=f.index), g, cfg)


def test_base_roles_and_frontier(cfg):
    f = features()
    before = f.copy(deep=True)
    r = assign(f, cfg)
    assert r.role.tolist() == ['consolidator', 'distributor', 'transit', 'peripheral', 'peripheral', 'terminal', 'terminal', 'peripheral']
    assert r.role_score.between(0, 1).all()
    assert r.loc[3, 'role_score'] <= 0.5
    assert r.evidence.str.len().between(1, 200).all()
    assert r.evidence.str.contains('признаки', case=False).all()
    pd.testing.assert_frame_equal(f, before)


def test_coordinator_requires_two_real_signals(cfg):
    f = features()
    f.loc[7, ['seed_sources', 'n_clusters_touched']] = [5, 3]
    r = assign(f, cfg)
    assert r.loc[7, 'role'] == 'coordinator'
    f.loc[7, 'n_clusters_touched'] = np.nan
    assert assign(f, cfg).loc[7, 'role'] == 'peripheral'


def test_tie_secondary_and_missing_v1_v2(cfg):
    f = features()
    f.loc[0, ['in_deg', 'out_deg', 'eff_payers', 'eff_receivers', 'seed_sources']] = [12, 40, 12, 40, 5]
    r = assign(f, cfg)
    assert r.loc[0, 'role'] == 'consolidator'
    assert r.loc[0, 'secondary_role'] == 'distributor'
    f[['seed_sources', 'betweenness', 'n_clusters_touched', 'fast_pass_share']] = np.nan
    assert assign(f, cfg).role_score.notna().all()


def test_seed_transit_and_frontier_override(cfg):
    f = features()
    f.loc[2, 'is_seed'] = True
    f.loc[2, 'pass_ratio'] = np.nan
    assert assign(f, cfg).loc[2, 'role_score'] == pytest.approx(0.24)
    f.loc[2, 'is_frontier'] = True
    assert assign(f, cfg).loc[2, 'role'] == 'peripheral'
