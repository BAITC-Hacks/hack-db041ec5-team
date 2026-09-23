import json
from pathlib import Path
import subprocess
import sys
import warnings

import pandas as pd
import pytest
import yaml

from moneygraph.export import SCHEMAS
from moneygraph.io import resolve_data_dir, load
from moneygraph.roles import ROLES
from run import run_pipeline


def check_outputs(out, expected):
    tables = {name: pd.read_csv(out / name) for name in SCHEMAS}
    for name, columns in SCHEMAS.items():
        assert tables[name].columns.tolist() == columns
        assert not (out / name).read_bytes().startswith(b'\xef\xbb\xbf')
    R, C, P = (tables[name] for name in SCHEMAS)
    assert len(R) == R.gid.nunique() == expected
    assert R.gid.dtype == 'int64' and R.cluster_id.dtype == 'int64'
    assert R.role.isin(ROLES).all()
    assert R.role_score.between(0, 1).all() and R.priority_score.between(0, 1).all()
    assert R.evidence.str.len().between(1, 200).all()
    assert set(R.cluster_id) == set(C.cluster_id)
    assert C.hypothesis.str.len().gt(0).all()
    assert C.n_nodes.sum() == expected
    assert len(P) == min(50, expected)
    assert P['rank'].tolist() == list(range(1, len(P) + 1))
    assert P.priority_score.is_monotonic_decreasing and P.why.str.len().gt(0).all()
    assert P.gid.is_unique and set(P.gid) <= set(R.gid)
    node_priority = R.set_index('gid').priority_score
    assert P.priority_score.equals(P.gid.map(node_priority).rename('priority_score'))
    graph = json.loads((out / 'graph.json').read_text(encoding='utf-8'))
    assert len(graph['nodes']) == expected
    ids = {node['id'] for node in graph['nodes']}
    assert ids == set(R.gid.astype(str))
    assert all(edge['source'] in ids and edge['target'] in ids for edge in graph['edges'])
    report = json.loads((out / 'run_report.json').read_text(encoding='utf-8'))
    assert report['status'] == 'ok' and report['elapsed_seconds'] > 0
    assert 0 <= report['priority_stability']['mean_jaccard'] <= 1
    features = pd.read_csv(out / 'node_features.csv')
    assert not ((features.is_frontier) & (features.role == 'terminal')).any()


def test_end_to_end(tmp_path, sample_network, cfg):
    data, out = tmp_path / 'data', tmp_path / 'output'
    data.mkdir()
    for name, frame in zip(['nodes', 'edges', 'transactions'], sample_network):
        frame.to_parquet(data / f'{name}.parquet', index=False)
    cfg['resilience'].update(sizes=[1, 5], random_runs=2)
    cfg['clusters']['stability_runs'] = 2
    path = tmp_path / 'config.yaml'
    path.write_text(yaml.safe_dump(cfg), encoding='utf-8')
    with pytest.warns(UserWarning):
        run_pipeline(data, out, path)
    check_outputs(out, len(sample_network[0]))


@pytest.fixture(scope='session')
def real_output(tmp_path_factory):
    root = Path(__file__).resolve().parents[1]
    try:
        data = resolve_data_dir(root / 'data')
    except FileNotFoundError:
        pytest.skip('Реальные parquet-файлы организаторов отсутствуют')
    out = tmp_path_factory.mktemp('real-output')
    with warnings.catch_warnings():
        warnings.simplefilter('error', RuntimeWarning)
        run_pipeline(data, out, root / 'config.yaml')
    return out


def test_real_outputs(real_output):
    check_outputs(real_output, 2248)
    report = json.loads((real_output / 'run_report.json').read_text(encoding='utf-8'))
    assert report['elapsed_seconds'] < 300
    assert report['attribution']['converged']
    F = pd.read_csv(real_output / 'node_features.csv')
    assert F.loc[F.is_frontier, 'role'].isin(['consolidator', 'peripheral']).all()
    assert F.loc[F.is_seed, 'pass_ratio'].isna().all()
    assert F.loc[(F.in_deg + F.out_deg) == 0, 'cluster_id'].eq(0).all()


