from pathlib import Path
import pytest

from assistant.tools import simulate_removal
from run import run_pipeline
from ui.data import load_context


def test_pipeline_exports_are_consumed_by_web_app(sample_network, tmp_path):
    nodes, edges, tx = sample_network
    data, out = tmp_path / 'data', tmp_path / 'output'
    data.mkdir()
    for name, frame in [('nodes', nodes), ('edges', edges), ('transactions', tx)]:
        frame.to_parquet(data / f'{name}.parquet', index=False)
    config = Path(__file__).resolve().parents[1] / 'config.yaml'
    with pytest.warns(UserWarning):
        run_pipeline(data, out, config)
    ctx = load_context(out, data, config)
    assert len(ctx.graph) == len(nodes)
    assert not ctx.warnings and not ctx.missing
    assert simulate_removal(ctx, [7])['available']
