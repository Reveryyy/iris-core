from __future__ import annotations

import ctypes
from types import SimpleNamespace

from app.tools.pc_minimize import MinimizeWindowTool
from app.tools.permissions import Permission


class FakeUser32:
    def __init__(
        self,
        windows: dict[int, str],
        visible: dict[int, bool] | None = None,
        show_window_result: bool = True,
    ) -> None:
        self.windows = windows
        self.visible = visible or {
            hwnd: True
            for hwnd in windows
        }
        self.show_window_result = show_window_result
        self.show_window_calls: list[
            tuple[int, int]
        ] = []

        self.GetWindowTextLengthW = (
            self._get_window_text_length
        )
        self.GetWindowTextW = (
            self._get_window_text
        )
        self.IsWindowVisible = (
            self._is_window_visible
        )
        self.EnumWindows = (
            self._enum_windows
        )
        self.ShowWindow = (
            self._show_window
        )

    def _get_window_text_length(
        self,
        hwnd,
    ) -> int:
        return len(
            self.windows.get(
                int(hwnd),
                "",
            )
        )

    def _get_window_text(
        self,
        hwnd,
        buffer,
        length,
    ) -> int:
        value = self.windows.get(
            int(hwnd),
            "",
        )

        buffer.value = value

        return len(value)

    def _is_window_visible(
        self,
        hwnd,
    ) -> bool:
        return self.visible.get(
            int(hwnd),
            False,
        )

    def _enum_windows(
        self,
        callback,
        _lparam,
    ) -> bool:
        for hwnd in self.windows:
            if not callback(
                hwnd,
                0,
            ):
                break

        return True

    def _show_window(
        self,
        hwnd,
        command,
    ) -> bool:
        hwnd = int(hwnd)

        self.show_window_calls.append(
            (
                hwnd,
                int(command),
            )
        )

        if (
            int(command) == 6
            and self.show_window_result
        ):
            self.visible[hwnd] = False

        return self.show_window_result


def test_minimize_window_definition_requires_gui_permission():
    tool = MinimizeWindowTool()

    definition = tool.definition

    assert definition.name == "minimize_window"
    assert definition.risk_level == "medium"
    assert Permission.GUI.value in definition.permissions

    assert "title" in definition.input_schema[
        "properties"
    ]

    assert definition.input_schema[
        "required"
    ] == ["title"]


def test_minimize_window_rejects_missing_title():
    tool = MinimizeWindowTool()

    result = tool.execute({})

    assert result.success is False
    assert result.error is not None
    assert "titolo" in result.error.lower()


def test_minimize_window_rejects_non_string_title():
    tool = MinimizeWindowTool()

    result = tool.execute(
        {
            "title": 123,
        }
    )

    assert result.success is False
    assert result.error is not None


def test_minimize_window_rejects_empty_title():
    tool = MinimizeWindowTool()

    result = tool.execute(
        {
            "title": "   ",
        }
    )

    assert result.success is False
    assert result.error is not None


def test_minimize_window_reports_non_windows_environment(
    monkeypatch,
):
    tool = MinimizeWindowTool()

    monkeypatch.delattr(
        ctypes,
        "windll",
        raising=False,
    )

    result = tool.execute(
        {
            "title": "Notepad",
        }
    )

    assert result.success is False
    assert result.error is not None
    assert "solo su windows" in result.error.lower()


def test_normalize_text_removes_accents_and_normalizes_spaces():
    result = MinimizeWindowTool._normalize_text(
        "  Finestra   dell'Èditòr  "
    )

    assert result == "finestra dell'editor"


def test_build_search_titles_uses_notepad_aliases():
    result = MinimizeWindowTool._build_search_titles(
        "notepad"
    )

    assert result == (
        "notepad",
        "blocco note",
    )


def test_build_search_titles_uses_generic_title_without_alias():
    result = MinimizeWindowTool._build_search_titles(
        "google chrome"
    )

    assert result == (
        "google chrome",
    )


def test_title_matches_exact_and_partial_titles():
    assert MinimizeWindowTool._title_matches(
        "notepad",
        ("notepad",),
    )

    assert MinimizeWindowTool._title_matches(
        "notepad - documento",
        ("notepad",),
    )

    assert not MinimizeWindowTool._title_matches(
        "google chrome",
        ("notepad",),
    )


def test_execute_minimizes_matching_window(
    monkeypatch,
):
    tool = MinimizeWindowTool()

    user32 = FakeUser32(
        {
            100: "Google Chrome",
            200: "Notepad",
            300: "Discord",
        }
    )

    monkeypatch.setattr(
        ctypes,
        "windll",
        SimpleNamespace(
            user32=user32,
        ),
        raising=False,
    )

    result = tool.execute(
        {
            "title": "Notepad",
        }
    )

    assert result.success is True
    assert result.output is not None

    assert result.output[
        "title"
    ] == "Notepad"

    assert result.output[
        "hwnd"
    ] == 200

    assert result.output[
        "state"
    ] == "minimized"

    assert user32.show_window_calls == [
        (
            200,
            6,
        )
    ]

    assert user32.visible[200] is False


def test_execute_supports_notepad_alias():
    tool = MinimizeWindowTool()

    user32 = FakeUser32(
        {
            100: "Google Chrome",
            200: "Notepad",
        }
    )

    # Simula ctypes.windll presente su Windows.
    original_windll = getattr(
        ctypes,
        "windll",
        None,
    )

    try:
        ctypes.windll = SimpleNamespace(
            user32=user32,
        )

        result = tool.execute(
            {
                "title": "blocco note",
            }
        )

    finally:
        if original_windll is None:
            try:
                del ctypes.windll
            except AttributeError:
                pass
        else:
            ctypes.windll = original_windll

    assert result.success is True
    assert result.output is not None
    assert result.output[
        "hwnd"
    ] == 200


def test_execute_reports_missing_window(
    monkeypatch,
):
    tool = MinimizeWindowTool()

    user32 = FakeUser32(
        {
            100: "Google Chrome",
            200: "Discord",
        }
    )

    monkeypatch.setattr(
        ctypes,
        "windll",
        SimpleNamespace(
            user32=user32,
        ),
        raising=False,
    )

    result = tool.execute(
        {
            "title": "Notepad",
        }
    )

    assert result.success is False
    assert result.error is not None

    assert "nessuna finestra visibile trovata" in (
        result.error.lower()
    )


def test_execute_reports_minimize_failure_when_window_stays_visible(
    monkeypatch,
):
    tool = MinimizeWindowTool()

    user32 = FakeUser32(
        {
            200: "Notepad",
        },
        show_window_result=False,
    )

    monkeypatch.setattr(
        ctypes,
        "windll",
        SimpleNamespace(
            user32=user32,
        ),
        raising=False,
    )

    result = tool.execute(
        {
            "title": "Notepad",
        }
    )

    assert result.success is False
    assert result.error is not None

    assert "windows non ha consentito" in (
        result.error.lower()
    )

    assert user32.visible[200] is True