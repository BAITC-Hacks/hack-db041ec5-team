"""Структурные и временные признаки с индексом gid."""

import numpy as np
import pandas as pd

from .flow import attribute_sources, centrality_features


def structural_features(nodes, edges, cfg):
    """Посчитать степени, обороты и эффективное число контрагентов."""
    pairs = edges.groupby(['src', 'dst'], sort=False)[['sum_kzt', 'n_tx']].sum().reset_index()
    F = nodes.set_index('gid').copy()
    for side, key, other in [('in', 'dst', 'src'), ('out', 'src', 'dst')]:
        stats = pairs.groupby(key).agg(**{f'{side}_deg': (other, 'nunique'),
            f'{side}_sum': ('sum_kzt', 'sum'), f'{side}_tx': ('n_tx', 'sum')})
        F = F.join(stats)
        columns = [f'{side}_{suffix}' for suffix in ('deg', 'sum', 'tx')]
        F[columns] = F[columns].fillna(0)
        totals = pairs.groupby(key).sum_kzt.transform('sum')
        shares = pairs.sum_kzt / totals.where(totals > 0)
        hhi = shares.pow(2).groupby(pairs[key]).sum()
        effective = 1 / hhi.where(hhi > 0)
        name = 'eff_payers' if side == 'in' else 'eff_receivers'
        F[name] = effective.reindex(F.index).fillna(0)
    F['is_seed'] = F.is_seed.astype(bool)
    frontier = cfg.get('features', {}).get('frontier_depth', 4)
    F['is_frontier'] = False if frontier is None else F.depth >= frontier
    F['pass_ratio'] = (F.out_sum / F.in_sum.where(F.in_sum > 0)).where(~F.is_seed & ~F.is_frontier)
    F['ext_inflow'] = (F.out_sum - F.in_sum).clip(lower=0).where(~F.is_seed, 0)
    return F


def temporal_features(F, tx, cfg):
    """Найти поступления перед отправкой, активные дни и синхронных плательщиков."""
    result = pd.DataFrame(0.0, index=F.index,
                         columns=['fast_pass_share', 'max_payers_same_day', 'burst_ratio'])
    if tx.empty:
        return result
    data = tx.copy()
    data['date'] = pd.to_datetime(data.date, errors='raise', utc=True).dt.as_unit('ns')
    if data.date.isna().any():
        raise ValueError('Пустые даты транзакций')
    days = float(cfg.get('features', {}).get('fast_pass_days', 2))
    if days < 0:
        raise ValueError('fast_pass_days не может быть отрицательным')
    window = days * 86400 * 1e9
    incoming = {gid: np.sort(group.date.astype('int64').to_numpy())
                for gid, group in data.groupby('dst')}
    for gid, group in data.groupby('src'):
        if gid not in incoming or gid not in F.index:
            continue
        dates = group.date.astype('int64').to_numpy()
        before = np.searchsorted(incoming[gid], dates, side='right') - 1
        elapsed = dates - incoming[gid][np.maximum(before, 0)]
        fast = (before >= 0) & (elapsed <= window)
        if F.at[gid, 'out_sum'] > 0:
            result.at[gid, 'fast_pass_share'] = group.loc[fast, 'sum_kzt'].sum() / F.at[gid, 'out_sum']
    data['day'] = data.date.dt.floor('D')
    payers = data.groupby(['dst', 'day']).src.nunique().groupby(level=0).max()
    events = pd.concat([data[['src', 'day']].rename(columns={'src': 'gid'}),
                        data[['dst', 'day']].rename(columns={'dst': 'gid'})])
    daily = events.groupby(['gid', 'day']).size()
    burst = daily.groupby(level=0).max() / daily.groupby(level=0).mean()
    result['max_payers_same_day'] = payers.reindex(F.index).fillna(0)
    result['burst_ratio'] = burst.reindex(F.index).fillna(0)
    return result


def add_cluster_features(F, G, clusters):
    """Добавить число кластеров среди узла и его входящих/исходящих соседей."""
    result = F.copy()
    result['n_clusters_touched'] = [len({clusters.loc[v] for v in
        {gid}.union(G.predecessors(gid), G.successors(gid))}) for gid in F.index]
    return result


def compute_features(G, nodes, edges, tx, cfg):
    """Вернуть F v2; мосты добавляются после cluster через add_cluster_features."""
    F = structural_features(nodes, edges, cfg)
    attribution = attribute_sources(F, edges, cfg)
    F = F.join(attribution).join(centrality_features(G, F, cfg)).join(temporal_features(F, tx, cfg))
    for column in ['n_clusters_touched', 'anomaly_z', 'in_cycle']:
        F[column] = np.nan
    F.attrs['attribution'] = attribution.attrs.copy()
    return F
