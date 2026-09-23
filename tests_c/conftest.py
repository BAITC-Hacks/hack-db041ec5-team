"""Изолированные тесты C; не меняют тесты участников A/B."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture
def ctx():
    from ui.demo import make_demo

    return make_demo()
