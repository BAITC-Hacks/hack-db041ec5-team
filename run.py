"""One-command pipeline: parquet data to explainable graph exports."""

import argparse
from contextlib import contextmanager
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import platform
from time import perf_counter

import yaml
import networkx as nx
import pandas as pd

from moneygraph.clusters import cluster, cluster_stability, cluster_summary
from moneygraph.export import export
from moneygraph.features import add_cluster_features, compute_features
from moneygraph.gaps import next_requests
from moneygraph.graph import build_graph
from moneygraph.hypotheses import summarize_clusters
from moneygraph.io import ensure_valid_data, load, validate, write_quality_report
from moneygraph.patterns import detect_patterns
from moneygraph.priority import prioritize
from moneygraph.resilience import compare_strategies
from moneygraph.roles import assign_roles


@contextmanager
def stage(name, timings):
    start = perf_counter()
    try:
        yield
    finally:
        timings[name] = round(perf_counter() - start, 4)
        print(f'[{name}] {timings[name]:.4f} s')


def analyze(nodes, edges, tx, cfg, timings=None):
    """Core in-memory pipeline; failures never substitute dummy results."""
    t = {} if timings is None else timings
    ensure_valid_data(nodes, edges, tx)
    if nodes.empty:
        raise ValueError('В nodes нет узлов для анализа')
    if (not pd.api.types.is_integer_dtype(nodes.gid.dtype)
            or any(int(gid) < -(2 ** 63) or int(gid) > 2 ** 63 - 1 for gid in nodes.gid)):
        raise ValueError('Для итоговых CSV gid должны быть целыми идентификаторами int64')
    with stage('graph', t):
        G = build_graph(nodes, edges)
    with stage('features', t):
        F = compute_features(G, nodes, edges, tx, cfg)
        F['median_out'] = tx.groupby('src').sum_kzt.median().reindex(F.index)
        daily = tx.assign(day=pd.to_datetime(tx.date, utc=True).dt.floor('D')).groupby(['dst', 'day']).src.nunique().reset_index(name='n_payers')
        peak = daily.sort_values(['n_payers', 'day'], ascending=[False, True], kind='stable').drop_duplicates('dst').set_index('dst')
        F['max_payers_date'] = peak.day.dt.strftime('%d.%m').reindex(F.index)
    with stage('clusters', t):
        # A's tie ordering compares stringified gid. Positional labels make
        # clustering independent of identifier spelling without editing A.
        labels = dict(enumerate(G))
        canonical = nx.relabel_nodes(G, {gid: pos for pos, gid in labels.items()}, copy=True)
        groups = cluster(canonical, cfg).rename(index=labels).reindex(F.index)
        F = add_cluster_features(F, G, groups)
        F['cluster_id'] = groups
    with stage('roles', t):
        R = assign_roles(F, groups, G, cfg)
    with stage('priority', t):
        P = prioritize(F, R, cfg)
    with stage('hypotheses', t):
        C = summarize_clusters(F, R, P, groups, edges, cfg)
    return F, R, P, C, G


def run_pipeline(data_dir='data', out_dir='output', config_path='config.yaml'):
    started, timings = perf_counter(), {}
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    report = {'status': 'running', 'python': platform.python_version()}
    try:
        with stage('config', timings):
            config_bytes = Path(config_path).read_bytes()
            report['config_sha1'] = hashlib.sha1(config_bytes).hexdigest()
            cfg = yaml.safe_load(config_bytes)
            if not isinstance(cfg, dict):
                raise ValueError('Конфигурация должна быть непустым YAML-словарём')
            # Reject non-finite or non-JSON values before storing the config in
            # the report, so error reporting cannot mask the original failure.
            json.dumps(cfg, allow_nan=False)
            report['config'] = cfg
            report['versions'] = {p: version(p) for p in ['pandas', 'numpy', 'scipy', 'networkx', 'pyarrow', 'PyYAML']}
        with stage('load', timings):
            nodes, edges, tx = load(Path(data_dir))
        with stage('validate', timings):
            checks = validate(nodes, edges, tx)
            write_quality_report(checks, out)
        F, R, P, C, G = analyze(nodes, edges, tx, cfg, timings)
        extras = {}
        with stage('gaps', timings):
            extras['next_requests'] = next_requests(F, R, P, cfg)
        if cfg['extras']['patterns']:
            with stage('patterns', timings):
                F, extras['cycles'] = detect_patterns(G, F, cfg)
            report['cycles_truncated'] = extras['cycles'].attrs.get('truncated', False)
        if cfg['extras']['cluster_stability']:
            with stage('cluster_stability', timings):
                stable = cluster_stability(G, F.cluster_id, cfg)
                extras['cluster_metrics'] = cluster_summary(F.cluster_id, F, edges, stable)
        if cfg['extras']['resilience']:
            with stage('resilience', timings):
                extras['resilience'] = compare_strategies(G, F, edges, P.priority_score, cfg)
        with stage('export', timings):
            export(R, P, C, F, G, out, cfg, extras)
        report.update(status='ok', n_nodes=len(F), n_edges=G.number_of_edges(),
                      role_counts={k: int(v) for k, v in R.role.value_counts().items()},
                      attribution=F.attrs.get('attribution', {}), priority_stability=P.attrs['stability'],
                      quality_warnings=sum(not row['ok'] for row in checks))
    except Exception as exc:
        report.update(status='failed', error=f'{type(exc).__name__}: {exc}')
        raise
    finally:
        report.update(timings_seconds=timings, elapsed_seconds=round(perf_counter() - started, 4))
        (out / 'run_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', default='data')
    parser.add_argument('--out', default='output')
    parser.add_argument('--config', default='config.yaml')
    args = parser.parse_args()
    try:
        report = run_pipeline(args.data, args.out, args.config)
    except (ValueError, KeyError, FileNotFoundError, yaml.YAMLError) as exc:
        parser.exit(1, f'Pipeline failed: {exc}\n')
    print(f'OK: {report["n_nodes"]} nodes, {report["elapsed_seconds"]:.2f} s')


if __name__ == '__main__':
    main()
