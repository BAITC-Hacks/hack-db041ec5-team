"""Package calculated contest results for demonstration; never read .env."""
import argparse
import gzip
import json
from pathlib import Path
import shutil
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def prepare(data, out, destination):
    report = json.loads((out / 'run_report.json').read_text(encoding='utf-8'))
    if report.get('status') != 'ok':
        raise ValueError('Only a successful calculation may be demonstrated.')
    source = data / 'data' if (data / 'data' / 'nodes.parquet').exists() else data
    packet = {
        'csv': {p.name: p.read_text(encoding='utf-8') for p in out.glob('*.csv')},
        'graph': json.loads((out / 'graph.json').read_text(encoding='utf-8')),
        'transactions': pd.read_parquet(source / 'transactions.parquet').to_csv(index=False),
        'config': report['config'],
    }
    (destination / 'source').mkdir(parents=True, exist_ok=True)
    for name in ['nodes', 'edges', 'transactions']:
        shutil.copyfile(source / (name + '.parquet'), destination / 'source' / (name + '.parquet'))
    with gzip.open(destination / 'analysis.json.gz', 'wt', encoding='utf-8') as target:
        json.dump({'packet': packet, 'report': report,
                   'quality': (out / 'data_quality.md').read_text(encoding='utf-8')}, target, ensure_ascii=False)
    print('Prepared calculated showcase:', report['n_nodes'], 'nodes')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', type=Path, default=ROOT / 'data')
    parser.add_argument('--out', type=Path, default=ROOT / 'output' / 'current')
    args = parser.parse_args()
    prepare(args.data, args.out, ROOT / 'showcase')
