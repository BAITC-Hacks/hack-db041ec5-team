"""Читает данные A/B. Не записывает выгрузки и не присваивает роли."""

import hashlib
import json
import math
import numbers
from dataclasses import dataclass, field
from pathlib import Path

import networkx as nx
import pandas as pd
import yaml

from ui.constants import ROLE_COLORS

SCHEMAS = {
    "nodes_roles": {
        "gid",
        "role",
        "role_score",
        "cluster_id",
        "priority_score",
        "evidence",
    },
    "top_nodes": {"rank", "gid", "role", "priority_score", "why"},
    "clusters": {
        "cluster_id",
        "n_nodes",
        "n_seed",
        "sum_kzt_internal",
        "top_gids",
        "hypothesis",
    },
    "node_features": {"gid"},
    "resilience": {"n_removed", "strategy", "lcc_share", "flow_share"},
    "next_requests": {"request_type", "n_nodes", "gids", "why"},
}
REQUIRED = ("nodes_roles", "top_nodes", "clusters")


def data_directory(path):
    """Поддержать data/data после распаковки, сохранив режим неполных данных."""
    root = Path(path)
    if not (root / 'transactions.parquet').is_file() and (root / 'data' / 'transactions.parquet').is_file():
        return root / 'data'
    return root


def clean(value):
    """Компактные JSON-совместимые значения; NaN/Infinity превращаются в null."""
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [clean(v) for v in value]
    if hasattr(value, "item"):
        value = value.item()
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, float):
        return round(value, 6) if math.isfinite(value) else None
    if isinstance(value, (str, int, bool)):
        return value
    return str(value)


def gid_int(value):
    if isinstance(value, bool) or value is None:
        raise ValueError("gid должен быть целым числом")
    if isinstance(value, numbers.Integral):
        return int(value)
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value)
    if isinstance(value, numbers.Real) and math.isfinite(value) and value == int(value):
        return int(value)
    raise ValueError("gid должен быть целым числом")


def as_bool(value):
    if (
        value is None
        or value is pd.NA
        or (isinstance(value, float) and math.isnan(value))
    ):
        return None
    if value in (True, 1, "1", "true", "True"):
        return True
    if value in (False, 0, "0", "false", "False"):
        return False
    raise ValueError("флаг должен быть true/false или 1/0")


@dataclass
class Context:
    graph: nx.DiGraph = field(default_factory=nx.DiGraph)
    frames: dict = field(default_factory=lambda: {k: pd.DataFrame() for k in SCHEMAS})
    edges: pd.DataFrame = field(
        default_factory=lambda: pd.DataFrame(columns=["src", "dst", "sum_kzt", "n_tx"])
    )
    tx: pd.DataFrame = field(default_factory=pd.DataFrame)
    cfg: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)
    missing: list = field(default_factory=list)
    fingerprint: str = ""
    demo: bool = False

    @property
    def nodes(self):
        return self.graph.nodes


def file_signature(out_dir, data_dir, cfg_path):
    data_dir = data_directory(data_dir)
    paths = [Path(out_dir) / f"{name}.csv" for name in SCHEMAS]
    paths += [Path(out_dir) / "graph.json", Path(out_dir) / 'run_report.json', Path(cfg_path)]
    paths += [
        Path(data_dir) / f"{name}.parquet"
        for name in ("nodes", "edges", "transactions")
    ]
    result = []
    for path in paths:
        try:
            stat = path.stat()
            result.append((str(path.resolve()), stat.st_mtime_ns, stat.st_size))
        except OSError:
            result.append((str(path.resolve()), None, None))
    return tuple(result)


