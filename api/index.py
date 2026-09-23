"""Vercel-compatible API using the same calculation and assistant as Streamlit."""
import io
import json
import os
from pathlib import Path
import secrets
import tempfile
import gzip
from zipfile import ZipFile, ZIP_DEFLATED
from functools import lru_cache

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from itsdangerous import BadSignature, URLSafeTimedSerializer
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env', override=False)
app = FastAPI(title='Money Graph', docs_url=None, redoc_url=None, openapi_url=None)
DEV_SECRET = secrets.token_hex(32)
MAX_BODY = 4_000_000


@app.middleware('http')
async def protect(request: Request, call_next):
    if request.url.path.startswith('/api/'):
        if request.method == 'POST':
            body = bytearray()
            async for part in request.stream():
                body.extend(part)
                if len(body) > MAX_BODY:
                    return JSONResponse({'detail': 'Запрос больше 4 МБ. Для большого набора используйте локальный запуск.'}, status_code=413)
            request._body = bytes(body)
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'same-origin'
    return response


def serializer():
    secret = os.getenv('MONEYGRAPH_SESSION_SECRET') or os.getenv('OPENAI_API_KEY')
    if not secret and os.getenv('VERCEL'):
        raise HTTPException(503, 'Задайте MONEYGRAPH_SESSION_SECRET для офлайн-работы на сервере.')
    return URLSafeTimedSerializer(secret or DEV_SECRET, salt='moneygraph-analysis-v1')


def read_packet(token):
    if token == 'showcase':
        return showcase()['packet']
    try:
        return serializer().loads(token, max_age=3600)
    except BadSignature:
        raise HTTPException(400, 'Результат изменён или срок сессии истёк. Повторите анализ.')


@lru_cache(maxsize=1)
def showcase():
    path = ROOT / 'showcase' / 'analysis.json.gz'
    if not path.is_file():
        raise HTTPException(404, 'Конкурсный набор не подготовлен. Выполните scripts/prepare_showcase.py.')
    with gzip.open(path, 'rt', encoding='utf-8') as source:
        return json.load(source)


def presentation(packet, report, quality, token):
    from ui.data import clean
    import pandas as pd
    tables = {name.removesuffix('.csv'): browser_safe(clean(pd.read_csv(io.StringIO(value)).to_dict('records')))
              for name, value in packet['csv'].items() if name != 'node_features.csv'}
    return {'token': token, 'graph': packet['graph'], 'tables': tables, 'report': report,
            'n_transactions': len(pd.read_csv(io.StringIO(packet['transactions']))), 'quality': quality}


@app.get('/api/default')
def default_analysis():
    saved = showcase()
    return presentation(saved['packet'], saved['report'], saved['quality'], 'showcase')


@app.post('/api/recalculate')
def recalculate():
    files = [(p.name, p.read_bytes()) for p in (ROOT / 'showcase' / 'source').glob('*.parquet')]
    if len(files) != 3:
        raise HTTPException(404, 'Исходный конкурсный набор отсутствует.')
    return calculate(files, 4)


def context(packet):
    import pandas as pd
    from ui.data import assemble
    frames = {name.removesuffix('.csv'): pd.read_csv(io.StringIO(text))
              for name, text in packet['csv'].items()}
    tx = pd.read_csv(io.StringIO(packet['transactions']))
    tx['date'] = pd.to_datetime(tx.date, utc=True)
    return assemble(frames, packet['graph'], tx=tx, cfg=packet['config'])


