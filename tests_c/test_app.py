from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "app.py"


def test_app_empty_demo_search_card_and_offline_chat(monkeypatch, tmp_path):
    monkeypatch.setenv("MONEYGRAPH_OUTPUT_DIR", str(tmp_path))
    monkeypatch.setenv("MONEYGRAPH_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MONEYGRAPH_DEMO", "0")
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    assert not app.exception and len(app.tabs) == 7
    app.toggle(key="demo_mode").set_value(True).run()
    assert not app.exception
    app.text_input(key="gid_query").set_value("900").run()
    assert not app.exception and any("gid 900" in x.value for x in app.markdown)
    app.button(key="graph_brief_900").click().run()
    assert not app.exception and app.session_state["briefs"]

    def unexpected_repeat(*args, **kwargs):
        raise AssertionError("Повторный вызов вместо кэшированной справки")

    monkeypatch.setattr("ui.node_card.brief", unexpected_repeat)
    app.button(key="graph_brief_900").click().run()
    assert not app.exception
    app.text_input(key="gid_query").set_value("999999").run()
    assert any("Узел не найден" in w.value for w in app.warning)
    app.text_input(key="gid_query").set_value("abc").run()
    assert any("целочисленный" in w.value for w in app.warning)
    app.chat_input[0].set_value(
        "Кто собирает деньги с этих пятерых: 101,102,103,104,105?"
    ).run()
    assert not app.exception
    answer = app.session_state["chat_history"][-1]
    assert (
        answer["mode"] == "офлайн" and answer["calls"][0]["tool"] == "common_downstream"
    )
    app.toggle(key="demo_mode").set_value(False).run()
    assert not app.exception and not app.session_state["chat_history"]


