import json

import numpy as np
import pandas as pd
import pytest

from moneygraph.io import ensure_valid_data, validate
from run import analyze, run_pipeline


@pytest.mark.parametrize('table,column,value', [
    (0, 'is_seed', 'False'), (0, 'is_seed', None),
    (0, 'depth', np.nan), (0, 'depth', -1), (0, 'depth', 1.5),
    (1, 'n_tx', 0.5), (1, 'sum_kzt', '100000'),
    (2, 'sum_kzt', '100000'),
])
def test_invalid_types_and_metadata_rejected(sample_network, table, column, value):
    frames = [frame.copy(deep=True) for frame in sample_network]
    dtype = object if isinstance(value, str) or value is None else float
    frames[table][column] = frames[table][column].astype(dtype)
    frames[table].loc[0, column] = value
    with pytest.raises(ValueError):
        ensure_valid_data(*frames)
    with pytest.warns(UserWarning):
        checks = validate(*frames)
    assert any(not row['ok'] for row in checks)


def test_duplicate_columns_reported(sample_network):
    nodes, edges, tx = sample_network
    nodes = pd.concat([nodes, nodes[['gid']]], axis=1)
    with pytest.raises(ValueError, match='колон'):
        ensure_valid_data(nodes, edges, tx)


@pytest.mark.parametrize('contents', [None, '', 'features: [broken', '[]', 'x: .nan'])
def test_config_failures_have_failed_report(tmp_path, contents):
    path, out = tmp_path / 'bad.yaml', tmp_path / 'out'
    if contents is not None:
        path.write_text(contents, encoding='utf-8')
    with pytest.raises(Exception):
        run_pipeline(tmp_path / 'data', out, path)
    report = json.loads((out / 'run_report.json').read_text(encoding='utf-8'))
    assert report['status'] == 'failed'
    assert report['error']


def test_uint64_gid_does_not_silently_wrap(sample_network, cfg):
    nodes, edges, tx = [frame.copy(deep=True) for frame in sample_network]
    offset = 2 ** 63
    nodes['gid'] = nodes.gid.astype('uint64') + offset
    for frame in [edges, tx]:
        for col in ['src', 'dst']:
            frame[col] = frame[col].astype('uint64') + offset
    with pytest.raises(ValueError, match='int64'):
        analyze(nodes, edges, tx, cfg)
