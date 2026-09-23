from io import BytesIO
from pathlib import Path
import sys

import pandas as pd
import pytest
import yaml

from moneygraph.patterns import transaction_patterns
from moneygraph.uploads import save_uploads
from run import run_pipeline
from ui.data import load_context

CONFIG = Path(__file__).resolve().parents[1] / 'config.yaml'


def files_for(frames, extension):
    result = []
    for name, frame in zip(['nodes', 'edges', 'transactions'], frames):
        stream = BytesIO()
        if extension == 'csv':
            stream.write(frame.to_csv(index=False).encode('utf-8'))
        else:
            frame.to_parquet(stream, index=False)
        result.append((name + '.' + extension, stream.getvalue()))
    return result


@pytest.mark.parametrize('extension', ['csv', 'parquet'])
def test_different_data_upload_to_results(sample_network, tmp_path, extension):
    nodes, edges, tx = [x.copy() for x in sample_network]
    mapping = {int(g): 100000000000000000 + int(g) * 19 for g in nodes.gid}
    nodes.gid = nodes.gid.map(mapping)
    nodes.depth = nodes.depth.replace(4, 6)
    for frame in (edges, tx):
        frame.src = frame.src.map(mapping)
        frame.dst = frame.dst.map(mapping)
        frame.sum_kzt *= 1.7
    tx.date = tx.date.str.replace('2026-07-', '2026-09-', regex=False)
    out, data, cfg = save_uploads(files_for((nodes, edges, tx), extension), tmp_path, CONFIG, None)
    assert yaml.safe_load(cfg.read_text())['dataset_profile'] == 'generic'
    report = run_pipeline(data, out, cfg)
    assert report['status'] == 'ok' and report['quality_warnings'] == 0
    roles = pd.read_csv(out / 'nodes_roles.csv')
    assert set(roles.gid) == set(mapping.values()) and len(roles) == 32
    ctx = load_context(out, data, cfg)
    assert not ctx.warnings and not ctx.missing
    assert not pd.read_csv(out / 'node_features.csv').is_frontier.any()
    assert len(ctx.tx) == len(tx)
    assert (out / 'splitting.csv').is_file() and (out / 'repeated_routes.csv').is_file()


def test_upload_rejects_missing_duplicate_and_inconsistent(sample_network, tmp_path):
    files = files_for(sample_network, 'csv')
    with pytest.raises(ValueError, match='Не хватает'):
        save_uploads(files[:2], tmp_path, CONFIG)
    with pytest.raises(ValueError, match='Повторный'):
        save_uploads(files + files[:1], tmp_path, CONFIG)
    nodes, edges, tx = [x.copy() for x in sample_network]
    edges.loc[0, 'sum_kzt'] += 100
    with pytest.raises(ValueError, match='не совпадает'):
        save_uploads(files_for((nodes, edges, tx), 'csv'), tmp_path, CONFIG)
    assert not list(tmp_path.iterdir())


def test_repeated_routes_require_order_and_distinct_days():
    tx = pd.DataFrame([(1, 2, '2026-01-01', 100), (2, 3, '2026-01-02', 95),
                       (1, 2, '2026-01-05', 100), (2, 3, '2026-01-06', 95)],
                      columns=['src', 'dst', 'date', 'sum_kzt'])
    result = transaction_patterns(tx, {})['repeated_routes']
    assert len(result) == 1 and result.iloc[0].episodes == 2
    assert result.iloc[0].path == '1→2→3'
    tx.loc[tx.src == 2, 'date'] = ['2025-12-30', '2026-01-04']
    assert transaction_patterns(tx, {})['repeated_routes'].empty
    duplicate = pd.concat([tx.iloc[:1], tx.iloc[:1], tx.iloc[:1]])
    assert transaction_patterns(duplicate, {})['repeated_routes'].empty


def test_splitting_similar_amounts_and_no_false_threshold_claim():
    tx = pd.DataFrame([(1, 2, '2026-01-01', 9000), (1, 2, '2026-01-01', 9500),
                       (1, 2, '2026-01-01', 10000), (3, 2, '2026-01-01', 9000)],
                      columns=['src', 'dst', 'date', 'sum_kzt'])
    result = transaction_patterns(tx, {})['splitting']
    assert len(result) == 1 and result.iloc[0].n_tx == 3
    assert result.iloc[0].sum_kzt == 28500
    tx.loc[2, 'sum_kzt'] = 100000
    assert transaction_patterns(tx, {})['splitting'].empty


def test_no_api_key_needed_to_open_app(monkeypatch, tmp_path):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv('OPENAI_API_KEY', '')
    monkeypatch.setenv('MONEYGRAPH_LLM_PROVIDER', 'openai')
    monkeypatch.setenv('MONEYGRAPH_OUTPUT_DIR', str(tmp_path))
    monkeypatch.setenv('MONEYGRAPH_DATA_DIR', str(tmp_path))
    monkeypatch.setenv('MONEYGRAPH_DEMO', '0')
    app = AppTest.from_file(str(CONFIG.parent / 'app.py'), default_timeout=30).run()
    assert not app.exception and len(app.chat_input) == 1
    assert any(x.label == 'Загрузить и проанализировать' for x in app.button)


def test_analysis_button_loads_fresh_result(sample_network, monkeypatch, tmp_path):
    from streamlit.testing.v1 import AppTest
    data = tmp_path / 'data'
    data.mkdir()
    for name, frame in zip(['nodes', 'edges', 'transactions'], sample_network):
        frame.to_parquet(data / (name + '.parquet'), index=False)
    monkeypatch.setenv('MONEYGRAPH_OUTPUT_DIR', str(tmp_path / 'empty'))
    monkeypatch.setenv('MONEYGRAPH_DATA_DIR', str(data))
    monkeypatch.setenv('MONEYGRAPH_DEMO', '0')
    app = AppTest.from_file(str(CONFIG.parent / 'app.py'), default_timeout=60).run()
    with pytest.warns(UserWarning):
        app.button(key='analyze_local').click().run()
    assert not app.exception
    assert app.session_state['active_analysis']
    assert any('Анализ завершён' in x.value for x in app.success)
