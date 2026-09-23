> Историческая версия до упрощения запуска и отключения ИИ в интерфейсе. Актуальные действия и возможности: [README](../README.md) и [CHECK_PROJECT](CHECK_PROJECT.md).

# Запуск веб-приложения A/B/C

Python 3.12. Команды выполняются из корня проекта.

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
Copy-Item .env.example .env
.\start.ps1 -Demo
```

Если PowerShell запрещает запуск скрипта:

```powershell
$env:MONEYGRAPH_DEMO='1'
.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1
```

Открыть http://127.0.0.1:8501. В Linux используйте `.venv/bin/python`.
Демо включается также переключателем в боковой панели. Все его числа вымышлены.
Слева находятся параметры данных, фильтры графа и режим ассистента.
Вкладка «Обзор» содержит dashboard, динамику переводов и скачивание CSV.

## Полный расчёт на синтетических данных

```powershell
.venv\Scripts\python.exe scripts\demo_pipeline.py
```

Выключите готовое демо в UI. В «Источники данных» задайте `output/demo` и
`data/demo`. Здесь роли рассчитывает настоящее ядро; они могут отличаться от
заданных ролей готового демонстрационного интерфейса.
Предупреждения о размере выборки ожидаемы: демо меньше конкурсного датасета.

## Данные команды

Положите nodes.parquet, edges.parquet, transactions.parquet в data/.
Схемы описаны в корневом README. Выполните:

```powershell
.venv\Scripts\python.exe run.py --data data --out output --config config.yaml
.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1
```

Перед просмотром проверьте `status: ok` в output/run_report.json.
Не используйте выгрузки незавершённого запуска. В UI нажмите «Обновить данные».
Офлайн не требует ключа. Примеры: «Карточка 900», «Кому платил 900?»,
«Путь от 101 до 920», «Топ-5 консолидаторов». Это локальный помощник с
ограниченным набором распознаваемых вопросов; неизвестные запросы не выдумывает.
Для опционального онлайн настройте провайдер, endpoint, ключ и модель в .env
и явно включите онлайн в интерфейсе. NVIDIA/Brev: [NVIDIA_SETUP](NVIDIA_SETUP.md).
Для OpenAI задайте MONEYGRAPH_LLM_PROVIDER=openai, OPENAI_API_KEY и
MONEYGRAPH_LLM_BASE_URL=https://api.openai.com/v1.

## Перенос на машину без интернета

На машине с сетью с той же ОС, архитектурой и Python 3.12:

```powershell
.venv\Scripts\python.exe -m pip download -r requirements-lock.txt -d wheelhouse
```

Перенесите исходники, wheelhouse и установщик Python. На целевой машине:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install --no-index --find-links wheelhouse -r requirements-lock.txt
.venv\Scripts\python.exe -m pytest tests tests_c -q
.\start.ps1 -Demo
```

wheelhouse не включён в исходный ZIP. Lock проверен на Windows/Python 3.12;
другие ОС требуют отдельной проверки. Для обновления зависимостей используйте
requirements.txt и повторно прогоните тесты перед обновлением lock.

## Командные зоны ответственности

A — moneygraph: граф, атрибуция, устойчивость; B — роли, приоритеты, гипотезы;
C — ui и assistant. Контракты CSV не менять без совместного обновления загрузчика.
Рабочие реализации интегрированы, вместо них пустые заглушки не устанавливаются.
Схема: docs/ARCHITECTURE.md. Проверки: docs/VERIFICATION_CURRENT.md.
