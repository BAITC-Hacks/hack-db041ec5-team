"""Сценарии удаления узлов с повторной атрибуцией на оставшейся сети."""

import networkx as nx
import numpy as np
import pandas as pd

from .features import structural_features
from .flow import attribute_sources


def simulate_removal(G, F, edges, removed, cfg):
    """Пересчитать остаточную сеть; знаменатели берутся из исходной сети."""
    removed = set(removed)
    remaining = F.loc[~F.index.isin(removed)]
    kept_edges = edges.loc[~edges.src.isin(removed) & ~edges.dst.isin(removed)].copy()
    nodes = remaining[['depth', 'is_seed']].rename_axis('gid').reset_index()
    updated = structural_features(nodes, kept_edges, cfg)
    attributed = attribute_sources(updated, kept_edges, cfg)
    subgraph = G.subgraph(remaining.index)
    sizes = [len(c) for c in nx.weakly_connected_components(subgraph)]
    active_before = sum(G.degree(v) > 0 for v in G)
    min_depth = cfg.get('resilience', {}).get('min_flow_depth', 2)
    base = attribute_sources(F, edges, cfg)
    before = float(base.loc[F.depth >= min_depth, 'seed_kzt'].sum())
    after = float(attributed.loc[updated.depth >= min_depth, 'seed_kzt'].sum())
    return {'lcc_share': max(sizes, default=0) / active_before if active_before else 0.0,
            'n_components': len(sizes), 'flow_share': after / before if before else np.nan}


def compare_strategies(G, F, edges, priority, cfg):
    """Сравнить приоритет, степень и среднее случайных изъятий; seed=42."""
    opts = cfg.get('resilience', {})
    rng, rows = np.random.default_rng(42), []
    runs = int(opts.get('random_runs', 20))
    if runs < 1:
        raise ValueError('random_runs должен быть положительным')
    ranking = priority.reindex(F.index)
    if ranking.isna().any():
        raise ValueError('priority_score должен быть задан для всех gid')
    degree = (F.in_deg + F.out_deg).sort_values(ascending=False, kind='stable').index
    ranked = ranking.sort_values(ascending=False, kind='stable').index
    for requested in opts.get('sizes', [5, 10, 20, 50]):
        count = min(int(requested), len(F))
        if count < 0:
            raise ValueError('Размер изъятия не может быть отрицательным')
        for strategy, order in [('priority', ranked), ('degree', degree)]:
            rows.append({'strategy': strategy, 'n_removed': count,
                         **simulate_removal(G, F, edges, order[:count], cfg)})
        trials = [simulate_removal(G, F, edges,
                  F.index[rng.choice(len(F), size=count, replace=False)], cfg) for _ in range(runs)]
        mean = pd.DataFrame(trials).mean().to_dict()
        rows.append({'strategy': 'random', 'n_removed': count, **mean})
    return pd.DataFrame(rows, columns=['strategy', 'n_removed', 'lcc_share', 'n_components', 'flow_share'])
