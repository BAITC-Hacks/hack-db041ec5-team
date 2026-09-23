"""Пропорциональная атрибуция наблюдаемых входящих денег."""

import warnings

import networkx as nx
import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix


def attribute_sources(F, edges, cfg):
    """Вернуть суммы по seed/EXT; диагностика сходимости хранится в attrs."""
    opts = cfg.get('attribution', {})
    limit, tol = int(opts.get('max_iter', 200)), float(opts.get('tol_kzt', 1e-6))
    if limit < 1 or tol <= 0:
        raise ValueError('max_iter >= 1 и tol_kzt > 0 обязательны')
    gids = F.index
    seeds = gids[F.is_seed.astype(bool)]
    n, k = len(gids), len(seeds)
    positions = pd.Series(np.arange(n), index=gids)
    incoming, outgoing = F.in_sum.to_numpy(float), F.out_sum.to_numpy(float)
    excess = np.maximum(outgoing - incoming, 0)
    denom = np.maximum(incoming, outgoing)
    denom = np.where(denom > 0, denom, 1)
    matrix = csr_matrix((edges.sum_kzt.to_numpy(float),
                         (positions.loc[edges.dst], positions.loc[edges.src])), shape=(n, n))
    own = np.full(n, k)
    own[positions.loc[seeds].to_numpy()] = np.arange(k)
    external = np.zeros((n, k + 1))
    external[np.arange(n), own] = excess
    attributed = np.zeros_like(external)
    converged, residual = False, 0.0
    for iteration in range(1, limit + 1):
        updated = matrix @ ((attributed + external) / denom[:, None])
        residual = float(np.max(np.abs(updated - attributed), initial=0))
        attributed = updated
        if residual < tol:
            converged = True
            break
    seed_part = attributed[:, :k]
    threshold = np.maximum(opts.get('min_source_kzt', 10000),
                           opts.get('min_source_share', 0.01) * incoming)
    top = np.argsort(-seed_part, axis=1, kind='stable')[:, :3]
    result = pd.DataFrame({'seed_kzt': seed_part.sum(axis=1), 'ext_kzt': attributed[:, k],
        'seed_sources': ((seed_part >= threshold[:, None]) & (seed_part > 0)).sum(axis=1),
        'top_seeds': [';'.join(str(seeds[j]) for j in row if seed_part[i, j] > 0)
                      for i, row in enumerate(top)]}, index=gids)
    unknown = float(np.maximum(incoming - attributed.sum(axis=1), 0).sum())
    result.attrs.update(converged=converged, iterations=iteration, residual_kzt=residual,
                        unattributed_kzt=unknown)
    if not converged or unknown > tol * max(n, 1) * 10:
        warnings.warn(f'Атрибуция: converged={converged}; не атрибутировано {unknown:.6g} KZT',
                      RuntimeWarning, stacklevel=2)
    return result


def centrality_features(G, F, cfg):
    """Посчитать достижимость seed и направленные центральности."""
    reach = pd.Series(0, index=F.index, dtype=int)
    for seed in F.index[F.is_seed.astype(bool)]:
        reachable = nx.descendants(G, seed)
        if reachable:
            reach.loc[list(reachable)] += 1
    opts = cfg.get('features', {})
    pagerank = nx.pagerank(G, weight='sum_kzt', max_iter=opts.get('pagerank_max_iter', 1000))
    sample = opts.get('betweenness_k')
    sample = min(sample, len(G)) if sample is not None else None
    between = nx.betweenness_centrality(G, k=sample, normalized=True, seed=42)
    return pd.DataFrame({'seed_reach': reach, 'pagerank_w': pd.Series(pagerank),
                         'betweenness': pd.Series(between)}, index=F.index).fillna(0)
