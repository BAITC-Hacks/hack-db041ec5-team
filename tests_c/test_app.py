from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "app.py"


def test_app_empty_demo_search_card_and_assistant(monkeypatch, tmp_path):
    monkeypatch.setenv("MONEYGRAPH_OUTPUT_DIR", str(tmp_path))
    monkeypatch.setenv("MONEYGRAPH_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MONEYGRAPH_DEMO", "0")
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    assert not app.exception and len(app.tabs) == 8
    app.toggle(key="demo_mode").set_value(True).run()
    assert not app.exception
    app.text_input(key="gid_query").set_value("900").run()
    assert not app.exception and any("gid 900" in x.value for x in app.markdown)
    assert len(app.chat_input) == 1
    app.button(key="graph_brief_900").click().run()
    assert not app.exception and app.session_state["briefs"]
    app.chat_input[0].set_value("Карточка 900").run()
    assert not app.exception and app.session_state["chat_history"][-1]["mode"] == "офлайн"
    app.text_input(key="gid_query").set_value("999999").run()
    assert any("Узел не найден" in w.value for w in app.warning)
    app.text_input(key="gid_query").set_value("abc").run()
    assert any("целочисленный" in w.value for w in app.warning)
    app.toggle(key="demo_mode").set_value(False).run()
    assert not app.exception
