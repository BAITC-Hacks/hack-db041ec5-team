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


def transaction_patterns(tx, cfg):
    """Temporal route hypotheses and repeated similar payments, never money tracing."""
    opts = cfg.get('patterns', {})
    window = float(opts.get('route_window_days', 2))
    min_days = int(opts.get('route_min_days', 2))
    pair_limit = int(opts.get('max_route_pairs', 50000))
    min_payments = int(opts.get('split_min_payments', 3))
    tolerance = float(opts.get('split_amount_tolerance', .2))
    if window < 0 or min_days < 2 or pair_limit < 1 or min_payments < 2 or tolerance < 0:
        raise ValueError('Некорректные параметры временных паттернов')
    data = tx.copy()
    data['date'] = pd.to_datetime(data.date, utc=True).dt.as_unit('ns')
    data['day'] = data.date.dt.floor('D')
    routes, splitting = [], []
    incoming = {gid: g for gid, g in data.groupby('dst', sort=True)}
    evaluated, truncated = 0, False
    for middle, outgoing in data.groupby('src', sort=True):
        if middle not in incoming:
            continue
        for source, first in incoming[middle].groupby('src', sort=True):
            times = np.sort(first.date.astype('int64').to_numpy())
            for target, last in outgoing.groupby('dst', sort=True):
                if len({source, middle, target}) < 3:
                    continue
                if evaluated >= pair_limit:
                    truncated = True
                    break
                evaluated += 1
                ends = np.sort(last.date.astype('int64').to_numpy())
                previous = np.searchsorted(times, ends, side='right') - 1
                lag = ends - times[np.maximum(previous, 0)]
                valid = (previous >= 0) & (lag <= window * 86400 * 1e9)
                # A single incoming event cannot count as many repeated episodes.
                starts = np.unique(times[previous[valid]])
                days = pd.to_datetime(starts, utc=True).floor('D').nunique()
                if days >= min_days:
                    routes.append(dict(src=int(source), via=int(middle), dst=int(target),
                        path=f'{source}→{middle}→{target}', episodes=len(starts), active_days=days,
                        first_date=str(pd.to_datetime(starts.min(), utc=True)),
                        last_date=str(pd.to_datetime(starts.max(), utc=True)),
                        evidence=f'Цепочка наблюдается в {days} разных днях; окно {window:g} дн. Совпадение по времени, не трассировка суммы.'))
            if truncated:
                break
        if truncated:
            break
    for (src, dst, day), group in data.groupby(['src', 'dst', 'day'], sort=True):
        amounts = group.sum_kzt
        if len(group) >= min_payments and amounts.min() > 0 and amounts.max() <= amounts.min() * (1 + tolerance):
            splitting.append(dict(src=int(src), dst=int(dst), day=str(day.date()),
                n_tx=len(group), sum_kzt=float(amounts.sum()), min_kzt=float(amounts.min()),
                max_kzt=float(amounts.max()), evidence=f'{len(group)} близких сумм за день одному получателю; признак возможного дробления, требует проверки.'))
    route_table = pd.DataFrame(routes, columns=['src', 'via', 'dst', 'path', 'episodes', 'active_days', 'first_date', 'last_date', 'evidence'])
    route_table.attrs.update(truncated=truncated, evaluated_pairs=evaluated)
    split_table = pd.DataFrame(splitting, columns=['src', 'dst', 'day', 'n_tx', 'sum_kzt', 'min_kzt', 'max_kzt', 'evidence'])
    return {'repeated_routes': route_table, 'splitting': split_table}