def _frame(path, required, ctx):
    if not path.is_file():
        return pd.DataFrame()
    try:
        df = pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(path)
        absent = required - set(df.columns)
        if absent:
            raise ValueError("нет колонок: " + ", ".join(sorted(absent)))
        for col in (
            "gid",
            "src",
            "dst",
            "cluster_id",
            "rank",
            "n_nodes",
            "n_seed",
            "n_tx",
            "n_removed",
            "depth",
        ):
            if col in df:
                df[col] = df[col].map(gid_int)
                if (
                    col in ("rank", "n_nodes", "n_seed", "n_tx", "n_removed", "depth")
                    and (df[col] < 0).any()
                ):
                    raise ValueError(f"{col}: отрицательные значения недопустимы")
        if "gid" in df and df.gid.duplicated().any():
            raise ValueError("повторяющиеся gid")
        for col in (
            "priority_score",
            "role_score",
            "sum_kzt",
            "sum_kzt_internal",
            "lcc_share",
            "flow_share",
        ):
            if col in df:
                df[col] = pd.to_numeric(df[col], errors="raise")
                if not all(math.isfinite(float(v)) and float(v) >= 0 for v in df[col]):
                    raise ValueError(f"{col}: нужны конечные неотрицательные числа")
                if (
                    col in ("priority_score", "role_score", "lcc_share")
                    and (df[col] > 1).any()
                ):
                    raise ValueError(f"{col}: нужны значения от 0 до 1")
        if "role" in df and not df.role.isin(ROLE_COLORS).all():
            raise ValueError("неизвестная роль")
        for col in ("is_seed", "is_frontier"):
            if col in df:
                df[col] = df[col].map(as_bool)
        return df
    except Exception as exc:
        # Ошибка одного файла не должна закрывать остальные вкладки.
        ctx.warnings.append(f"{path.name}: {type(exc).__name__}: {str(exc)[:180]}")
        return pd.DataFrame()


def assemble(
    frames,
    graph_data=None,
    raw_nodes=None,
    raw_edges=None,
    tx=None,
    cfg=None,
    fingerprint="",
    demo=False,
):
    ctx = Context(
        frames={name: frames.get(name, pd.DataFrame()) for name in SCHEMAS},
        cfg=cfg or {},
        fingerprint=fingerprint,
        demo=demo,
    )
    graph_data = graph_data or {"nodes": [], "edges": []}
    raw_nodes = raw_nodes if raw_nodes is not None else pd.DataFrame()
    raw_edges = raw_edges if raw_edges is not None else pd.DataFrame()
    ctx.tx = tx if tx is not None else pd.DataFrame()
    for record in graph_data["nodes"]:
        attrs = clean(record)
        gid = gid_int(attrs.pop("id"))
        attrs["gid"] = gid
        for original, canonical in (
            ("cluster", "cluster_id"),
            ("priority", "priority_score"),
        ):
            if original in attrs:
                attrs[canonical] = attrs.pop(original)
        ctx.graph.add_node(gid, **attrs)
    # Метрики -> роли -> топ: канонические CSV имеют приоритет над JSON.
    for df in (
        raw_nodes,
        ctx.frames["node_features"],
        ctx.frames["nodes_roles"],
        ctx.frames["top_nodes"],
    ):
        if not df.empty:
            for record in df.to_dict("records"):
                gid = gid_int(record["gid"])
                attrs = {k: v for k, v in clean(record).items() if v is not None}
                ctx.graph.add_node(gid, **attrs)
    records = [
        {
            "src": e["source"],
            "dst": e["target"],
            "sum_kzt": e["sum_kzt"],
            "n_tx": e["n_tx"],
        }
        for e in graph_data["edges"]
    ]
    if not records and not raw_edges.empty:
        records = raw_edges.to_dict("records")
    if records:
        edges = pd.DataFrame(records)
        edges = edges.groupby(["src", "dst"], as_index=False)[["sum_kzt", "n_tx"]].sum()
        ctx.edges = edges
        for row in edges.to_dict("records"):
            src, dst = gid_int(row["src"]), gid_int(row["dst"])
            ctx.graph.add_edge(
                src, dst, sum_kzt=float(row["sum_kzt"]), n_tx=int(row["n_tx"])
            )
    for gid, attrs in ctx.graph.nodes(data=True):
        attrs["gid"] = gid
        for key in ("is_seed", "is_frontier"):
            if key in attrs:
                try:
                    attrs[key] = as_bool(attrs[key])
                except ValueError:
                    attrs[key] = None
        if attrs.get("depth") is not None and "is_frontier" not in attrs:
            attrs["is_frontier"] = float(attrs["depth"]) >= 4
    if ctx.graph and any(
        ctx.nodes[g].get("x") is None or ctx.nodes[g].get("y") is None
        for g in ctx.graph
    ):
        # Только временная раскладка визуализации, если A ещё не экспортировал x/y.
        positions = nx.spring_layout(
            ctx.graph, seed=42, iterations=25, scale=900, weight=None
        )
        for gid, xy in positions.items():
            ctx.nodes[gid].update(x=float(xy[0]), y=float(xy[1]))
        ctx.warnings.append(
            "Нет полной раскладки A: использована временная раскладка для просмотра."
        )
    return ctx


