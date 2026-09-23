# Контракт подключения части C

## Владение файлами

| Владелец | Содержание |
| --- | --- |
| C | app.py, ui/, assistant/, tests_c/, документация интерфейса и схема |
| A | Граф, метрики, атрибуция, кластеры, раскладка, симуляция |
| B | Роли, приоритеты, обоснования, выгрузки, run.py, config.yaml |

В этом архиве нет заглушек A/B. Первоначальная задача C1 про общий каркас
уже относится к командному проекту; пользователь запросил только часть C.

## Основные файлы

| Файл | Колонки / поля |
| --- | --- |
| output/graph.json | nodes: id, x, y, role, cluster, priority, is_seed, depth; edges: source, target, sum_kzt, n_tx |
| output/nodes_roles.csv | gid, role, role_score, cluster_id, priority_score, evidence |
| output/top_nodes.csv | rank, gid, role, priority_score, why |
| output/clusters.csv | cluster_id, n_nodes, n_seed, sum_kzt_internal, top_gids, hypothesis |
| output/node_features.csv | gid и признаки из PLAN.md; score_coordinator, score_consolidator, score_distributor, score_transit, score_terminal, score_peripheral; rule_fired |
| data/transactions.parquet | src, dst, date, sum_kzt |
| output/resilience.csv | n_removed, strategy, lcc_share, flow_share |
| output/next_requests.csv | request_type, n_nodes, gids, why |

Для JSON используйте числовые id/source/target, конечные x/y, priority в
диапазоне 0–1. seed передаётся как boolean. В CSV gid — целое число,
отдельная именованная колонка. Для F с индексом gid:

```python
F.to_csv(out_dir / "node_features.csv", index=True, index_label="gid")
```

Роли: coordinator, consolidator, distributor, transit, terminal, peripheral.
Колонки обязательных CSV остаются строго по ТЗ; дополнительные метрики
нужно передавать в node_features.csv. Приоритет и роль из CSV важнее
аналогичных значений в graph.json: старый JSON не переопределит новый CSV.

Устойчивость попадания в топ-20 читается из `freq_top20`. Для совместимости
также распознаются `top20_frequency`, `top20_share`, `stability_top20`.
Все варианты означают **долю 0–1**. Не передавайте 90 вместо 0.9.

Даты транзакций приводятся к UTC и группируются по календарному дню UTC.
Если команда использует иной часовой пояс, согласуйте его до экспорта.
Неверные даты пропускаются с предупреждением. Повторные строки стратегии
устойчивости для одного n_removed усредняются с явной подписью.

Если graph.json ещё не готов, C может прочитать nodes.parquet и
edges.parquet из data/, а признаки F v0 — из node_features.csv.
Исходные роли и метрики C при этом не вычисляет. Для режима F v0 включите
«Весь граф · без порога»: приоритетов может ещё не быть.

## Симуляция

Ожидается реальная функция участника A:

```python
simulate_removal(G, F, edges, removed: list[int], cfg) -> dict
```

- G — направленный networkx.DiGraph, вес суммы в атрибуте sum_kzt;
- F — DataFrame с индексом gid;
- edges — DataFrame с src, dst, sum_kzt, n_tx;
- removed — список gid, проверенных на наличие в графе;
- cfg — словарь из config.yaml в корне проекта.

Передаются копии, чтобы модуль не изменил контекст интерфейса. Исключения
модуля A превращаются в сообщение о недоступности; C не имитирует расчёт.
Объясните в документации команды смысл flow_share: оставшаяся доля или
отрезанная доля. Интерфейс не переименовывает её в неверную величину.

## Проверка интеграции

1. A/B запускают свой run.py и передают все готовые output/.
2. C выключает демо, проверяет число узлов, статус загрузки и исходные seed.
3. Сверяются три произвольных gid: роль, score, evidence, суммы и направления.
4. Проверяются изолированный seed и frontier-узел.
5. Сверяются история транзакций и две кривые устойчивости с исходными CSV.
6. Выполняются одинаковые вопросы онлайн и офлайн; сравниваются вызванные инструменты.
7. Все трое проверяют установку в новых venv; объединённые версии пакетов фиксируются командой.
