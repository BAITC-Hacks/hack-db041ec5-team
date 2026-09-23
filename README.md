# hack-db041ec5-team
Hackathon team repository for ООО «Бнал»

Часть A — граф, признаки, атрибуция источников и кластеры — находится в
`moneygraph/`. Инструкция запуска, контракты для B/C и ограничения:
[docs/A_handoff.md](docs/A_handoff.md).

```powershell
python -m pip install -r requirements-a.txt
python -m pytest -q
python -m moneygraph.prepare --data data --out output
```

Для расчёта нужны `nodes.parquet`, `edges.parquet`, `transactions.parquet` в `data/`.
Данные и генерируемые выгрузки не включаются в Git.
