"""Cautious cluster hypotheses based on observable role composition."""

from .clusters import cluster_summary


def summarize_clusters(F, R, P, clusters, edges, cfg):
    C = cluster_summary(clusters, F, edges).drop(columns='stability')
    c = cfg['hypotheses']
    top_gids, hypotheses = [], []
    for row in C.itertuples():
        members = clusters.index[clusters == row.cluster_id]
        ranked = P.loc[members].sort_values('rank').index
        top_gids.append(';'.join(str(g) for g in ranked[:c['top_n']]))
        roles = R.loc[ranked, 'role']
        found = []
        if row.cluster_id == 0:
            found.append('Изолированные узлы: наблюдаемых переводов нет; для seed нужны данные о наличных и внешних переводах')
        else:
            consolidators = roles.index[roles == 'consolidator']
            coordinators = roles.index[roles == 'coordinator']
            distributors = roles.index[(roles == 'distributor') & (F.loc[ranked, 'out_deg'] >= c['distributor_degree'])]
            if row.n_seed >= c['min_seeds'] and len(consolidators):
                found.append(f'Признаки ячейки сбора выручки: {row.n_seed} seed → точка консолидации {consolidators[0]}')
            if len(coordinators):
                found.append(f'Возможный управляющий узел {coordinators[0]}: сходятся потоки нескольких групп')
            if len(distributors):
                gid = distributors[0]
                found.append(f'Признаки веерной раздачи ({gid} → {F.at[gid, "out_deg"]:.0f} получателей): возможные выплаты или вывод через множество счетов')
            if (roles == 'transit').mean() >= c['transit_share']:
                found.append('Признаки слоя расслоения (layering): цепочки транзитных счетов')
            if F.loc[members, 'is_frontier'].mean() >= c['frontier_share']:
                found.append('Периферия на границе обхода: структура не раскрыта, нужно расширить выгрузку')
        hypotheses.append('; '.join(found[:2]) or 'Группа получателей, выраженной структуры не выявлено')
    return C.assign(top_gids=top_gids, hypothesis=hypotheses)
