"""Схемы function calling; валидируются также до исполнения в Python."""

INTEGER = {"type": "integer"}
GIDS = {"type": "array", "items": INTEGER, "minItems": 1, "maxItems": 50}


def opt(kind, **constraints):
    return {"type": [kind, "null"], **constraints}


SPECS = {
    "get_node": (
        "Карточка клиента: роль, объяснения, метрики и контрагенты.",
        {"gid": INTEGER},
        ["gid"],
    ),
    "neighbors": (
        "Окрестность узла; in=входящие, out=исходящие, both=оба направления.",
        {
            "gid": INTEGER,
            "direction": opt("string", enum=["in", "out", "both", None]),
            "hops": opt("integer", minimum=1, maximum=3),
            "min_kzt": opt("number", minimum=0),
        },
        ["gid"],
    ),
    "common_downstream": (
        "Куда сходятся направленные пути от нескольких gid; по умолчанию не менее 60% источников.",
        {
            "gids": GIDS,
            "max_hops": opt("integer", minimum=1, maximum=8),
            "min_sources": opt("integer", minimum=1, maximum=50),
        },
        ["gids"],
    ),
    "money_path": (
        "До трёх направленных путей; минимальный оборот ребра не является атрибутированной суммой денег.",
        {
            "src": INTEGER,
            "dst": INTEGER,
            "max_len": opt("integer", minimum=1, maximum=8),
        },
        ["src", "dst"],
    ),
    "top_nodes": (
        "Приоритетные узлы по роли или кластеру; приоритеты берутся только из выгрузок B.",
        {
            "role": opt(
                "string",
                enum=[
                    "coordinator",
                    "consolidator",
                    "distributor",
                    "transit",
                    "terminal",
                    "peripheral",
                    None,
                ],
            ),
            "cluster_id": opt("integer"),
            "n": opt("integer", minimum=1, maximum=50),
        },
        [],
    ),
    "cluster_info": (
        "Размер, оборот, гипотеза и приоритетные узлы кластера.",
        {"cluster_id": INTEGER},
        ["cluster_id"],
    ),
    "simulate_removal": (
        "Расчёт эффекта удаления через функцию A. Это симуляция, реальной блокировки счетов нет.",
        {"gids": GIDS},
        ["gids"],
    ),
}
PARAMETERS = {
    name: {
        "type": "object",
        "properties": fields,
        "required": required,
        "additionalProperties": False,
    }
    for name, (_, fields, required) in SPECS.items()
}
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "strict": True,
            "parameters": {**PARAMETERS[name], "required": list(fields)},
        },
    }
    for name, (description, fields, _) in SPECS.items()
]
