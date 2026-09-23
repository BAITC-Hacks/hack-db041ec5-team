"""Офлайн: извлечение намерения -> те же инструменты -> честный шаблонный ответ."""

import re

from ui.constants import ROLE_LABELS, fmt_kzt, fmt_number

from assistant.tools import execute

ROLE_WORDS = {
    "consolidator": ("консолид",),
    "coordinator": ("координ", "организатор"),
    "distributor": ("распредел",),
    "transit": ("транзит",),
    "terminal": ("конечн",),
    "peripheral": ("перифер",),
}


def _table(rows, columns):
    if not rows:
        return "Подходящих результатов в загруженных данных нет."

    def cell(x):
        if x is None:
            return "—"
        if isinstance(x, list):
            return ", ".join(map(str, x))
        return (
            str(x)
            .replace("|", "\\|")
            .replace("\n", " ")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    return "\n".join(
        [
            "| " + " | ".join(label for _, label in columns) + " |",
            "| " + " | ".join("---" for _ in columns) + " |",
        ]
        + [
            "| " + " | ".join(cell(row.get(key)) for key, _ in columns) + " |"
            for row in rows
        ]
    )


def render_result(name, result):
    if "error" in result:
        return result["error"]
    if name == "get_node":
        role = ROLE_LABELS.get(result.get("role"), "роль ещё не загружена")
        text = f"**gid {result['gid']}** · {role}. Приоритет: {fmt_number(result.get('priority_score'), 3)}.\n\n"
        text += result["evidence"]
        if result.get("rule_fired"):
            text += "\n\nПравило: " + result["rule_fired"]
        text += "\n\n" + _table(
            [
                dict(name="Входящие", amount=fmt_kzt(result["metrics"].get("in_sum"))),
                dict(
                    name="Исходящие", amount=fmt_kzt(result["metrics"].get("out_sum"))
                ),
            ],
            [("name", "Поток"), ("amount", "Сумма в выборке")],
        )
        return text + "\n\nРоль — гипотеза для проверки."
    if name == "common_downstream":
        text = f"В пределах {result['max_hops']} шагов найдены узлы, достижимые минимум из {result['min_sources']} указанных источников.\n\n"
        return (
            text
            + _table(
                result["nodes"],
                [
                    ("gid", "gid"),
                    ("source_count", "Источников"),
                    ("source_gids", "Исходные gid"),
                    ("max_hops", "Макс. шагов"),
                    ("role", "Роль"),
                    ("priority_score", "Приоритет"),
                ],
            )
            + "\n\n"
            + result["note"]
        )
    if name == "money_path":
        rows = [
            dict(
                route=" → ".join(map(str, p["gids"])), amount=fmt_kzt(p["min_edge_kzt"])
            )
            for p in result["paths"]
        ]
        note = (
            " Поиск ограничен: это не исчерпывающий список маршрутов."
            if result["search_truncated"]
            else ""
        )
        return (
            _table(rows, [("route", "Путь"), ("amount", "Мин. оборот ребра")])
            + "\n\n"
            + result["note"]
            + note
        )
    if name == "neighbors":
        return (
            _table(
                result["nodes"],
                [
                    ("gid", "gid"),
                    ("role", "Роль"),
                    ("hops", "Шагов"),
                    ("direct_in_kzt", "Прямые входящие, KZT"),
                    ("direct_out_kzt", "Прямые исходящие, KZT"),
                ],
            )
            + "\n\n"
            + result["note"]
        )
    if name == "top_nodes":
        return _table(
            result["nodes"],
            [
                ("gid", "gid"),
                ("role", "Роль"),
                ("priority_score", "Приоритет"),
                ("why", "Обоснование"),
            ],
        )
    if name == "cluster_info":
        return (
            f"**Кластер {result['cluster_id']}**: узлов {result['n_nodes']}, seed {result['n_seed']}, "
            f"внутренний оборот {fmt_kzt(result['sum_kzt_internal'])}.\n\nГипотеза: {result['hypothesis']}"
        )
    if name == "simulate_removal":
        if not result.get("available"):
            return result["reason"]
        values = result["result"]
        if not isinstance(values, dict):
            return "Результат симуляции A: " + str(values)
        return (
            "Симуляция удаления gid: "
            + ", ".join(map(str, result["gids"]))
            + "\n\n"
            + _table(
                [dict(metric=k, value=v) for k, v in values.items()],
                [("metric", "Метрика A"), ("value", "Значение")],
            )
        )
    return "Нет шаблона для этого инструмента."


def ask(question, ctx):
    q = question.lower().replace("ё", "е")
    calls = []
    cluster_match = re.search(r"кластер\w*\s*[#№]?\s*(\d+)", q)
    top_match = re.search(r"топ\s*[-–]?\s*(\d+)", q)
    cluster = int(cluster_match[1]) if cluster_match else None
    role = next(
        (r for r, words in ROLE_WORDS.items() if any(w in q for w in words)), None
    )
    # Не путаем номер кластера и размер топа с gid (gid может состоять из одной цифры).
    stripped = q
    for match in sorted(
        [m for m in (cluster_match, top_match) if m],
        key=lambda m: m.start(),
        reverse=True,
    ):
        stripped = (
            stripped[: match.start()]
            + " " * (match.end() - match.start())
            + stripped[match.end() :]
        )
    gids = list(
        dict.fromkeys(int(x) for x in re.findall(r"(?<![\w.-])\d+(?![\w.])", stripped))
    )

    def invoke(name, args):
        result = execute(ctx, name, args)
        calls.append({"tool": name, "args": args, "result": result})
        return result

    if any(w in q for w in ("заблок", "изъят", "удал", "блокиров")):
        if top_match:
            ranked = invoke(
                "top_nodes",
                {"n": int(top_match[1]), "role": role, "cluster_id": cluster},
            )
            if "error" in ranked:
                return render_result("top_nodes", ranked), calls
            gids = [n["gid"] for n in ranked["nodes"]]
        name, args = "simulate_removal", {"gids": gids}
    elif any(w in q for w in ("путь", "цепоч", "дошл", "маршрут")):
        if len(gids) != 2:
            return "Для пути укажи два gid: например, «Путь от 101 до 900».", calls
        name, args = "money_path", {"src": gids[0], "dst": gids[1]}
    elif any(w in q for w in ("собира", "сходят", "куда уход")) or (
        "кому" in q and len(gids) > 1
    ):
        if not gids:
            return (
                "Укажи gid источников: «Кто собирает деньги с этих клиентов: 101, 102, 103?»",
                calls,
            )
        name, args = "common_downstream", {"gids": gids}
    elif "топ" in q or "приоритет" in q or (role and not gids):
        name, args = (
            "top_nodes",
            {
                "n": int(top_match[1]) if top_match else 10,
                "role": role,
                "cluster_id": cluster,
            },
        )
    elif cluster is not None:
        name, args = "cluster_info", {"cluster_id": cluster}
    elif (
        any(
            w in q
            for w in (
                "сосед",
                "связ",
                "кому",
                "платил",
                "получал",
                "от кого",
                "входящ",
                "исходящ",
            )
        )
        and len(gids) == 1
    ):
        direction = (
            "in"
            if any(w in q for w in ("получал", "от кого", "входящ"))
            else (
                "out" if any(w in q for w in ("кому", "платил", "исходящ")) else "both"
            )
        )
        name, args = "neighbors", {"gid": gids[0], "direction": direction}
    elif len(gids) == 1:
        name, args = "get_node", {"gid": gids[0]}
    else:
        return (
            "В офлайн-режиме доступны: карточка gid, соседи, общий получатель, путь между двумя gid, топ, кластер и симуляция удаления. Укажи gid или номер кластера явно.",
            calls,
        )
    return render_result(name, invoke(name, args)), calls


def node_brief(record):
    if "error" in record:
        return record["error"]
    m = record["metrics"]
    role = ROLE_LABELS.get(record.get("role"), "не определена в загруженных данных")
    sources = (
        ", ".join(str(n["gid"]) for n in record["incoming"]) or "не показаны в выборке"
    )
    targets = (
        ", ".join(str(n["gid"]) for n in record["outgoing"]) or "не показаны в выборке"
    )
    attention = (
        "Исходящие могут быть обрезаны границей выборки."
        if m.get("is_frontier")
        else "Проверьте полноту входящих и исходящих переводов."
    )
    return (
        f"gid {record['gid']}: роль «{role}» рассматривается как гипотеза для проверки. "
        f"Приоритет проверки — {fmt_number(record.get('priority_score'), 3)}; обоснование: {record['evidence']} "
        f"В выборке входящие составляют {fmt_kzt(m.get('in_sum'))}, исходящие — {fmt_kzt(m.get('out_sum'))}. "
        f"Крупные входящие контрагенты: {sources}; исходящие: {targets}. {attention}"
    )
