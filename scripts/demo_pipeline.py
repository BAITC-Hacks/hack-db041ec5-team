"""Generate labelled synthetic input and run the real A/B pipeline."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd
from ui.demo import make_demo
from run import run_pipeline


def main():
    ctx = make_demo()
    data = ROOT / "data" / "demo"
    out = ROOT / "output" / "demo"
    data.mkdir(parents=True, exist_ok=True)
    nodes = pd.DataFrame([{"gid": gid, "depth": int(n["depth"]), "is_seed": n["is_seed"]} for gid, n in ctx.nodes(data=True)])
    edges = ctx.edges.assign(depth=1)
    nodes.to_parquet(data / "nodes.parquet", index=False)
    edges.to_parquet(data / "edges.parquet", index=False)
    ctx.tx.to_parquet(data / "transactions.parquet", index=False)
    run_pipeline(data, out, ROOT / "config.yaml")
    (out / "SYNTHETIC_DEMO.txt").write_text("Синтетические входные данные. Роли и приоритеты рассчитаны ядром A/B.", encoding="utf-8")
    print(f"Demo ready: data={data}, output={out}")


if __name__ == "__main__":
    main()
