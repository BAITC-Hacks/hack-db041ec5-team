"""Единая палитра и названия для графа, таблиц и диаграммы."""

ROLE_COLORS = {
    "coordinator": "#C0392B",
    "consolidator": "#E08E0B",
    "distributor": "#7B4BC4",
    "transit": "#1F6FB2",
    "terminal": "#2E8753",
    "peripheral": "#A0A8B5",
}
ROLE_LABELS = {
    "coordinator": "Координатор",
    "consolidator": "Консолидатор",
    "distributor": "Распределитель",
    "transit": "Транзит",
    "terminal": "Конечный получатель",
    "peripheral": "Периферия",
}
CLUSTER_COLORS = [
    "#4E79A7",
    "#F28E2B",
    "#E15759",
    "#76B7B2",
    "#59A14F",
    "#EDC948",
    "#B07AA1",
    "#FF9DA7",
    "#9C755F",
    "#6F8FAF",
    "#8C9A52",
    "#956A9C",
]
METRIC_LABELS = {
    "in_deg": "Плательщики",
    "out_deg": "Получатели",
    "in_sum": "Входящие, KZT",
    "out_sum": "Исходящие, KZT",
    "pass_ratio": "Отдал / получил",
    "seed_kzt": "Атрибутировано seed, KZT",
    "seed_sources": "Seed-источники",
    "top_seeds": "Крупнейшие seed-источники",
    "fast_pass_share": "Доля быстрого транзита",
    "depth": "Колено",
    "is_seed": "Исходный seed",
    "is_frontier": "Граница выборки",
    "ext_inflow": "Неучтённый приток, KZT",
    "seed_reach": "Достигающие seed",
    "in_tx": "Входящие операции",
    "out_tx": "Исходящие операции",
}
STABILITY_COLUMNS = ("freq_top20", "top20_frequency", "top20_share", "stability_top20")


def cluster_color(cluster_id):
    return (
        "#A0A8B5"
        if cluster_id in (None, 0)
        else CLUSTER_COLORS[(int(cluster_id) - 1) % 12]
    )


def fmt_number(value, digits=0):
    if value is None:
        return "—"
    try:
        return f"{float(value):,.{digits}f}".replace(",", " ")
    except (ValueError, TypeError):
        return str(value)


def fmt_kzt(value):
    return f"{fmt_number(value)} KZT" if value is not None else "—"