def test_real_metrics_match_organizer_starter(real_output):
    import importlib.util
    import numpy as np
    root = Path(__file__).resolve().parents[1]
    starter = root / 'starter' / 'starter' / 'starter.py'
    if not starter.exists():
        pytest.skip('Starter организаторов отсутствует')
    spec = importlib.util.spec_from_file_location('organizer_starter', starter)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    nodes, edges, _ = load(root / 'data')
    baseline = module.basic_features(module.build_graph(edges), nodes).set_index('gid')
    actual = pd.read_csv(real_output / 'node_features.csv').set_index('gid').loc[baseline.index]
    for ours, theirs in [('in_sum', 'in_kzt'), ('out_sum', 'out_kzt'),
                         ('in_deg', 'in_deg'), ('out_deg', 'out_deg'), ('in_tx', 'in_tx'), ('out_tx', 'out_tx')]:
        np.testing.assert_allclose(actual[ours], baseline[theirs], atol=1e-7)
    np.testing.assert_array_equal(actual.is_frontier, baseline.truncated_by_depth)
    assert actual.index.equals(baseline.index)


def test_real_outputs_in_ui_and_offline_tools(real_output):
    from assistant.tools import get_node, simulate_removal
    from ui.data import load_context
    from ui.graph_view import graph_records, graph_html
    root = Path(__file__).resolve().parents[1]
    ctx = load_context(real_output, root / 'data', root / 'config.yaml')
    assert not ctx.warnings and not ctx.missing
    assert len(ctx.graph) == 2248 and len(ctx.tx) == 4840
    gid = int(ctx.frames['top_nodes'].iloc[0].gid)
    assert get_node(ctx, str(gid))['gid'] == gid
    nodes, edges = graph_records(ctx, highlight=gid)
    html = graph_html(nodes, edges, highlight=gid)
    assert f'"id": "{gid}"' in html
    assert simulate_removal(ctx, [gid])['available']


def test_real_streamlit_search(real_output, monkeypatch):
    from streamlit.testing.v1 import AppTest
    root = Path(__file__).resolve().parents[1]
    monkeypatch.setenv('MONEYGRAPH_OUTPUT_DIR', str(real_output))
    monkeypatch.setenv('MONEYGRAPH_DATA_DIR', str(root / 'data'))
    monkeypatch.setenv('MONEYGRAPH_DEMO', '0')
    gid = str(pd.read_csv(real_output / 'top_nodes.csv').iloc[0].gid)
    app = AppTest.from_file(str(root / 'app.py'), default_timeout=60).run()
    assert not app.exception and len(app.tabs) == 7
    app.text_input(key='gid_query').set_value(gid).run()
    assert not app.exception
    assert any(f'gid {gid}' in item.value for item in app.markdown)


def test_failed_core_is_reported(tmp_path):
    with pytest.raises(FileNotFoundError):
        run_pipeline(tmp_path / 'missing', tmp_path / 'out')
    report = json.loads((tmp_path / 'out' / 'run_report.json').read_text(encoding='utf-8'))
    assert report['status'] == 'failed'


def test_cli_with_default_config(tmp_path, sample_network):
    """Проверить объединённый A/B через CLI со всеми штатными extras."""
    root = Path(__file__).resolve().parents[1]
    data, out = tmp_path / 'data', tmp_path / 'output'
    data.mkdir()
    for name, frame in zip(['nodes', 'edges', 'transactions'], sample_network):
        frame.to_parquet(data / f'{name}.parquet', index=False)
    result = subprocess.run(
        [sys.executable, str(root / 'run.py'), '--data', str(data),
         '--out', str(out), '--config', str(root / 'config.yaml')],
        cwd=root, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=300,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    check_outputs(out, len(sample_network[0]))
    for name in ['resilience', 'cycles', 'cluster_metrics', 'next_requests']:
        assert (out / f'{name}.csv').exists()
    resilience = pd.read_csv(out / 'resilience.csv')
    assert len(resilience) == 12
    assert set(resilience.strategy) == {'priority', 'degree', 'random'}
    report = json.loads((out / 'run_report.json').read_text(encoding='utf-8'))
    assert report['attribution']['converged']
    assert report['priority_stability']['runs'] == 200
