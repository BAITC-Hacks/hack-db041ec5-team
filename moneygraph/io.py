"""Чтение parquet и диагностический отчёт без привязки расчётов к размеру выборки."""

from pathlib import Path
import warnings

import networkx as nx
import numpy as np
import pandas as pd

from .graph import build_graph

SCHEMA = {'nodes': ['gid', 'depth', 'is_seed'],
          'edges': ['src', 'dst', 'sum_kzt', 'n_tx', 'depth'],
          'transactions': ['src', 'dst', 'date', 'sum_kzt']}


def resolve_data_dir(data_dir):
    """Найти полный набор parquet непосредственно в папке или внутри data/."""
    root = Path(data_dir)
    for candidate in (root, root / 'data'):
        if all((candidate / f'{name}.parquet').is_file() for name in SCHEMA):
            return candidate
    raise FileNotFoundError(f'Не найден полный набор nodes/edges/transactions.parquet в {root} или {root / "data"}')


def load(data_dir):
    """Прочитать канонические файлы; неоднозначные названия колонок не угадываются."""
    data_dir = resolve_data_dir(data_dir)
    tables = {}
    for name, required in SCHEMA.items():
        table = pd.read_parquet(Path(data_dir) / f'{name}.parquet')
        missing = set(required) - set(table.columns)
        if missing:
            raise ValueError(f'{name}: отсутствуют колонки {sorted(missing)}')
        tables[name] = table.copy()
    seed = tables['nodes'].is_seed
    if seed.isna().any() or not seed.isin([True, False, 0, 1]).all():
        raise ValueError('nodes.is_seed должен содержать bool или 0/1')
    tables['nodes']['is_seed'] = seed.astype(bool)
    tables['transactions']['date'] = pd.to_datetime(tables['transactions'].date, errors='raise', utc=True)
    return tables['nodes'], tables['edges'], tables['transactions']


def _integrity(nodes, edges, tx):
    """Вернуть проверки, без которых финансовые вычисления неоднозначны."""
    rows = []
    for name, table in [('nodes', nodes), ('edges', edges), ('transactions', tx)]:
        missing = sorted(set(SCHEMA[name]) - set(table.columns))
        rows.append({'check': f'{name}: отсутствующие колонки', 'expected': [], 'actual': missing, 'ok': not missing})
        duplicate = table.columns[table.columns.duplicated()].tolist()
        rows.append({'check': f'{name}: повторные колонки', 'expected': [], 'actual': duplicate, 'ok': not duplicate})
    if not all(row['ok'] for row in rows):
        return rows
    facts = {'дубликаты gid': int(nodes.gid.duplicated().sum()),
             'пустые gid': int(nodes.gid.isna().sum()),
             'неизвестные концы рёбер': len((set(edges.src) | set(edges.dst)) - set(nodes.gid)),
             'неизвестные концы транзакций': len((set(tx.src) | set(tx.dst)) - set(nodes.gid)),
             'невалидные даты': int(pd.to_datetime(tx.date, errors='coerce', utc=True).isna().sum())}
    facts['nodes.is_seed: невалидные значения'] = int((nodes.is_seed.isna() | ~nodes.is_seed.isin([True, False, 0, 1])).sum())
    for name, series in [('edges.sum_kzt', edges.sum_kzt), ('edges.n_tx', edges.n_tx),
                          ('transactions.sum_kzt', tx.sum_kzt), ('nodes.depth', nodes.depth),
                          ('edges.depth', edges.depth)]:
        if len(series) and (not pd.api.types.is_numeric_dtype(series.dtype)
                            or pd.api.types.is_bool_dtype(series.dtype)
                            or pd.api.types.is_complex_dtype(series.dtype)):
            facts[f'{name}: нечисловой тип'] = len(series)
            continue
        numeric = pd.to_numeric(series, errors='coerce')
        invalid = numeric.isna() | ~np.isfinite(numeric) | (numeric < 0)
        if name.endswith(('.depth', '.n_tx')):
            invalid |= numeric.mod(1).ne(0)
        facts[f'{name}: невалидные значения'] = int(invalid.sum())
    rows.extend({'check': key, 'expected': 0, 'actual': value, 'ok': value == 0} for key, value in facts.items())
    return rows


