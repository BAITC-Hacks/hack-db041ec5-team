from pathlib import Path

import pandas as pd
import pytest
import yaml


@pytest.fixture
def cfg():
    return yaml.safe_load((Path(__file__).resolve().parents[1] / 'config.yaml').read_text(encoding='utf-8'))


@pytest.fixture
def sample_network():
    nodes = pd.DataFrame({'gid': range(1, 33), 'depth': [0] * 6 + [1] * 10 + [2] * 10 + [4] * 6,
                          'is_seed': [True] * 6 + [False] * 26})
    rows = [(i, 7, '2026-07-01', 100000) for i in range(1, 6)]
    rows += [(7, 8, '2026-07-02', 400000)]
    rows += [(8, j, '2026-07-03', 20000) for j in range(9, 29)]
    rows += [(9, 29, '2026-07-04', 20000), (10, 30, '2026-07-04', 20000)]
    tx = pd.DataFrame(rows, columns=['src', 'dst', 'date', 'sum_kzt'])
    edges = tx.groupby(['src', 'dst'], sort=False).agg(sum_kzt=('sum_kzt', 'sum'), n_tx=('sum_kzt', 'size')).reset_index()
    edges['depth'] = 1
    return nodes, edges, tx
