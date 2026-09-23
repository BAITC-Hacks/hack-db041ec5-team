import json
from types import SimpleNamespace

from assistant.agent import ask, brief
from openai import APIConnectionError, BadRequestError
from openai.types.chat import ChatCompletion


def completion(content=None, name=None, args=None):
    message = {"role": "assistant", "content": content}
    if name:
        message["tool_calls"] = [
            {
                "id": "call_test",
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(args)},
            }
        ]
    return ChatCompletion(
        id="test",
        created=0,
        model="test-model",
        object="chat.completion",
        choices=[
            {
                "index": 0,
                "finish_reason": "tool_calls" if name else "stop",
                "message": message,
            }
        ],
    )


class FakeClient:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.requests.append(kwargs)
        item = next(self.responses)
        if isinstance(item, Exception):
            raise item
        return item


def test_tool_result_is_returned_with_matching_call_id(ctx):
    client = FakeClient(
        [
            completion(name="get_node", args={"gid": 900}),
            completion("У gid 900 приоритет 0.93; это гипотеза для проверки."),
        ]
    )
    result = ask("Карточка 900", ctx, [], "test", client=client)
    assert result.mode == "онлайн" and result.calls[0]["result"]["gid"] == 900
    tool = [m for m in client.requests[1]["messages"] if m["role"] == "tool"][0]
    assert tool["tool_call_id"] == "call_test"
    assert json.loads(tool["content"])["priority_score"] == 0.93
    assert client.requests[0]["tool_choice"] == "required"


def test_connection_failure_uses_same_offline_tools(ctx):
    client = FakeClient([APIConnectionError(request=SimpleNamespace())])
    result = ask("Карточка 900", ctx, [], "test", client=client)
    assert result.mode == "офлайн" and "900" in result.text
    assert result.calls[-1]["tool"] == "get_node"


def test_no_key_does_not_construct_sdk_client(ctx, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    result = ask("Топ-5", ctx, [], "test")
    assert result.mode == "офлайн" and len(result.calls[0]["result"]["nodes"]) == 5


def test_tool_free_model_claim_is_not_accepted(ctx):
    client = FakeClient([completion("Этот человек точно виновен")])
    result = ask("Карточка 900", ctx, [], "test", client=client)
    assert result.mode == "офлайн" and "точно виновен" not in result.text


def test_unknown_tool_cannot_execute_code(ctx):
    client = FakeClient(
        [completion(name="exec", args={"code": "print(1)"}), completion("Готово")]
    )
    result = ask("Карточка 900", ctx, [], "test", client=client)
    assert result.mode == "офлайн" and "error" in result.calls[0]["result"]


def test_brief_sends_only_one_node_and_no_chat(ctx):
    client = FakeClient([completion("Справка по gid 900.")])
    result = brief(ctx, 900, "test", client=client)
    assert result.mode == "онлайн"
    messages = client.requests[0]["messages"]
    assert len(messages) == 2 and '"gid": 900' in messages[-1]["content"]
    assert "tools" not in client.requests[0]


def test_tool_loop_budget_falls_back(ctx):
    client = FakeClient([completion(name="get_node", args={"gid": 900})] * 2)
    result = ask("Карточка 900", ctx, [], "test", max_steps=2, client=client)
    assert len(client.requests) == 2 and result.mode == "офлайн"


def test_legacy_token_parameter_retry(ctx):
    from httpx2 import Request, Response

    response = Response(
        400, request=Request("POST", "https://api.openai.com/v1/chat/completions")
    )
    error = BadRequestError(
        "Unsupported parameter",
        response=response,
        body={"error": {"param": "max_completion_tokens"}},
    )
    client = FakeClient(
        [
            error,
            completion(name="get_node", args={"gid": 900}),
            completion("gid 900: приоритет 0.93."),
        ]
    )
    result = ask("Карточка 900", ctx, [], "test", client=client)
    assert result.mode == "онлайн"
    assert (
        "max_tokens" in client.requests[1]
        and "max_completion_tokens" not in client.requests[1]
    )


def test_nvidia_uses_compatible_tools_and_token_parameter(ctx, monkeypatch):
    monkeypatch.setenv('MONEYGRAPH_LLM_PROVIDER', 'nvidia')
    client = FakeClient([completion(name='get_node', args={'gid': 900}), completion('gid 900: гипотеза.')])
    result = ask('Карточка 900', ctx, [], 'test-nvidia', client=client)
    assert result.mode == 'онлайн'
    assert client.requests[0]['tool_choice'] == 'auto'
    assert 'max_tokens' in client.requests[0] and 'max_completion_tokens' not in client.requests[0]
    assert all('strict' not in tool['function'] for tool in client.requests[0]['tools'])
    from assistant.schemas import TOOL_SCHEMAS
    assert all(tool['function']['strict'] for tool in TOOL_SCHEMAS)


def test_nvidia_key_is_only_sent_to_nvidia_endpoint(monkeypatch):
    from assistant.agent import _client
    import openai
    monkeypatch.setenv('MONEYGRAPH_LLM_PROVIDER', 'nvidia')
    monkeypatch.setenv('NVIDIA_API_KEY', 'synthetic-nvidia-key')
    monkeypatch.setenv('OPENAI_API_KEY', 'synthetic-other-key')
    monkeypatch.delenv('MONEYGRAPH_LLM_BASE_URL', raising=False)
    captured = {}
    monkeypatch.setattr(openai, 'OpenAI', lambda **kw: captured.update(kw))
    _client()
    assert captured['base_url'] == 'https://integrate.api.nvidia.com/v1'
    assert captured['api_key'] == 'synthetic-nvidia-key'


def test_nvidia_without_tools_falls_back(ctx, monkeypatch):
    monkeypatch.setenv('MONEYGRAPH_LLM_PROVIDER', 'nvidia')
    client = FakeClient([completion('Выдуманный ответ')])
    result = ask('Карточка 900', ctx, [], 'test', client=client)
    assert result.mode == 'офлайн' and 'Выдуманный' not in result.text