def ensure_valid_data(nodes, edges, tx):
    """Остановить расчёт при нарушении схемы/целостности, но не фактов ТЗ."""
    failed = [row['check'] for row in _integrity(nodes, edges, tx) if not row['ok']]
    if failed:
        raise ValueError('Некорректные исходные данные: ' + '; '.join(failed))


def _dataset_checks(nodes, edges, tx):
    """Сверить факты из ТЗ; ожидания используются только для отчёта."""
    facts = []
    def add(check, expected, actual, ok=None):
        facts.append({'check': check, 'expected': expected, 'actual': actual,
                      'ok': bool(actual == expected if ok is None else ok)})
    for name, table, expected in [('узлы', nodes, 2248), ('рёбра', edges, 3119), ('транзакции', tx, 4840)]:
        add(name, expected, len(table))
    seed = nodes.loc[nodes.is_seed.astype(bool), 'gid']
    add('seed', 81, len(seed))
    add('по коленам', {0: 81, 1: 472, 2: 462, 3: 789, 4: 444}, nodes.depth.value_counts().to_dict())
    add('минимальная транзакция', '>= 5000', tx.sum_kzt.min(), tx.empty or tx.sum_kzt.min() >= 5000)
    dates = pd.to_datetime(tx.date, utc=True)
    add('даты', ('2026-07-01', '2026-07-31'), (str(dates.min().date()), str(dates.max().date())))
    add('frontier без исходящих', 444, int(((nodes.depth == 4) & ~nodes.gid.isin(edges.src)).sum()))
    add('seed без исходящих', 31, int((~seed.isin(edges.src)).sum()))
    add('seed вне рёбер', 19, int((~seed.isin(set(edges.src) | set(edges.dst))).sum()))
    add('seed только получатели', 12, int((seed.isin(edges.dst) & ~seed.isin(edges.src)).sum()))
    G = build_graph(nodes, edges)
    sizes = sorted((len(c) for c in nx.weakly_connected_components(G)
                    if any(G.degree(v) > 0 for v in c)), reverse=True)
    add('компоненты без изолятов', 16, len(sizes))
    add('крупнейшая компонента', 1877, max(sizes, default=0))
    incoming = edges.groupby('dst').sum_kzt.sum().reindex(nodes.gid, fill_value=0)
    outgoing = edges.groupby('src').sum_kzt.sum().reindex(nodes.gid, fill_value=0)
    add('отдают больше входящего', 354, int((outgoing > incoming).sum()))
    add('оборот KZT', 365890012, float(edges.sum_kzt.sum()))
    agg = tx.groupby(['src', 'dst']).agg(sum_tx=('sum_kzt', 'sum'), n_tx_tx=('sum_kzt', 'size'))
    totals = edges.groupby(['src', 'dst'])[['sum_kzt', 'n_tx']].sum()
    merged = totals.join(agg, how='outer')
    bad = merged.isna().any(axis=1) | ((merged.sum_kzt - merged.sum_tx).abs() > 1) | (merged.n_tx != merged.n_tx_tx)
    add('несогласованные пары edges/tx', 0, int(bad.sum()))
    return facts


def validate(nodes, edges, tx, profile='organizer'):
    """Вернуть список check/expected/actual/ok; расхождения сообщать warnings.warn."""
    checks = _integrity(nodes, edges, tx)
    if profile not in ('organizer', 'generic'):
        raise ValueError('Профиль данных должен быть organizer или generic')
    if all(row['ok'] for row in checks) and profile == 'organizer':
        checks.extend(_dataset_checks(nodes, edges, tx))
    for row in checks:
        if not row['ok']:
            warnings.warn(f"{row['check']}: ожидалось {row['expected']}, получено {row['actual']}",
                          UserWarning, stacklevel=2)
    return checks


def write_quality_report(checks, out_dir):
    """Записать Markdown-таблицу диагностики в output/data_quality.md."""
    path = Path(out_dir)
    path.mkdir(parents=True, exist_ok=True)
    lines = ['# Качество данных', '', '| Проверка | Ожидали | Получили | Статус |', '|---|---|---|---|']
    for row in checks:
        cells = [str(row[key]).replace('|', '\\|').replace('\n', ' ') for key in ('check', 'expected', 'actual')]
        lines.append('| ' + ' | '.join(cells) + (' | ✓ |' if row['ok'] else ' | ⚠ |'))
    (path / 'data_quality.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
