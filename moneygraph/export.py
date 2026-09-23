"""UTF-8 exports with strict competition schemas."""

import json
from pathlib import Path

from .graph import build_graph_json, compute_layout

SCHEMAS = {
    'nodes_roles.csv': ['gid', 'role', 'role_score', 'cluster_id', 'priority_score', 'evidence'],
    'clusters.csv': ['cluster_id', 'n_nodes', 'n_seed', 'sum_kzt_internal', 'top_gids', 'hypothesis'],
    'top_nodes.csv': ['rank', 'gid', 'role', 'priority_score', 'why'],
}


def export(R, P, C, F, G, out_dir, cfg, extras=None):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    roles = R[['role', 'role_score', 'evidence']].join(F[['cluster_id']]).join(P[['priority_score']]).rename_axis('gid').reset_index()
    roles[['gid', 'cluster_id']] = roles[['gid', 'cluster_id']].astype('int64')
    clusters = C.copy()
    clusters['cluster_id'] = clusters.cluster_id.astype('int64')
    top = P[['rank', 'priority_score', 'why']].join(R[['role']]).sort_values('rank').head(cfg['priority']['top_n']).rename_axis('gid').reset_index()
    top[['rank', 'gid']] = top[['rank', 'gid']].astype('int64')
    for filename, table in [('nodes_roles.csv', roles), ('clusters.csv', clusters), ('top_nodes.csv', top)]:
        table[SCHEMAS[filename]].to_csv(out / filename, index=False, encoding='utf-8', float_format='%.4f')
    priority_features = P.rename(columns={key: 'priority_' + key for key in ['money', 'convergence', 'position', 'role']})
    F.join(R).join(priority_features).rename_axis('gid').reset_index().to_csv(out / 'node_features.csv', index=False, encoding='utf-8')
    payload = build_graph_json(G, compute_layout(G, cfg), F, R, P, F.cluster_id)
    (out / 'graph.json').write_text(json.dumps(payload, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    for name, table in (extras or {}).items():
        table.to_csv(out / (name + '.csv'), index=False, encoding='utf-8')
