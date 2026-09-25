from __future__ import annotations

import ctypes

from app.tools.pc_ui_interaction import InteractUIElementTool


def test_interact_ui_element_definition() -> None:
    definition = InteractUIElementTool().definition

    assert definition.name == "interact_ui_element"
    assert "window_title" in definition.input_schema["properties"]
    assert "element" in definition.input_schema["properties"]
    assert "action" in definition.input_schema["properties"]
    assert definition.input_schema["required"] == [
        "window_title",
        "element",
        "action",
    ]


def test_interact_ui_element_rejects_invalid_action() -> None:
    result = InteractUIElementTool().execute(
        {
            "window_title": "Notepad",
            "element": "Edit",
            "action": "invented_action",
        }
    )

    assert result.success is False
    assert "non supportata" in result.error.lower()


def test_interact_ui_element_requires_value_for_set_text() -> None:
    result = InteractUIElementTool().execute(
        {
            "window_title": "Notepad",
            "element": "Edit",
            "action": "set_text",
        }
    )

    assert result.success is False
    assert "value" in result.error.lower()


def test_interact_ui_element_requires_windows(monkeypatch) -> None:
    monkeypatch.delattr(
        ctypes,
        "windll",
        raising=False,
    )

    result = InteractUIElementTool().execute(
        {
            "window_title": "Notepad",
            "element": "Edit",
            "action": "focus",
        }
    )

    assert result.success is False
    assert "solo su windows" in result.error.lower()
