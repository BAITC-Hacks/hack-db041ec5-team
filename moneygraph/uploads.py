"""Validate uploaded files before saving an isolated analysis dataset."""

from io import BytesIO
from pathlib import Path
import uuid

import pandas as pd
import yaml

from .io import SCHEMA, ensure_valid_data


def save_uploads(files, root, config_path, frontier_depth=4):
    tables = {}
    for filename, content in files:
        path = Path(filename)
        name = path.stem.lower()
        if name not in SCHEMA or path.suffix.lower() not in ('.csv', '.parquet'):
            raise ValueError('Нужны nodes, edges, transactions в формате CSV или Parquet')
        if name in tables:
            raise ValueError(f'Повторный файл {name}')
        if path.suffix.lower() == '.parquet':
            table = pd.read_parquet(BytesIO(content))
        else:
            # Read IDs as integers, never via floating point (18-digit IDs).
            ids = {'gid': 'int64'} if name == 'nodes' else {'src': 'int64', 'dst': 'int64'}
            table = pd.read_csv(BytesIO(content), dtype=ids)
        if name == 'nodes' and 'is_seed' in table:
            values = table.is_seed.astype(str).str.lower().map({'true': True, 'false': False, '1': True, '0': False})
            if values.isna().any():
                raise ValueError('nodes.is_seed: нужны true/false или 0/1')
            table['is_seed'] = values.astype(bool)
        tables[name] = table
    missing = set(SCHEMA) - set(tables)
    if missing:
        raise ValueError('Не хватает файлов: ' + ', '.join(sorted(missing)))
    for name, columns in [('nodes', ['gid']), ('edges', ['src', 'dst']), ('transactions', ['src', 'dst'])]:
        for column in columns:
            if column not in tables[name]:
                raise ValueError(f'{name}: отсутствует {column}')
            series = tables[name][column]
            if len(series) and (not pd.api.types.is_integer_dtype(series.dtype) or
                pd.api.types.is_bool_dtype(series.dtype) or series.isna().any() or
                not series.map(lambda x: -(2 ** 63) <= int(x) < 2 ** 63).all()):
                raise ValueError(f'{name}.{column}: нужен int64')
    ensure_valid_data(tables['nodes'], tables['edges'], tables['transactions'])
    check_consistency(tables['edges'], tables['transactions'])
    if tables['nodes'].empty:
        raise ValueError('Файл nodes пуст')
    if frontier_depth is not None and int(frontier_depth) < 1:
        raise ValueError('Глубина границы должна быть положительной')
    config = yaml.safe_load(Path(config_path).read_text(encoding='utf-8'))
    config['dataset_profile'] = 'generic'
    config['features']['frontier_depth'] = frontier_depth
    folder = Path(root) / uuid.uuid4().hex
    data = folder / 'data'
    data.mkdir(parents=True)
    for name, table in tables.items():
        table.to_parquet(data / f'{name}.parquet', index=False)
    cfg = folder / 'config.yaml'
    cfg.write_text(yaml.safe_dump(config, allow_unicode=True), encoding='utf-8')
    return folder / 'results', data, cfg


def check_consistency(edges, tx):
    expected = tx.groupby(['src', 'dst']).agg(amount=('sum_kzt', 'sum'), count=('sum_kzt', 'size'))
    actual = edges.groupby(['src', 'dst']).agg(amount=('sum_kzt', 'sum'), count=('n_tx', 'sum'))
    joined = expected.join(actual, how='outer', lsuffix='_tx', rsuffix='_edge')
    if (joined.isna().any(axis=None) or
        (joined.amount_tx - joined.amount_edge).abs().gt(.011).any() or
        joined.count_tx.ne(joined.count_edge).any()):
        raise ValueError('edges не совпадает с transactions: проверьте пары, суммы и n_tx')