def load_context(out_dir, data_dir, cfg_path):
    out_dir, data_dir, cfg_path = Path(out_dir), Path(data_dir), Path(cfg_path)
    data_dir = data_directory(data_dir)
    state = Context()
    report_path = out_dir / 'run_report.json'
    if report_path.is_file():
        try:
            report = json.loads(report_path.read_text(encoding='utf-8'))
            if not isinstance(report, dict) or report.get('status') != 'ok':
                raise ValueError('последний расчёт не завершён успешно')
        except (ValueError, OSError):
            state.warnings.append('Результаты не показаны: run_report.json не подтверждает успешный расчёт. Повторите run.py.')
            state.fingerprint = hashlib.sha256(repr(file_signature(out_dir, data_dir, cfg_path)).encode()).hexdigest()[:16]
            return state
    frames = {
        name: _frame(out_dir / f"{name}.csv", columns, state)
        for name, columns in SCHEMAS.items()
    }
    for name in REQUIRED:
        if not (out_dir / f"{name}.csv").is_file():
            state.missing.append(f"{name}.csv")
    graph_data = None
    graph_path = out_dir / "graph.json"
    if graph_path.is_file():
        try:
            candidate = json.loads(graph_path.read_text(encoding="utf-8-sig"))
            if not isinstance(candidate, dict) or not all(
                isinstance(candidate.get(k), list) for k in ("nodes", "edges")
            ):
                raise ValueError("нужны массивы nodes и edges")
            ids = set()
            for n in candidate["nodes"]:
                n["id"] = gid_int(n["id"])
                if n["id"] in ids:
                    raise ValueError("повторяющиеся id")
                ids.add(n["id"])
                if n.get("role") is not None and n["role"] not in ROLE_COLORS:
                    raise ValueError("неизвестная роль")
                for key in ("x", "y", "priority", "depth"):
                    if n.get(key) is not None:
                        n[key] = float(n[key])
                        if not math.isfinite(n[key]):
                            raise ValueError(f"неверное {key}")
                if n.get("priority") is not None and not 0 <= n["priority"] <= 1:
                    raise ValueError("priority вне диапазона 0–1")
                if n.get("cluster") is not None:
                    n["cluster"] = gid_int(n["cluster"])
            for e in candidate["edges"]:
                for key in ("source", "target"):
                    e[key] = gid_int(e[key])
                    if e[key] not in ids:
                        raise ValueError("ребро ссылается на неизвестный узел")
                e["sum_kzt"] = float(e["sum_kzt"])
                e["n_tx"] = gid_int(e["n_tx"])
                if not math.isfinite(e["sum_kzt"]) or e["sum_kzt"] < 0 or e["n_tx"] < 0:
                    raise ValueError(
                        "суммы и число операций должны быть неотрицательными"
                    )
            graph_data = candidate
        except Exception as exc:
            state.warnings.append(f"graph.json: {type(exc).__name__}: {str(exc)[:180]}")
    else:
        state.missing.append("graph.json")
    raw_nodes = raw_edges = pd.DataFrame()
    if graph_data is None:
        raw_nodes = _frame(
            data_dir / "nodes.parquet", {"gid", "depth", "is_seed"}, state
        )
        raw_edges = _frame(
            data_dir / "edges.parquet", {"src", "dst", "sum_kzt", "n_tx"}, state
        )
    tx = _frame(
        data_dir / "transactions.parquet", {"src", "dst", "sum_kzt", "date"}, state
    )
    if not tx.empty:
        tx["date"] = (
            pd.to_datetime(tx.date, errors="coerce", utc=True, format="mixed")
            .dt.tz_convert(None)
            .dt.normalize()
        )
        invalid = int(tx.date.isna().sum())
        if invalid:
            state.warnings.append(
                f"transactions.parquet: пропущено операций с неверной датой: {invalid}."
            )
            tx = tx.dropna(subset=["date"])
    cfg = {}
    if cfg_path.is_file():
        try:
            cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
            if not isinstance(cfg, dict):
                raise ValueError("ожидается YAML-объект")
        except Exception:
            state.warnings.append("config.yaml не прочитан; симуляция A недоступна.")
            cfg = {}
    signature = file_signature(out_dir, data_dir, cfg_path)
    ctx = assemble(
        frames,
        graph_data,
        raw_nodes,
        raw_edges,
        tx,
        cfg,
        hashlib.sha256(repr(signature).encode()).hexdigest()[:16],
    )
    ctx.warnings = state.warnings + ctx.warnings
    ctx.missing = state.missing
    return ctx

