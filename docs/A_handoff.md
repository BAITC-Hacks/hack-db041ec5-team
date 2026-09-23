# Часть A: интеграция графа и метрик

Обновление: данные организаторов получены и проверены, см.
[real_data_review.md](real_data_review.md). В graph.json идентификаторы узлов
и концов рёбер — строки для сохранения больших gid в браузере. Общий
config.yaml теперь задаёт attribution.max_iter=1000; умолчание функции — 200.
Упоминания отсутствия данных ниже относятся к первоначальной передаче части A.

Реализованы `io`, `graph`, `features`, `flow`, `clusters`, `patterns`, `resilience`.
Общий `run.py`, `config.yaml`, роли и UI остаются точками интеграции B/C.
В репозитории пока нет реальных данных организаторов: факты из ТЗ — ожидания
для отчёта, а не результаты анализа. Проверки выполнены на синтетических данных.

## Запуск

Python 3.11+; локально проверено на Python 3.12.14.

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-a.txt
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m moneygraph.prepare --data data --out output
```

`prepare` — самостоятельная проверка части A до появления общего `run.py`.
Принимает необязательный `--config-json path.json` с тем же словарём `cfg`.
Пишет `node_features.csv`, `graph.json`, `data_quality.md`, `cluster_metrics.csv`,
`cycles.csv`, `metrics_report.json`. `cluster_metrics.csv` — промежуточная сводка
для B, не финальный `clusters.csv` с гипотезами и фиксированной схемой ТЗ.
Сценарии изъятия запускаются после получения реальных приоритетов от B.

## Контракт для общего оркестратора

```python
from moneygraph.io import load, validate, write_quality_report, ensure_valid_data
from moneygraph.graph import build_graph, compute_layout, build_graph_json
from moneygraph.features import compute_features, add_cluster_features
from moneygraph.clusters import cluster, cluster_stability, cluster_summary
from moneygraph.patterns import detect_patterns
from moneygraph.resilience import compare_strategies

nodes, edges, tx = load(data_dir)
checks = validate(nodes, edges, tx)
write_quality_report(checks, out_dir)
ensure_valid_data(nodes, edges, tx)
G = build_graph(nodes, edges)
F = compute_features(G, nodes, edges, tx, cfg)
clusters = cluster(G, cfg)
F = add_cluster_features(F, G, clusters)
F, cycles = detect_patterns(G, F, cfg)
stability = cluster_stability(G, clusters, cfg)
summary = cluster_summary(clusters, F, edges, stability)
# После assign_roles/prioritize участника B:
# payload = build_graph_json(G, compute_layout(G, cfg), F, R, P, clusters)
# resilience = compare_strategies(G, F, edges, P.priority_score, cfg)
```

F, R, P и Series кластеров индексированы по `gid`. `compute_features` вычисляет
v0/v1/v2, но `n_clusters_touched`, `anomaly_z`, `in_cycle` первоначально NaN:
для них нужны следующие вызовы из примера. Входные DataFrame не меняются.
Отсутствие наблюдаемых операций даёт нулевые суммы и степени; `pass_ratio`
не определён для seed, frontier и нулевого входящего оборота.

## Настройки для config.yaml участника B

Все параметры необязательны. Значения ниже совпадают с умолчаниями модулей.

```yaml
features:
  frontier_depth: 4
  fast_pass_days: 2
  pagerank_max_iter: 1000
  betweenness_k: null
attribution:
  max_iter: 200
  tol_kzt: 0.000001
  min_source_kzt: 10000
  min_source_share: 0.01
clusters:
  resolution: 1.0
  stability_runs: 20
layout:
  iterations: 50
  scale: 1500
patterns:
  max_cycles: 10000
  max_length: 5
resilience:
  min_flow_depth: 2
  sizes: [5, 10, 20, 50]
  random_runs: 20
```

В тесте с переводами по 100 KZT порог `min_source_kzt=1`: при рабочем пороге
10 000 этот пример закономерно имеет `seed_sources=0`, хотя `seed_kzt=100`.

## Данные — раздел для README

Вход: nodes.parquet (`gid, depth, is_seed`), edges.parquet
(`src, dst, sum_kzt, n_tx, depth`), transactions.parquet
(`src, dst, date, sum_kzt`). Идентификаторы сохраняются, строковые seed-флаги
не преобразуются молча в True. Изолированные узлы сохраняются; дубликаты пар
рёбер агрегируются. При другой схеме файлов требуется явное сопоставление
колонок после получения README датасета.

Валидация сравнивает размеры, даты, оборот, компоненты и суммы/количества
транзакций с рёбрами. Расхождения отражаются в предупреждениях и отчёте;
отсутствующие обязательные колонки, неизвестные концы рёбер и некорректные
суммы препятствуют расчёту, потому что результат был бы неоднозначен.

## Ограничения — раздел для README

- На 4-м колене исходящие не наблюдаются; нулевой исходящий оборот не доказывает
  накопление средств. Ролевые ограничения применяет B по `is_frontier`.
- Входящие seed неполны, операции ниже 5 000 KZT и другие каналы не представлены.
- Haircut-атрибуция — гипотеза о составе денег по агрегированному периоду,
  а не доказательство происхождения; она не учитывает порядок транзакций.
- `ext_inflow` — собственная подпитка узла. `ext_kzt` — пришедшие деньги
  EXT-происхождения, которые могут распространяться дальше от места подпитки.
- Цикл без наблюдаемого источника имеет неопределённый состав. Такие деньги
  не объявляются EXT: неатрибутированный остаток и сходимость находятся в
  `attribute_sources(...).attrs` и `F.attrs['attribution']`, а при локальном
  запуске — в `metrics_report.json`. Исчерпание итераций выдаёт предупреждение.
- Быстрая отправка означает наличие любого поступления за предшествующие
  2 дня; это не доказательство связи двух конкретных платежей. Даты без времени
  допускают поступление и отправку в один день. Время нормализуется в UTC.
- Устойчивость кластера считается по задаче A: средняя максимальная доля
  его участников, оставшаяся вместе. Это не доля сохранённых пар из общего плана.
  Кластер 0 объединяет изоляты условно, его устойчивость по соглашению равна 1.
- `n_clusters_touched` включает кластер самого узла по задаче A6.
- MAD=0 не позволяет оценить соответствующий z-score; полностью неопределённый
  `anomaly_z` остаётся NaN. При ограничении числа циклов отсутствие `in_cycle`
  не доказывает отсутствие цикла; усечение отражено в attrs и отчёте.
- При изъятии in/out и подпитка вычисляются заново. Это сценарная модель,
  `flow_share` может превышать 1; при нулевом базовом потоке результат NaN.
  Знаменатель LCC — исходное число неизолированных узлов; компоненты после
  удаления включают оставшиеся изоляты. Число удаляемых узлов ограничено размером сети.

## Масштабирование — раздел для README

Для миллиона узлов потребуется отдельная реализация: колонночное чтение
parquet, агрегация вне памяти, CSR для обходов, выборочная betweenness,
Leiden/графовый движок и раскладка только выбранного подграфа. Текущая матрица
атрибуции имеет размер узлы × (seed + 1), поэтому рост числа seed потребует
пакетного расчёта источников. Точный расчёт центральностей, полный spring-layout
и поиск циклов не рассчитаны на миллион узлов. Лимит 5 минут и реальные числа
проверяются после получения исходных parquet, а не выводятся из игрушечных тестов.
