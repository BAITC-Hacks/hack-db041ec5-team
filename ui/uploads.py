"""User-facing file analysis workflow; no LLM imports or network calls."""

from pathlib import Path
import streamlit as st

from moneygraph.uploads import save_uploads
from run import run_pipeline


def analysis_controls(root, out_dir, data_dir, cfg_path):
    with st.expander('Загрузить файлы и выполнить анализ', expanded=not (Path(out_dir) / 'nodes_roles.csv').is_file()):
        st.write('Загрузите три файла: nodes, edges и transactions. Роли, приоритеты и связи рассчитаются автоматически.')
        st.caption('Поддерживаются Parquet и CSV с запятой и UTF-8. Имена: nodes.parquet/csv, edges.parquet/csv, transactions.parquet/csv. Файлы остаются на этом компьютере.')
        with st.expander('Какие колонки нужны'):
            st.code('nodes: gid, depth, is_seed\nedges: src, dst, sum_kzt, n_tx, depth\ntransactions: src, dst, date, sum_kzt', language=None)
            st.write('gid/src/dst — целые идентификаторы; суммы в KZT; date — дата/время ISO; depth — колено; is_seed — true/false или 0/1. Рёбра должны совпадать с суммами и числом операций transactions.')
        files = st.file_uploader('Три файла данных', type=['parquet', 'csv'], accept_multiple_files=True, key='analysis_files')
        truncated = st.checkbox('Выгрузка ограничена глубиной обхода', value=True, key='upload_truncated')
        depth = st.number_input('Последнее выгруженное колено', min_value=1, max_value=100, value=4, disabled=not truncated)
        st.caption('Для полной сети снимите ограничение. Порог ролей и валюта должны соответствовать смыслу ваших данных; произвольные банковские выписки автоматически не преобразуются.')
        uploaded = st.button('Загрузить и проанализировать', type='primary', disabled=len(files) != 3, key='analyze_uploads')
        local = st.button('Пересчитать данные из папки data', key='analyze_local')
        if uploaded or local:
            try:
                if uploaded:
                    target, source, config = save_uploads([(f.name, f.getvalue()) for f in files], root / 'output' / 'uploads', cfg_path, int(depth) if truncated else None)
                else:
                    # An independent output directory prevents stale results after failure.
                    import uuid
                    target, source, config = root / 'output' / 'runs' / uuid.uuid4().hex, Path(data_dir), Path(cfg_path)
                with st.spinner('Анализирую файлы: граф, роли, кластеры и паттерны…'):
                    report = run_pipeline(source, target, config)
                st.session_state['active_analysis'] = tuple(map(str, (target, source, config)))
                st.session_state['analysis_done'] = f"Анализ завершён: {report['n_nodes']} узлов за {report['elapsed_seconds']:.1f} с."
            except Exception as exc:
                st.error(f'Анализ не выполнен: {exc}')
                st.info('Ниже остаётся предыдущий результат, если он был. Исправьте входные файлы и повторите анализ.')
        if st.session_state.get('analysis_done'):
            st.success(st.session_state['analysis_done'])
        if st.session_state.get('active_analysis'):
            st.caption('Текущий результат: ' + st.session_state['active_analysis'][0])
            if st.button('Вернуться к данным из настроек', key='reset_analysis'):
                st.session_state.pop('active_analysis', None)
                st.session_state.pop('analysis_done', None)
                st.rerun()
    active = st.session_state.get('active_analysis', (out_dir, data_dir, cfg_path))
    with st.expander('Скачать результаты анализа'):
        for name in ('nodes_roles.csv', 'clusters.csv', 'top_nodes.csv'):
            path = Path(active[0]) / name
            if path.is_file():
                st.download_button(name, path.read_bytes(), file_name=name, mime='text/csv', key='export_' + name)
    return active
