from pathlib import Path
import json
import pytest
from fastapi.testclient import TestClient

from api.index import app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('MONEYGRAPH_SESSION_SECRET', 'test-signing-secret-only')
    monkeypatch.setenv('OPENAI_API_KEY', '')
    monkeypatch.setenv('MONEYGRAPH_LLM_PROVIDER', 'openai')
    return TestClient(app)


def test_no_password_required_locally_or_on_vercel(client, monkeypatch):
    assert client.get('/api/status').status_code == 200
    monkeypatch.setenv('VERCEL', '1')
    assert client.get('/api/status').status_code == 200
    assert client.get('/').status_code == 200
    assert 'id="password"' not in client.get('/').text


def test_contest_opens_without_key_and_keeps_int64_ids(client, monkeypatch):
    monkeypatch.setenv('VERCEL', '1')
    monkeypatch.delenv('MONEYGRAPH_SESSION_SECRET')
    result = client.get('/api/default')
    assert result.status_code == 200
    data = result.json()
    assert data['report']['n_nodes'] == 2248
    assert data['n_transactions'] == 4840
    assert len(data['tables']['top_nodes']) >= 20
    gid = data['tables']['top_nodes'][0]['gid']
    assert isinstance(gid, str)
    card = client.post('/api/node', json={'token':data['token'], 'gid':gid})
    assert card.status_code == 200 and card.json()['gid'] == gid
    assert client.post('/api/export',json={'token':data['token'],'filename':'nodes_roles.csv'}).status_code == 200
    from zipfile import ZipFile
    import io
    archive = client.post('/api/export',json={'token':data['token'],'filename':'moneygraph-results.zip'})
    assert archive.status_code == 200
    with ZipFile(io.BytesIO(archive.content)) as z:
        assert {'nodes_roles.csv','clusters.csv','top_nodes.csv','graph.json'} <= set(z.namelist())
        assert not any('.env' in name for name in z.namelist())


def test_web_upload_graph_node_chat_export(client, sample_network):
    frames = [f.copy() for f in sample_network]
    mapping = {int(g):100000000000000000+int(g) for g in frames[0].gid}
    frames[0].gid = frames[0].gid.map(mapping)
    for f in frames[1:]:
        f.src, f.dst = f.src.map(mapping), f.dst.map(mapping)
    files = [('files', (n+'.csv', f.to_csv(index=False).encode(), 'text/csv'))
             for n,f in zip(['nodes','edges','transactions'],frames)]
    response = client.post('/api/analyze',files=files,data={'frontier':'none'})
    assert response.status_code == 200, response.text[:500]
    result = response.json()
    assert result['report']['n_nodes'] == 32
    assert isinstance(result['tables']['top_nodes'][0]['gid'],str)
    token = result['token']
    gid = str(mapping[7])
    node = client.post('/api/node',json={'token':token,'gid':gid}).json()
    assert node['gid'] == gid and node['metrics']['in_sum'] == 500000
    chat = client.post('/api/chat',json={'token':token,'question':'Карточка '+gid,'online':False}).json()
    assert chat['mode'] == 'офлайн' and chat['calls'][0]['result']['gid'] == gid
    csv = client.post('/api/export',json={'token':token,'filename':'nodes_roles.csv'})
    assert csv.status_code == 200 and gid in csv.text
    assert client.post('/api/export',json={'token':token,'filename':'../.env'}).status_code == 404
    assert client.post('/api/node',json={'token':token+'x','gid':gid}).status_code == 400


def test_invalid_upload_and_oversized_request(client):
    assert client.post('/api/analyze',files={'files':('nodes.csv',b'gid\n1')}).status_code == 400
    assert client.post('/api/chat',content=b'x'*4_000_001).status_code == 413


def test_server_key_not_in_public_config(client,monkeypatch):
    secret='fake-api-secret-for-test'
    monkeypatch.setenv('OPENAI_API_KEY',secret)
    r=client.get('/api/status')
    assert r.json()['online_available'] and secret not in r.text
