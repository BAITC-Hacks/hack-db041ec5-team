"""Ограниченный поиск циклов и робастные аномалии внутри колена."""

from itertools import islice

import networkx as nx
import numpy as np
import pandas as pd


def robust_z(series, groups):
    """Вернуть z по MAD; при нулевом MAD оценка не определена (NaN)."""
    median = series.groupby(groups).transform('median')
    mad = (series - median).abs().groupby(groups).transform('median')
    return (series - median) / (1.4826 * mad.where(mad > 0))


def detect_patterns(G, F, cfg):
    """Вернуть новую F и таблицу cycles; in_cycle относится к найденным циклам."""
    opts = cfg.get('patterns', {})
    limit = int(opts.get('max_cycles', 10000))
    cycles = list(islice(nx.simple_cycles(G, length_bound=opts.get('max_length', 5)), limit + 1))
    truncated = len(cycles) > limit
    result, rows, members = F.copy(), [], set()
    for number, cycle in enumerate(cycles[:limit], 1):
        members.update(cycle)
        path = cycle + cycle[:1]
        rows.append({'cycle_id': number, 'length': len(cycle), 'path': '→'.join(map(str, path)),
                     'has_seed': bool(F.loc[cycle, 'is_seed'].any()),
                     'min_edge_kzt': min(G[u][v]['sum_kzt'] for u, v in zip(path, path[1:]))})
    scores = [robust_z(np.log1p(F.in_sum), F.depth), robust_z(F.in_deg, F.depth),
              robust_z(F.out_deg, F.depth)]
    result['anomaly_z'] = pd.concat(scores, axis=1).abs().max(axis=1)
    result['in_cycle'] = result.index.isin(members)
    table = pd.DataFrame(rows, columns=['cycle_id', 'length', 'path', 'has_seed', 'min_edge_kzt'])
    table.attrs['truncated'] = truncated
    result.attrs['cycles_truncated'] = truncated
    return result, table
