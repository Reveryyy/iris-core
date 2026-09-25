from __future__ import annotations

import ctypes

from app.tools.permissions import Permission
from app.tools.pc_window import FocusWindowTool


class FakeWindowFunction:
    def __init__(self, callback=None):
        self.callback = callback

    def __call__(self, *args):
        if self.callback is None:
            return 0

        return self.callback(*args)


class FakeUser32:
    def __init__(self):
        self.visible_windows = [1, 2, 3]

        self.GetForegroundWindow = FakeWindowFunction(
            lambda: 1
        )

        self.GetWindowThreadProcessId = FakeWindowFunction(
            lambda hwnd, process_id: 100
        )

        self.SetForegroundWindow = FakeWindowFunction(
            lambda hwnd: True
        )

        self.BringWindowToTop = FakeWindowFunction(
            lambda hwnd: True
        )

        self.ShowWindow = FakeWindowFunction(
            lambda hwnd, command: True
        )

        self.IsWindow = FakeWindowFunction(
            lambda hwnd: True
        )

        self.IsWindowVisible = FakeWindowFunction(
            lambda hwnd: True
        )

        self.IsIconic = FakeWindowFunction(
            lambda hwnd: False
        )

        self.AttachThreadInput = FakeWindowFunction(
            lambda current, target, attach: True
        )

        self.EnumWindows = FakeWindowFunction(
            self._enum_windows
        )

    def _enum_windows(self, callback, lparam):
        for hwnd in self.visible_windows:
            if not callback(hwnd, lparam):
                break

        return True


class FakeKernel32:
    def __init__(self):
        self.GetCurrentThreadId = FakeWindowFunction(
            lambda: 200
        )


def test_focus_window_definition_requires_gui_permission():
    tool = FocusWindowTool()

    definition = tool.definition

    assert definition.name == "focus_window"
    assert definition.risk_level == "medium"
    assert Permission.GUI.value in definition.permissions

    assert "title" in definition.input_schema[
        "properties"
    ]

    assert definition.input_schema[
        "required"
    ] == ["title"]


def test_focus_window_rejects_missing_title():
    tool = FocusWindowTool()

    result = tool.execute({})

    assert result.success is False
    assert result.error is not None

    assert "titolo" in result.error.lower()


def test_focus_window_rejects_non_string_title():
    tool = FocusWindowTool()

    result = tool.execute(
        {
            "title": 123,
        }
    )

    assert result.success is False
    assert result.error is not None


def test_focus_window_rejects_empty_title():
    tool = FocusWindowTool()

    result = tool.execute(
        {
            "title": "   ",
        }
    )

    assert result.success is False
    assert result.error is not None


def test_focus_window_reports_non_windows_environment(monkeypatch):
    tool = FocusWindowTool()

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

    assert (
        "solo su windows"
        in result.error.lower()
    )


def test_focus_window_normalizes_accents_and_whitespace():
    assert (
        FocusWindowTool._normalize_text(
            "  Finestra   dell'Èditòr  "
        )
        == "finestra dell'editor"
    )


def test_score_window_match_prefers_exact_title():
    result = FocusWindowTool._score_window_match(
        query="notepad",
        title="notepad",
        process="notepad.exe",
        window_class="notepad",
    )

    assert result == (
        0,
        "title_exact",
    )


def test_score_window_match_accepts_partial_title():
    result = FocusWindowTool._score_window_match(
        query="notepad",
        title="notepad - documento",
        process="notepad.exe",
        window_class="notepad",
    )

    assert result == (
        1,
        "title",
    )


def test_score_window_match_can_use_process_name():
    result = FocusWindowTool._score_window_match(
        query="chrome",
        title="Google",
        process="chrome",
        window_class="Chrome_WidgetWin_1",
    )

    assert result == (
        2,
        "process_exact",
    )


def test_score_window_match_can_use_window_class():
    result = FocusWindowTool._score_window_match(
        query="chrome_widgetwin_1",
        title="Google",
        process="chrome",
        window_class="chrome_widgetwin_1",
    )

    assert result == (
        4,
        "class_exact",
    )


def test_score_window_match_returns_none_when_unrelated():
    result = FocusWindowTool._score_window_match(
        query="discord",
        title="Notepad",
        process="notepad",
        window_class="Notepad",
    )

    assert result is None


