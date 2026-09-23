"""Построение графа, воспроизводимая раскладка и контракт интерфейса."""

import networkx as nx
import numpy as np
import pandas as pd


def build_graph(nodes, edges):
    """Построить DiGraph, сохранив изолированные узлы и сложив дубликаты рёбер."""
    if nodes.gid.isna().any() or nodes.gid.duplicated().any():
        raise ValueError('gid должны быть непустыми и уникальными')
    if not set(edges.src).union(edges.dst).issubset(set(nodes.gid)):
        raise ValueError('Концы рёбер отсутствуют в nodes')
    if not np.isfinite(edges[['sum_kzt', 'n_tx']].to_numpy(float)).all():
        raise ValueError('Суммы и количества должны быть конечными')
    if (edges[['sum_kzt', 'n_tx']] < 0).any().any():
        raise ValueError('Суммы и количества не могут быть отрицательными')
    G = nx.DiGraph()
    for row in nodes.to_dict('records'):
        gid = row.pop('gid')
        G.add_node(gid, **row)
    for row in edges.groupby(['src', 'dst'], sort=False)[['sum_kzt', 'n_tx']].sum().reset_index().to_dict('records'):
        G.add_edge(row.pop('src'), row.pop('dst'), **row)
    return G


def compute_layout(G, cfg=None):
    """Вернуть координаты с фиксированным генератором случайных чисел."""
    opts = (cfg or {}).get('layout', {})
    return nx.spring_layout(G.to_undirected(), seed=42, weight=None,
                            iterations=opts.get('iterations', 50), scale=opts.get('scale', 1500))


def _scalar(value, default=None):
    """Привести скаляр pandas/numpy к JSON-совместимому значению."""
    if pd.isna(value):
        return default
    return value.item() if isinstance(value, np.generic) else value


def build_graph_json(G, pos, F, R=None, P=None, clusters=None):
    """Собрать словарь graph.json; таблицы R/P индексированы по gid."""
    nodes = []
    for gid in G:
        point = pos.get(gid, (0, 0))
        role = R.at[gid, 'role'] if R is not None and gid in R.index else 'peripheral'
        priority = P.at[gid, 'priority_score'] if P is not None and gid in P.index else 0
        group = clusters.get(gid, 0) if clusters is not None else 0
        nodes.append({'id': _scalar(gid), 'label': str(gid), 'x': float(point[0]),
                      'y': float(point[1]), 'role': _scalar(role, 'peripheral'),
                      'priority': _scalar(priority, 0), 'cluster': _scalar(group, 0),
                      'is_seed': bool(F.at[gid, 'is_seed']), 'depth': _scalar(F.at[gid, 'depth'])})
    edges = [{'source': _scalar(u), 'target': _scalar(v), 'sum_kzt': float(d['sum_kzt']),
              'n_tx': _scalar(d['n_tx'])} for u, v, d in G.edges(data=True)]
    return {'nodes': nodes, 'edges': edges}
