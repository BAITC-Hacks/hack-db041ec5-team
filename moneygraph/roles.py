"""Explainable two-pass role assignment. Scores are heuristics, not probabilities."""

import numpy as np
import pandas as pd

BASE_ROLES = ['consolidator', 'distributor', 'transit', 'terminal']
ROLES = ['coordinator', *BASE_ROLES, 'peripheral']
LABELS = dict(zip(ROLES, ['координации', 'консолидации', 'распределения', 'транзита', 'удержания средств', 'периферийной роли']))


def numeric(F, name):
    return pd.to_numeric(F.get(name, pd.Series(np.nan, index=F.index)), errors='coerce').replace([np.inf, -np.inf], np.nan)


def pct(series):
    return series.fillna(0).rank(pct=True, method='average')


def ramp(x, lo, hi):
    if hi < lo:
        raise ValueError('Верхняя граница ramp меньше нижней')
    if hi == lo:
        return (x > lo).astype(float)
    return ((x - lo) / (hi - lo)).clip(0, 1)


def fmt_kzt(value):
    if pd.isna(value):
        return 'нет данных'
    if value >= 1e6:
        return f'{value / 1e6:.1f} млн KZT'.replace('.', ',')
    if value >= 1e3:
        return f'{value / 1e3:.0f} тыс. KZT'
    return f'{value:.0f} KZT'


