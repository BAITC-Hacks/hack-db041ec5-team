# Правила, проверка и демо

Источник порогов — config.yaml; таблица формул — README.
moneygraph/roles.py возвращает все 6 score_*, base_role, итоговую и вторичную
роль, rule_fired и evidence. Балл — эвристическая выраженность признаков,
не вероятность. Недопустимый кандидат не может победить по высокому баллу.

## Полные формулы

ramp(x,lo,hi)=clip((x-lo)/(hi-lo),0,1). Отсутствующие дополнительные метрики
заменяются нулём в баллах; пропуск для seed/frontier остаётся неопределённым.

- consolidator: in_deg≥5. 0,5 ramp(in_deg,4,12) + 0,3 ramp(seed_sources,1,5)
  + 0,2 ramp(eff_payers/in_deg,0.3,0.8). Для frontier ×0,8.
- distributor: out_deg≥10. 0,7 ramp(out_deg,8,40)
  + 0,3 ramp(eff_receivers/out_deg,0.3,0.8).
- transit: не frontier; in_deg≤3, out_deg≤3, out_sum>0; seed либо
  pass∈[0,8;1,2]. Балл 0,6 clip(1−abs(pass−1)/0,2,0,1) + 0,4 fast_pass_share.
  Для seed близость pass=0,5, итог ×0,8.
- terminal: не frontier; положительный in_sum≥P50 положительных входов;
  out_sum=0 либо не-seed pass≤0,2. Балл 0,6 clip(1−pass/0,2,0,1)
  + 0,4 ramp(log1p(in_sum),log1p(P50),log1p(P95)). При out_sum=0 pass=0,
  включая seed. Если P50=P95, ramp равен 0 на пороге и 1 выше него.
- coordinator: ≥2 сигналов: seed_sources≥max(P95,3); ≥2 входящих от
  consolidator/transit или ≥2 исходящих к consolidator/distributor;
  n_clusters_touched≥3 или положительная betweenness≥P99. Берём только базовые
  роли соседей. Балл — среднее percentile(seed_sources), min(1,role_nb/4),
  max(percentile(betweenness),min(1,n_clusters_touched/4)); role_nb — максимум
  входящего/исходящего числа. Нулевые/отсутствующие seed_sources и betweenness
  дают нулевой соответствующий вклад, а не искусственный сигнал.
- peripheral: никто не подошёл. 1−max баллов допустимых активных кандидатов,
  для frontier не больше 0,5.

Базовая роль: argmax допустимых баллов, при равенстве consolidator → distributor
→ transit → terminal. Coordinator перекрывает базовую роль. Secondary — лучший
оставшийся кандидат. Evidence ≤200 символов; вторичная роль добавляется, если
помещается. Rule_fired сохраняет значения, пороги, кандидатов и баллы для проверки.
Обработка нулевой betweenness, вырожденных квантилей и допустимых баллов peripheral
уточняет неоднозначные граничные случаи чернового плана.

## Синтетическая проверка

Это проверка внутренней логики, не экспертная разметка реальных клиентов.
Строки — номера из tests/test_roles.py.

| Строка | Роль | Проверка |
|---|---|---|
| 0 | consolidator | 8 плательщиков, ровные доли |
| 1 | distributor | 60 получателей |
| 2 | transit | степени 1/1, pass=1 |
| 3 | peripheral | frontier без исходящих не означает terminal |
| 4 | peripheral | изолированный seed |
| 5 | terminal | внутренний узел с удержанием |
| 6 | terminal | seed только получает, вход не ниже медианы |
| 7 (вариант) | coordinator | 5 seed-источников и 3 кластера |

## Реальные данные: осталось выполнить

Parquet-файлы организаторов не предоставлены. Калибровка, ручная проверка
5 случайных + 3 лучших узлов каждой роли, реальные demo-gid и время на 2 248
узлах не заявляются выполненными. Тест реальных CSV включится при наличии data/.

После прогона изучите node_features.csv: распределения степеней, pass_ratio,
seed_sources и ролей. Для каждой роли выберите min(5,n) строк с random_state=42
и 3 лучших по role_score; проверьте потоки, frontier и объяснение. Запишите
gid, роль, вердикт «ок/спорно», причину. Меняйте правило, а не конкретный gid.
После калибровки зафиксируйте пороги в config.yaml и обновите документацию.

Демо: первый узел топа; frontier с out_sum=0; transit с максимальным
fast_pass_share, если такой есть. Выпишите правило, роль и балл, почему
не две соседние роли, вклады contribution_*, rank, freq_top20.
Фактические Jaccard и время берите из run_report.json, не из плана.
