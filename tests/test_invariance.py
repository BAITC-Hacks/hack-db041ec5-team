import pandas as pd
import numpy as np

from run import analyze


def test_monotone_relabeling(sample_network, cfg):
    original = analyze(*sample_network, cfg)
    nodes, edges, tx = [x.copy(deep=True) for x in sample_network]
    mapping = {gid: gid * 7919 + 1000003 for gid in nodes.gid}
    inverse = {v: k for k, v in mapping.items()}
    nodes['gid'] = nodes.gid.map(mapping)
    for table in (edges, tx):
        table['src'], table['dst'] = table.src.map(mapping), table.dst.map(mapping)
    renamed = analyze(nodes, edges, tx, cfg)
    pd.testing.assert_series_equal(original[0].cluster_id, renamed[0].cluster_id.rename(index=inverse), check_exact=True)
    for columns, offset in [(['role', 'role_score', 'secondary_role'], 1), (['priority_score', 'rank', 'freq_top20'], 2)]:
        pd.testing.assert_frame_equal(original[offset][columns], renamed[offset][columns].rename(index=inverse), check_exact=True)


def test_arbitrary_relabeling(sample_network, cfg):
    original = analyze(*sample_network, cfg)
    nodes, edges, tx = [x.copy(deep=True) for x in sample_network]
    mapping = dict(zip(nodes.gid, np.random.default_rng(17).permutation(nodes.gid)))
    inverse = {v: k for k, v in mapping.items()}
    nodes['gid'] = nodes.gid.map(mapping)
    for frame in (edges, tx):
        frame['src'], frame['dst'] = frame.src.map(mapping), frame.dst.map(mapping)
    renamed = analyze(nodes, edges, tx, cfg)
    for columns, offset in [(['role', 'role_score', 'secondary_role'], 1),
                            (['priority_score', 'rank', 'freq_top20'], 2)]:
        pd.testing.assert_frame_equal(original[offset][columns], renamed[offset][columns].rename(index=inverse))
