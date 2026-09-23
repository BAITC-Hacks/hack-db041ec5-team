"""Явно синтетический пример только для проверки интерфейса, не решение кейса."""

import math

import pandas as pd

from ui.constants import ROLE_COLORS
from ui.data import assemble


def make_demo():
    seeds = [101, 102, 103, 104, 105]
    roles = {
        **{g: "peripheral" for g in seeds},
        201: "transit",
        202: "transit",
        900: "consolidator",
        901: "coordinator",
        910: "distributor",
        920: "terminal",
        921: "peripheral",
        930: "peripheral",
        940: "peripheral",
    }
    pairs = [
        (101, 900, 120000),
        (102, 900, 98000),
        (103, 201, 76000),
        (201, 900, 74000),
        (104, 202, 110000),
        (202, 900, 107000),
        (105, 900, 65000),
        (900, 901, 410000),
        (901, 910, 300000),
        (910, 920, 150000),
        (910, 921, 100000),
        (910, 930, 45000),
    ]
    edges = [
        {"source": a, "target": b, "sum_kzt": amount, "n_tx": 2}
        for a, b, amount in pairs
    ]
    nodes, rows, features, tx = [], [], [], []
    for i, (gid, role) in enumerate(roles.items()):
        priority = {
            900: 0.93,
            901: 0.96,
            910: 0.81,
            201: 0.56,
            202: 0.53,
            920: 0.61,
        }.get(gid, 0.12)
        cluster = 0 if gid == 940 else (2 if gid in (910, 920, 921, 930) else 1)
        depth = (
            0
            if gid in seeds
            else (4 if gid in (921, 930) else (3 if gid == 920 else 1))
        )
        nodes.append(
            dict(
                id=gid,
                x=800 * math.cos(i * 2 * math.pi / len(roles)),
                y=600 * math.sin(i * 2 * math.pi / len(roles)),
                role=role,
                cluster=cluster,
                priority=priority,
                is_seed=gid in seeds,
                depth=depth,
            )
        )
        ins, outs = (
            [e for e in edges if e["target"] == gid],
            [e for e in edges if e["source"] == gid],
        )
        in_sum, out_sum = (
            sum(e["sum_kzt"] for e in ins),
            sum(e["sum_kzt"] for e in outs),
        )
        evidence = f"ДЕМО: входящих контрагентов {len(ins)}, исходящих {len(outs)}; роль задана для проверки экрана."
        rows.append(
            dict(
                gid=gid,
                role=role,
                role_score=0.8,
                cluster_id=cluster,
                priority_score=priority,
                evidence=evidence,
            )
        )
        features.append(
            dict(
                gid=gid,
                depth=depth,
                is_seed=gid in seeds,
                is_frontier=depth == 4,
                in_deg=len(ins),
                out_deg=len(outs),
                in_sum=in_sum,
                out_sum=out_sum,
                pass_ratio=out_sum / in_sum
                if in_sum and gid not in seeds and depth != 4
                else None,
                in_tx=2 * len(ins),
                out_tx=2 * len(outs),
                seed_kzt=None,
                seed_sources=None,
                rule_fired="ДЕМО: иллюстративная роль, не результат алгоритма A/B.",
                freq_top20=0.9 if priority > 0.8 else 0.3,
                **{f"score_{r}": 0.8 if r == role else 0.15 for r in ROLE_COLORS},
            )
        )
    for a, b, amount in pairs:
        tx.extend(
            [
                dict(
                    src=a, dst=b, sum_kzt=amount * 0.4, date=pd.Timestamp("2026-07-10")
                ),
                dict(
                    src=a, dst=b, sum_kzt=amount * 0.6, date=pd.Timestamp("2026-07-11")
                ),
            ]
        )
    R = pd.DataFrame(rows)
    P = R.sort_values("priority_score", ascending=False)[
        ["gid", "role", "priority_score"]
    ].copy()
    P.insert(0, "rank", range(1, len(P) + 1))
    P["why"] = "ДЕМО: приоритет задан для тестирования интерфейса."
    clusters = []
    for cid, group in R.groupby("cluster_id"):
        gids = set(group.gid)
        clusters.append(
            dict(
                cluster_id=cid,
                n_nodes=len(group),
                n_seed=len(gids & set(seeds)),
                sum_kzt_internal=sum(v for a, b, v in pairs if a in gids and b in gids),
                top_gids=", ".join(map(str, group.gid.head(3))),
                hypothesis="ДЕМО: пример группы для проверки вкладки.",
            )
        )
    resilience = pd.DataFrame(
        [
            dict(
                n_removed=n,
                strategy=s,
                lcc_share=max(0, 0.93 - n * k),
                flow_share=max(0, 1 - n * k * 0.9),
            )
            for s, k in [("priority", 0.11), ("degree", 0.08), ("random", 0.035)]
            for n in [0, 1, 3, 5]
        ]
    )
    frames = dict(
        nodes_roles=R,
        top_nodes=P,
        node_features=pd.DataFrame(features),
        clusters=pd.DataFrame(clusters),
        resilience=resilience,
        next_requests=pd.DataFrame(
            [
                dict(
                    request_type="Расширить обход",
                    n_nodes=2,
                    gids="921, 930",
                    why="ДЕМО: граница на 4-м колене",
                )
            ]
        ),
    )
    return assemble(
        frames,
        {"nodes": nodes, "edges": edges},
        tx=pd.DataFrame(tx),
        fingerprint="synthetic-demo-v1",
        demo=True,
    )
