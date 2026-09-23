"""Priority components, explanatory text and reproducible weight sensitivity."""

import numpy as np
import pandas as pd

from .roles import LABELS, fmt_kzt, numeric, pct

COMPONENTS = ['money', 'convergence', 'position', 'role']


def prioritize(F, R, cfg):
    c = cfg['priority']
    weights = np.array([c['weights'][k] for k in COMPONENTS], dtype=float)
    if not np.isfinite(weights).all() or (weights < 0).any() or not np.isclose(weights.sum(), 1):
        raise ValueError('Веса приоритета должны быть неотрицательны и суммироваться в 1')
    P = pd.DataFrame({'money': pct(numeric(F, 'seed_kzt')),
        'convergence': pct(numeric(F, 'seed_sources')),
        'position': pd.concat([pct(numeric(F, 'pagerank_w')), pct(numeric(F, 'betweenness'))], axis=1).max(axis=1),
        'role': R.role.map(c['role_weight']) * R.role_score}, index=F.index)
    discount = np.where(F.is_seed, c['seed_discount'], 1.0)
    contributions = P[COMPONENTS].mul(weights, axis=1)
    P['priority_score'] = (contributions.sum(axis=1) * discount).clip(0, 1)
    P['rank'] = P.priority_score.rank(ascending=False, method='first').astype('int64')
    for key in COMPONENTS:
        P['contribution_' + key] = contributions[key] * discount
    opts = c['stability']
    runs, top_k = int(opts['runs']), min(int(opts['top_k']), len(F))
    if runs < 0 or top_k < 1 or opts['concentration'] <= 0:
        raise ValueError('Некорректные настройки устойчивости приоритета')
    P['freq_top20'] = np.nan
    jaccard = None
    if runs:
        rng = np.random.default_rng(cfg['seed'])
        W = np.zeros((runs, len(weights)))
        active = weights > 0
        W[:, active] = rng.dirichlet(opts['concentration'] * weights[active], size=runs)
        sampled = discount[:, None] * (P[COMPONENTS].to_numpy() @ W.T)
        top = np.argsort(-sampled, axis=0, kind='stable')[:top_k]
        P['freq_top20'] = np.bincount(top.ravel(), minlength=len(F)) / runs
        baseline = set(np.argsort(-P.priority_score.to_numpy(), kind='stable')[:top_k])
        jaccard = float(np.mean([len(baseline & set(top[:, i])) / len(baseline | set(top[:, i])) for i in range(runs)]))
    amounts, sources = numeric(F, 'seed_kzt'), numeric(F, 'seed_sources').fillna(0)
    pr_pct, bc_pct = pct(numeric(F, 'pagerank_w')), pct(numeric(F, 'betweenness'))
    fast, payers, external = (numeric(F, k) for k in ['fast_pass_share', 'max_payers_same_day', 'ext_inflow'])
    explanations = []
    for gid, row in P.iterrows():
        phrases = {
            'money': f'{fmt_kzt(amounts.at[gid])} seed-происхождения (топ-{max(1, int(np.ceil(100 * (1 - row.money))))}%)',
            'convergence': f'сходятся деньги {sources.at[gid]:.0f} seed',
            'position': f'позиция: PageRank-перцентиль {pr_pct.at[gid]:.0%}, betweenness-перцентиль {bc_pct.at[gid]:.0%}',
            'role': R.at[gid, 'evidence'],
        }
        largest = contributions.loc[gid].sort_values(ascending=False, kind='stable').index[:2]
        parts = [f'Признаки {LABELS[R.at[gid, "role"]]}'] + [phrases[k] for k in largest]
        if fast.at[gid] >= c['flags']['fast_pass_min']:
            parts.append(f'быстрый пропуск за {cfg["features"]["fast_pass_days"]} дн.')
        if payers.at[gid] >= c['flags']['same_day_payers_min']:
            day = F.at[gid, 'max_payers_date'] if 'max_payers_date' in F else None
            parts.append(f'{payers.at[gid]:.0f} плательщиков в один день' + (f' ({day})' if pd.notna(day) else ''))
        if external.at[gid] > 0:
            parts.append('подпитка извне выборки')
        if runs:
            parts.append(f'в топ-{top_k} при {row.freq_top20:.0%} вариантов весов')
        explanations.append('; '.join(parts))
    P['why'] = explanations
    P.attrs['stability'] = {'runs': runs, 'top_k': top_k, 'mean_jaccard': jaccard}
    return P
