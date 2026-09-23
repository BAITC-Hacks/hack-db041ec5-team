"""Локальная точка проверки части A до интеграции в командный run.py."""

import argparse
import json
from pathlib import Path
from time import perf_counter

from .clusters import cluster, cluster_stability, cluster_summary
from .features import compute_features, add_cluster_features
from .graph import build_graph, compute_layout, build_graph_json
from .io import load, validate, write_quality_report, ensure_valid_data
from .patterns import detect_patterns


def prepare(data_dir, out_dir, cfg=None):
    """Сохранить артефакты A и вернуть отчёт; обязательные CSV формирует модуль B."""
    started, cfg = perf_counter(), cfg or {}
    nodes, edges, tx = load(data_dir)
    checks = validate(nodes, edges, tx)
    out = Path(out_dir)
    write_quality_report(checks, out)
    ensure_valid_data(nodes, edges, tx)
    G = build_graph(nodes, edges)
    F = compute_features(G, nodes, edges, tx, cfg)
    attribution = F.attrs['attribution'].copy()
    groups = cluster(G, cfg)
    stability = cluster_stability(G, groups, cfg)
    summary = cluster_summary(groups, F, edges, stability)
    F = add_cluster_features(F, G, groups)
    F, cycles = detect_patterns(G, F, cfg)
    F['cluster_id'] = groups
    F.to_csv(out / 'node_features.csv')
    summary.to_csv(out / 'cluster_metrics.csv', index=False)
    cycles.to_csv(out / 'cycles.csv', index=False)
    payload = build_graph_json(G, compute_layout(G, cfg), F, clusters=groups)
    (out / 'graph.json').write_text(json.dumps(payload, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    multi_seed = int(((summary.n_seed > 1) & (summary.cluster_id != 0)).sum())
    checks.append({'check': 'кластеры с несколькими seed (ориентир ТЗ)',
                   'expected': 8, 'actual': multi_seed, 'ok': multi_seed == 8})
    write_quality_report(checks, out)
    report = {'elapsed_seconds': perf_counter() - started, 'n_nodes': len(F),
              'n_edges': G.number_of_edges(), 'attribution': attribution,
              'cycles_truncated': cycles.attrs['truncated']}
    (out / 'metrics_report.json').write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    return report


def main():
    """Запустить часть A с настройками по умолчанию или JSON-словарём cfg."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', default='data')
    parser.add_argument('--out', default='output')
    parser.add_argument('--config-json', help='Необязательный JSON-словарь cfg; общий YAML читает run.py участника B')
    args = parser.parse_args()
    cfg = json.loads(Path(args.config_json).read_text(encoding='utf-8')) if args.config_json else {}
    print(json.dumps(prepare(args.data, args.out, cfg), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
