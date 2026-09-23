"""Кластеры Louvain и устойчивость их состава."""

import networkx as nx
import numpy as np
import pandas as pd


def _undirected(G):
    """Сложить log1p-веса встречных направлений."""
    U = nx.Graph()
    U.add_nodes_from(G)
    for u, v, data in G.edges(data=True):
        weight = float(np.log1p(data['sum_kzt']))
        if weight > 0:
            U.add_edge(u, v, w=U.get_edge_data(u, v, {}).get('w', 0) + weight)
    return U


def _communities(U, cfg, seed):
    """Отдельно обработать изоляты, затем компоненты с положительными весами."""
    active = U.subgraph([v for v in U if U.degree(v) > 0])
    if not active:
        return []
    return nx.community.louvain_communities(active, weight='w', seed=seed,
                       resolution=cfg.get('clusters', {}).get('resolution', 1.0))


def cluster(G, cfg):
    """Назначить каждому узлу кластер; 0 зарезервирован для изолятов."""
    communities = _communities(_undirected(G), cfg, 42)
    def order(members):
        turnover = sum(d['sum_kzt'] for _, _, d in G.subgraph(members).edges(data=True))
        return -turnover, tuple(sorted(str(v) for v in members))
    result = pd.Series(0, index=pd.Index(list(G), name='gid'), dtype=int, name='cluster_id')
    for number, members in enumerate(sorted(communities, key=order), 1):
        result.loc[list(members)] = number
    return result


def cluster_stability(G, clusters, cfg):
    """Средняя максимальная доля кластера, оставшаяся вместе в каждом прогоне."""
    runs = int(cfg.get('clusters', {}).get('stability_runs', 20))
    if runs < 1:
        return pd.Series(np.nan, index=sorted(clusters.unique()), name='stability')
    U = _undirected(G)
    groups = {cid: set(clusters.index[clusters == cid]) for cid in clusters.unique()}
    scores = {cid: [] for cid in groups}
    for seed in range(runs):
        partition = _communities(U, cfg, seed)
        for cid, members in groups.items():
            scores[cid].append(1.0 if cid == 0 else
                               max((len(members & c) / len(members) for c in partition), default=0))
    return pd.Series({cid: float(np.mean(values)) for cid, values in scores.items()}, name='stability')


def cluster_summary(clusters, F, edges, stability=None):
    """Сводка для B; устойчивость передаётся результатом cluster_stability."""
    rows = []
    source, target = edges.src.map(clusters), edges.dst.map(clusters)
    for cid in sorted(clusters.unique()):
        members = clusters.index[clusters == cid]
        rows.append({'cluster_id': cid, 'n_nodes': len(members),
                     'n_seed': int(F.loc[members, 'is_seed'].sum()),
                     'sum_kzt_internal': float(edges.loc[(source == cid) & (target == cid), 'sum_kzt'].sum()),
                     'stability': float(stability.get(cid, np.nan)) if stability is not None else np.nan})
    return pd.DataFrame(rows, columns=['cluster_id', 'n_nodes', 'n_seed', 'sum_kzt_internal', 'stability'])