def test_find_best_window_prefers_exact_title_match():
    tool = FocusWindowTool()

    user32 = FakeUser32()
    kernel32 = FakeKernel32()

    titles = {
        1: "Google Chrome",
        2: "Notepad",
        3: "Notepad - Documento",
    }

    processes = {
        1: "chrome.exe",
        2: "notepad.exe",
        3: "notepad.exe",
    }

    classes = {
        1: "Chrome_WidgetWin_1",
        2: "Notepad",
        3: "Notepad",
    }

    tool._get_window_title = (
        lambda _user32, hwnd: titles[hwnd]
    )

    tool._get_window_class = (
        lambda _user32, hwnd: classes[hwnd]
    )

    tool._get_process_name = (
        lambda _kernel32, _user32, hwnd: processes[hwnd]
    )

    result = tool._find_best_window(
        user32=user32,
        kernel32=kernel32,
        query="notepad",
    )

    assert result is not None
    assert result["hwnd"] == 2
    assert result["title"] == "Notepad"
    assert result["process_name"] == "notepad.exe"
    assert result["matched_by"] == "title_exact"


def test_find_best_window_returns_none_for_unknown_window():
    tool = FocusWindowTool()

    user32 = FakeUser32()
    kernel32 = FakeKernel32()

    tool._get_window_title = (
        lambda _user32, _hwnd: "Notepad"
    )

    tool._get_window_class = (
        lambda _user32, _hwnd: "Notepad"
    )

    tool._get_process_name = (
        lambda _kernel32, _user32, _hwnd: "notepad.exe"
    )

    result = tool._find_best_window(
        user32=user32,
        kernel32=kernel32,
        query="discord",
    )

    assert result is None


def test_focus_window_returns_true_when_already_foreground():
    user32 = FakeUser32()
    kernel32 = FakeKernel32()

    result = FocusWindowTool._focus_window(
        user32=user32,
        kernel32=kernel32,
        hwnd=1,
    )

    assert result is True


def test_focus_window_rejects_invalid_window():
    user32 = FakeUser32()
    kernel32 = FakeKernel32()

    user32.IsWindow = FakeWindowFunction(
        lambda hwnd: False
    )

    result = FocusWindowTool._focus_window(
        user32=user32,
        kernel32=kernel32,
        hwnd=999,
    )

    assert result is False


def test_focus_window_uses_attach_thread_input_fallback():
    user32 = FakeUser32()
    kernel32 = FakeKernel32()

    calls = []

    user32.GetForegroundWindow = FakeWindowFunction(
        lambda: 999
    )

    user32.SetForegroundWindow = FakeWindowFunction(
        lambda hwnd: (
            calls.append(
                (
                    "set_foreground",
                    hwnd,
                )
            )
            or (
                len(
                    [
                        call
                        for call in calls
                        if call[0] == "set_foreground"
                    ]
                )
                > 1
            )
        )
    )

    user32.AttachThreadInput = FakeWindowFunction(
        lambda current, target, attach: (
            calls.append(
                (
                    "attach",
                    current,
                    target,
                    attach,
                )
            )
            or True
        )
    )

    result = FocusWindowTool._focus_window(
        user32=user32,
        kernel32=kernel32,
        hwnd=123,
    )

    assert result is True

    assert (
        "attach",
        200,
        100,
        True,
    ) in calls

    assert (
        "attach",
        200,
        100,
        False,
    ) in calls


def test_verify_foreground_succeeds_when_window_becomes_foreground():
    user32 = FakeUser32()

    values = iter(
        [
            999,
            123,
        ]
    )

    user32.GetForegroundWindow = FakeWindowFunction(
        lambda: next(values)
    )

    original_timeout = (
        FocusWindowTool.FOCUS_VERIFY_TIMEOUT_SECONDS
    )

    original_interval = (
        FocusWindowTool.FOCUS_VERIFY_INTERVAL_SECONDS
    )

    try:
        FocusWindowTool.FOCUS_VERIFY_TIMEOUT_SECONDS = 0.1
        FocusWindowTool.FOCUS_VERIFY_INTERVAL_SECONDS = 0

        result = FocusWindowTool._verify_foreground(
            user32=user32,
            hwnd=123,
        )

    finally:
        FocusWindowTool.FOCUS_VERIFY_TIMEOUT_SECONDS = (
            original_timeout
        )

        FocusWindowTool.FOCUS_VERIFY_INTERVAL_SECONDS = (
            original_interval
        )

    assert result is True