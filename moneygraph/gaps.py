"""Concrete next data requests; n_nodes counts the full selection."""

import pandas as pd

from .roles import numeric


def next_requests(F, R, P, cfg):
    c = cfg['gaps']
    amount, external = numeric(F, 'seed_kzt'), numeric(F, 'ext_inflow')
    positive_ext = external[external > 0]
    frontier = cfg.get('features', {}).get('frontier_depth', 4)
    boundary_request = f'Расширить обход на {frontier + 1}-е колено' if frontier is not None else 'Проверить полноту охвата сети'
    threshold_request = ('Запросить операции без порога 5 000 KZT' if cfg.get('dataset_profile', 'organizer') == 'organizer'
                         else 'Проверить, исключались ли мелкие операции из выгрузки')
    requests = [
        (boundary_request, F.is_frontier & (((amount > 0) & (amount >= amount.quantile(c['frontier_quantile']))) | (R.role == 'consolidator')),
         'Исходящие на границе не наблюдаются; нужно проследить дальнейшее движение'),
        ('Запросить входящие переводы извне выборки', (external > 0) & (external >= positive_ext.quantile(c['external_quantile'])),
         'Уточнить источники подпитки сверх наблюдаемых поступлений'),
        (threshold_request, P['rank'] <= c['top_k'],
         'Проверить дробление операций у приоритетных узлов'),
        ('Запросить снятие наличных и межбанковские переводы', (R.role == 'terminal') | (F.is_seed & (F.out_sum == 0)),
         'Проверить движение через каналы вне внутрибанковской выборки'),
    ]
    rows = []
    for name, mask, why in requests:
        selected = P.loc[mask].sort_values('rank').index
        rows.append({'request_type': name, 'n_nodes': len(selected),
                     'gids': ';'.join(str(g) for g in selected[:c['max_gids']]), 'why': why})
    return pd.DataFrame(rows, columns=['request_type', 'n_nodes', 'gids', 'why'])