def assign_roles(F, clusters, G, cfg):
    """Return R indexed by gid without mutating features or graph."""
    c = cfg['roles']
    seed, frontier = F.is_seed.fillna(False).astype(bool), F.is_frontier.fillna(False).astype(bool)
    indeg, outdeg = F.in_deg, F.out_deg
    sources = numeric(F, 'seed_sources').fillna(0)
    fast = numeric(F, 'fast_pass_share').fillna(0).clip(0, 1)
    between = numeric(F, 'betweenness')
    touched = numeric(F, 'n_clusters_touched')
    passing = numeric(F, 'pass_ratio')
    candidates, scores = {}, {}

    k = c['consolidator']
    even_in = (F.eff_payers / indeg.where(indeg > 0)).fillna(0)
    scores['consolidator'] = (0.5 * ramp(indeg, *k['ramp_in_deg']) +
        0.3 * ramp(sources, *k['ramp_seed_sources']) + 0.2 * ramp(even_in, *k['ramp_evenness']))
    scores['consolidator'] *= np.where(frontier, k['frontier_penalty'], 1)
    candidates['consolidator'] = indeg >= k['min_in_deg']

    k = c['distributor']
    even_out = (F.eff_receivers / outdeg.where(outdeg > 0)).fillna(0)
    candidates['distributor'] = ~frontier & (outdeg >= k['min_out_deg'])
    scores['distributor'] = 0.7 * ramp(outdeg, *k['ramp_out_deg']) + 0.3 * ramp(even_out, *k['ramp_evenness'])

    k = c['transit']
    candidates['transit'] = (~frontier & (indeg <= k['max_in_deg']) &
        (outdeg <= k['max_out_deg']) & (F.out_sum > 0) & (seed | passing.between(k['pass_min'], k['pass_max'])))
    width = np.where(passing <= 1, 1 - k['pass_min'], k['pass_max'] - 1)
    if min(1 - k['pass_min'], k['pass_max'] - 1) <= 0:
        raise ValueError('Пороги transit должны окружать 1')
    closeness = (1 - (passing - 1).abs() / width).clip(0, 1).fillna(0).where(~seed, 0.5)
    scores['transit'] = (0.6 * closeness + 0.4 * fast) * np.where(seed, k['seed_penalty'], 1)

    k = c['terminal']
    positive = F.loc[F.in_sum > 0, 'in_sum']
    median = positive.quantile(k['min_in_quantile']) if len(positive) else np.inf
    high = positive.quantile(k['high_in_quantile']) if len(positive) else np.inf
    terminal_pass = passing.where(F.out_sum != 0, 0)
    candidates['terminal'] = (~frontier & (F.in_sum > 0) & (F.in_sum >= median) &
        ((F.out_sum == 0) | (~seed & (passing <= k['max_pass']))))
    volume = ramp(np.log1p(F.in_sum), np.log1p(median), np.log1p(high)) if len(positive) else pd.Series(0.0, index=F.index)
    scores['terminal'] = 0.6 * (1 - terminal_pass / k['max_pass']).clip(0, 1).fillna(0) + 0.4 * volume

    masked = pd.DataFrame({r: scores[r].where(candidates[r], -1.0) for r in BASE_ROLES})
    base = masked.idxmax(axis=1).where(masked.max(axis=1) >= 0, 'peripheral')
    # Edge aggregation uses the first-pass roles only; no recursive feedback.
    links = pd.DataFrame(list(G.edges()), columns=['src', 'dst'])
    incoming = links.loc[links.src.map(base).isin(['consolidator', 'transit'])].groupby('dst').src.nunique().reindex(F.index, fill_value=0)
    outgoing = links.loc[links.dst.map(base).isin(['consolidator', 'distributor'])].groupby('src').dst.nunique().reindex(F.index, fill_value=0)
    neighbors = pd.concat([incoming, outgoing], axis=1).max(axis=1)
    k = c['coordinator']
    source_cut = max(sources.quantile(k['seed_sources_q']), k['seed_sources_min'])
    between_cut = between.quantile(k['betweenness_q'])
    a = sources >= source_cut
    b = neighbors >= k['min_role_neighbors']
    # An all-zero centrality distribution supplies no bridge evidence.
    bridge = (between > 0) & (between >= between_cut)
    d = (touched >= k['min_clusters_touched']) | bridge
    candidates['coordinator'] = ~frontier & ((a.astype(int) + b.astype(int) + d.astype(int)) >= k['min_signals'])
    bridge_score = pd.concat([pct(between).where(between > 0, 0), (touched.fillna(0) / 4).clip(0, 1)], axis=1).max(axis=1)
    scores['coordinator'] = (pct(sources).where(sources > 0, 0) + (neighbors / 4).clip(0, 1) + bridge_score) / 3
    role = base.where(~candidates['coordinator'], 'coordinator')
    active_scores = pd.DataFrame({r: scores[r].where(candidates[r], 0).clip(0, 1) for r in ROLES[:-1]})
    scores['peripheral'] = (1 - active_scores.max(axis=1)).where(~frontier, (1 - active_scores.max(axis=1)).clip(upper=c['peripheral']['frontier_cap']))
    R = pd.DataFrame({'role': role}, index=F.index)
    for r in ROLES:
        R['score_' + r] = scores[r].fillna(0).clip(0, 1)
    R['role_score'] = sum(R['score_' + r].where(role == r, 0) for r in ROLES)
    alternatives = pd.DataFrame({r: scores[r].where(candidates[r] & (role != r), -1) for r in ['coordinator', *BASE_ROLES]})
    R['secondary_role'] = alternatives.idxmax(axis=1).where(alternatives.max(axis=1) >= 0, '')
    R['base_role'] = base
    R['n_role_nb'] = neighbors

    # Text generation is row-wise; all scoring and candidate rules above are vectorized.
    evidence, fired = [], []
    seed_amount, known_touched = numeric(F, 'seed_kzt'), touched.fillna(0)
    for gid, f in F.iterrows():
        r = role.at[gid]
        pass_text = 'не наблюдается' if pd.isna(passing.at[gid]) else f'{passing.at[gid]:.0%}'
        prefix = f'Признаки {LABELS[r]}: '
        if r == 'consolidator':
            detail = f'{f.in_deg:.0f} плательщиков, {fmt_kzt(f.in_sum)}, {sources.at[gid]:.0f} seed; '
            detail += 'дальнейшее движение не наблюдается (граница обхода)' if frontier.at[gid] else f'дальше отдаёт {pass_text}'
        elif r == 'distributor':
            detail = f'{fmt_kzt(f.out_sum)} → {f.out_deg:.0f} получателей'
            if pd.notna(f.get('median_out')):
                detail += f'; медиана перевода {fmt_kzt(f.median_out)}'
        elif r == 'transit':
            detail = (f'seed пересылает {fmt_kzt(f.out_sum)}; входящие вне выборки' if seed.at[gid] else
                      f'{fmt_kzt(f.in_sum)} от {f.in_deg:.0f} плательщиков, переслал {pass_text}; {fast.at[gid]:.0%} за {cfg["features"]["fast_pass_days"]} дн.')
        elif r == 'terminal':
            detail = f'получил {fmt_kzt(f.in_sum)}, дальше {0 if f.out_sum == 0 else terminal_pass.at[gid]:.0%}; колено {f.depth:.0f}, не граница; возможен вывод вне банка'
        elif r == 'coordinator':
            detail = f'деньги {sources.at[gid]:.0f} seed ({fmt_kzt(seed_amount.at[gid])}); {neighbors.at[gid]:.0f} ролевых соседей; {known_touched.at[gid]:.0f} кластеров; кандидат в организаторы'
        elif frontier.at[gid]:
            detail = f'не определяются: колено {f.depth:.0f}, исходящие не выгружены; {f.in_deg:.0f} вход. на {fmt_kzt(f.in_sum)}'
        elif seed.at[gid] and f.in_deg + f.out_deg == 0:
            detail = 'не определяются: seed без внутрибанковских переводов ≥ 5 000 KZT; нужны данные об иных каналах'
        else:
            detail = f'не выражены: {f.in_deg:.0f} вход. / {f.out_deg:.0f} исход.; оборот {fmt_kzt(f.in_sum + f.out_sum)}'
        text = prefix + detail
        secondary = R.at[gid, 'secondary_role']
        suffix = f'; также признаки {LABELS[secondary]}' if secondary else ''
        limit = int(c['evidence_max_len'])
        if len(text + suffix) <= limit:
            text += suffix
        evidence.append(text if len(text) <= limit else text[:limit - 1] + '…')
        diagnostics = [f'{name}: cand={bool(candidates[name].at[gid])}, score={scores[name].at[gid]:.4f}' for name in ['coordinator', *BASE_ROLES]]
        fired.append(f'{r}={R.at[gid, "role_score"]:.4f}; in_deg={f.in_deg:g}, out_deg={f.out_deg:g}, pass={pass_text}, in_sum={f.in_sum:g}, seed={seed.at[gid]}, frontier={frontier.at[gid]}; '
                     f'even_in={even_in.at[gid]:.3f}, even_out={even_out.at[gid]:.3f}, fast={fast.at[gid]:.3f}; '
                     f'coordinator signals={int(a.at[gid])}/{int(b.at[gid])}/{int(d.at[gid])}, sources={sources.at[gid]:g}>={source_cut:g}, role_nb={neighbors.at[gid]:g}>={k["min_role_neighbors"]}, clusters={touched.at[gid]:g}>={k["min_clusters_touched"]}, betweenness={between.at[gid]:g}>={between_cut:g}; '
                     f'terminal in>={median:g}; ' + ' | '.join(diagnostics) + '; thresholds=' + str({name: c[name] for name in BASE_ROLES}))
    R['evidence'], R['rule_fired'] = evidence, fired
    return R
