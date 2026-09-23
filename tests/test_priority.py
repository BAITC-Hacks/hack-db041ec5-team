import numpy as np
import pandas as pd
import pytest

from moneygraph.gaps import next_requests
from moneygraph.priority import prioritize
from run import analyze


def test_priority_formula_stability_and_purity(sample_network, cfg):
    F, R, P, _, _ = analyze(*sample_network, cfg)
    original = F.copy(deep=True)
    expected = sum(P[key] * weight for key, weight in cfg['priority']['weights'].items())
    expected *= np.where(F.is_seed, cfg['priority']['seed_discount'], 1)
    np.testing.assert_allclose(P.priority_score, expected)
    pd.testing.assert_frame_equal(P, prioritize(F, R, cfg))
    pd.testing.assert_frame_equal(F, original)
    assert P.freq_top20.between(0, 1).all()
    assert P.freq_top20.sum() == pytest.approx(20)
    assert P.why.str.contains('Признаки').all()


def test_gaps_counts_and_selected_nodes(sample_network, cfg):
    F, R, P, _, _ = analyze(*sample_network, cfg)
    requests = next_requests(F, R, P, cfg)
    assert requests.columns.tolist() == ['request_type', 'n_nodes', 'gids', 'why']
    assert requests.loc[2, 'n_nodes'] == 20
    for row in requests.itertuples():
        ids = [int(x) for x in row.gids.split(';') if x]
        assert len(ids) == min(row.n_nodes, cfg['gaps']['max_gids'])
        assert set(ids) <= set(F.index)


def test_zero_weight_supported_and_invalid_sum_rejected(sample_network, cfg):
    F, R, _, _, _ = analyze(*sample_network, cfg)
    cfg['priority']['weights'] = dict(money=1, convergence=0, position=0, role=0)
    P = prioritize(F, R, cfg)
    assert P.attrs['stability']['mean_jaccard'] == 1
    cfg['priority']['weights']['money'] = 2
    with pytest.raises(ValueError, match='Веса'):
        prioritize(F, R, cfg)