def browser_safe(value):
    # Preserve all int64 IDs, including lists of IDs in tool results.
    if isinstance(value, dict):
        return {k: browser_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [browser_safe(v) for v in value]
    if isinstance(value, int) and abs(value) > 2 ** 53 - 1:
        return str(value)
    return value


@app.get('/api/status')
def status():
    from assistant.agent import api_key
    return {'ready': True, 'online_available': bool(api_key()),
            'model': os.getenv('MONEYGRAPH_LLM_MODEL', 'gpt-4.1-mini')}


def calculate(files, frontier):
    from moneygraph.uploads import save_uploads
    from moneygraph.io import load
    from run import run_pipeline
    from ui.data import clean
    import pandas as pd
    import yaml
    with tempfile.TemporaryDirectory(prefix='moneygraph-') as directory:
        out, data, cfg = save_uploads(files, Path(directory), ROOT / 'config.yaml', frontier)
        nodes, edges, tx = load(data)
        if len(nodes) > 5000 or len(tx) > 20000:
            raise ValueError('Веб-версия ограничена 5 000 узлов и 20 000 операций. Большие наборы анализируйте локально.')
        report = run_pipeline(data, out, cfg)
        csv_files = {p.name: p.read_text(encoding='utf-8') for p in out.glob('*.csv')}
        graph = json.loads((out / 'graph.json').read_text(encoding='utf-8'))
        packet = {'csv': csv_files, 'graph': graph, 'transactions': tx.to_csv(index=False),
                  'config': yaml.safe_load(cfg.read_text(encoding='utf-8'))}
        tables = {name.removesuffix('.csv'): browser_safe(clean(pd.read_csv(io.StringIO(text)).to_dict('records')))
                  for name, text in csv_files.items() if name != 'node_features.csv'}
        result = {'token': serializer().dumps(packet), 'graph': graph, 'tables': tables, 'report': report,
                  'n_transactions': len(tx), 'quality': (out / 'data_quality.md').read_text(encoding='utf-8')}
        if len(json.dumps(result, ensure_ascii=False).encode()) > MAX_BODY:
            raise ValueError('Результат превышает лимит веб-версии. Используйте START.cmd для этого набора.')
        return result


@app.post('/api/analyze')
async def analyze(request: Request):
    form = await request.form()
    files = []
    for value in form.getlist('files'):
        if not hasattr(value, 'read'):
            raise HTTPException(400, 'Ожидаются три файла.')
        files.append((value.filename, await value.read()))
    try:
        boundary = str(form.get('frontier', '4'))
        frontier = None if boundary == 'none' else int(boundary)
        return await run_in_threadpool(calculate, files, frontier)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        raise HTTPException(400, str(exc)[:400])


class SessionRequest(BaseModel):
    token: str = Field(max_length=MAX_BODY)


class NodeRequest(SessionRequest):
    gid: str = Field(max_length=20, pattern=r'^-?\d+$')
    online: bool = False


@app.post('/api/node')
def node(body: NodeRequest):
    from assistant.tools import get_node
    try:
        return browser_safe(get_node(context(read_packet(body.token)), body.gid))
    except ValueError as exc:
        raise HTTPException(400, str(exc)[:400])


class ChatRequest(SessionRequest):
    question: str = Field(min_length=1, max_length=4000)
    history: list[dict] = Field(default_factory=list, max_length=6)
    online: bool = False


@app.post('/api/chat')
def chat(body: ChatRequest):
    from assistant.agent import ask
    from dataclasses import asdict
    result = ask(body.question, context(read_packet(body.token)), body.history,
                 os.getenv('MONEYGRAPH_LLM_MODEL', 'gpt-4.1-mini'), online=body.online)
    return browser_safe(asdict(result))


@app.post('/api/brief')
def brief(body: NodeRequest):
    from assistant.agent import brief as make_brief
    from dataclasses import asdict
    result = make_brief(context(read_packet(body.token)), body.gid,
                       os.getenv('MONEYGRAPH_LLM_MODEL', 'gpt-4.1-mini'), online=body.online)
    return browser_safe(asdict(result))


class ExportRequest(SessionRequest):
    filename: str = Field(max_length=80)


@app.post('/api/export')
def export(body: ExportRequest):
    packet = read_packet(body.token)
    if body.filename == 'moneygraph-results.zip':
        buffer = io.BytesIO()
        with ZipFile(buffer, 'w', ZIP_DEFLATED) as archive:
            for name, content in packet['csv'].items():
                archive.writestr(name, content)
            archive.writestr('graph.json', json.dumps(packet['graph'], ensure_ascii=False))
            archive.writestr('analysis-config.json', json.dumps(packet['config'], ensure_ascii=False))
        return Response(buffer.getvalue(), media_type='application/zip',
                        headers={'Content-Disposition': 'attachment; filename="moneygraph-results.zip"'})
    if body.filename not in packet['csv']:
        raise HTTPException(404, 'Выгрузка не найдена.')
    return Response(packet['csv'][body.filename], media_type='text/csv; charset=utf-8',
                    headers={'Content-Disposition': f'attachment; filename="{body.filename}"'})


@app.get('/')
def index():
    return FileResponse(ROOT / 'web' / 'index.html')


app.mount('/assets', StaticFiles(directory=ROOT / 'web'), name='assets')
