from __future__ import annotations

import ctypes
from types import SimpleNamespace

from app.tools.pc_gui import (
    KEYEVENTF_KEYUP,
    KEYEVENTF_UNICODE,
    TypeTextTool,
)
from app.tools.permissions import Permission


class FakeFunction:
    def __init__(
        self,
        implementation,
    ) -> None:
        self.implementation = implementation
        self.argtypes = None
        self.restype = None

    def __call__(
        self,
        *args,
    ):
        return self.implementation(
            *args
        )


class FakeUser32:
    def __init__(
        self,
        foreground_window: int | None = 100,
    ) -> None:
        self.foreground_window = foreground_window

        self.key_events: list[
            tuple[int, int, int, int]
        ] = []

        self.GetForegroundWindow = FakeFunction(
            self._get_foreground_window
        )

        self.keybd_event = FakeFunction(
            self._keybd_event
        )

    def _get_foreground_window(self) -> int:
        if self.foreground_window is None:
            return 0

        return self.foreground_window

    def _keybd_event(
        self,
        virtual_key,
        scan_code,
        flags,
        extra_info,
    ) -> None:
        self.key_events.append(
            (
                int(virtual_key),
                int(scan_code),
                int(flags),
                int(extra_info),
            )
        )


def install_fake_windows(
    monkeypatch,
    user32: FakeUser32,
) -> None:
    monkeypatch.setattr(
        ctypes,
        "windll",
        SimpleNamespace(
            user32=user32,
        ),
        raising=False,
    )


# ============================================================================
# DEFINITION
# ============================================================================


def test_type_text_definition_requires_gui_permission():
    tool = TypeTextTool(
        max_characters=100,
        interval_seconds=0,
    )

    definition = tool.definition

    assert definition.name == "type_text"

    assert definition.risk_level == "medium"

    assert Permission.GUI.value in (
        definition.permissions
    )

    assert "text" in definition.input_schema[
        "properties"
    ]

    assert definition.input_schema[
        "required"
    ] == ["text"]

    assert definition.input_schema[
        "additionalProperties"
    ] is False


# ============================================================================
# INPUT VALIDATION
# ============================================================================


def test_type_text_rejects_missing_text():
    tool = TypeTextTool(
        interval_seconds=0,
    )

    result = tool.execute({})

    assert result.success is False
    assert result.error is not None

    assert "testo" in (
        result.error.lower()
    )


def test_type_text_rejects_non_string_text():
    tool = TypeTextTool(
        interval_seconds=0,
    )

    result = tool.execute(
        {
            "text": 123,
        }
    )

    assert result.success is False
    assert result.error is not None


def test_type_text_rejects_empty_text():
    tool = TypeTextTool(
        interval_seconds=0,
    )

    result = tool.execute(
        {
            "text": "",
        }
    )

    assert result.success is False
    assert result.error is not None

    assert "vuoto" in (
        result.error.lower()
    )


def test_type_text_rejects_text_over_limit():
    tool = TypeTextTool(
        max_characters=5,
        interval_seconds=0,
    )

    result = tool.execute(
        {
            "text": "123456",
        }
    )

    assert result.success is False
    assert result.error is not None

    assert "supera il limite" in (
        result.error.lower()
    )


def test_type_text_accepts_text_at_exact_limit(
    monkeypatch,
):
    tool = TypeTextTool(
        max_characters=5,
        interval_seconds=0,
    )

    user32 = FakeUser32()

    install_fake_windows(
        monkeypatch,
        user32,
    )

    result = tool.execute(
        {
            "text": "12345",
        }
    )

    assert result.success is True

    assert result.output is not None

    assert result.output[
        "characters"
    ] == 5


# ============================================================================
# WINDOWS / FOREGROUND
# ============================================================================


def test_type_text_reports_non_windows_environment(
    monkeypatch,
):
    tool = TypeTextTool(
        interval_seconds=0,
    )

    monkeypatch.delattr(
        ctypes,
        "windll",
        raising=False,
    )

    result = tool.execute(
        {
            "text": "ciao",
        }
    )

    assert result.success is False
    assert result.error is not None

    assert "solo su windows" in (
        result.error.lower()
    )


def test_type_text_reports_missing_foreground_window(
    monkeypatch,
):
    tool = TypeTextTool(
        interval_seconds=0,
    )

    user32 = FakeUser32(
        foreground_window=None,
    )

    install_fake_windows(
        monkeypatch,
        user32,
    )

    result = tool.execute(
        {
            "text": "ciao",
        }
    )

    assert result.success is False
    assert result.error is not None

    assert "primo piano" in (
        result.error.lower()
    )

    assert user32.key_events == []


# ============================================================================
# TEXT INPUT
# ============================================================================


def test_type_text_sends_unicode_key_events(
    monkeypatch,
):
    tool = TypeTextTool(
        interval_seconds=0,
    )

    user32 = FakeUser32(
        foreground_window=1234,
    )

    install_fake_windows(
        monkeypatch,
        user32,
    )

    result = tool.execute(
        {
            "text": "abc",
        }
    )

    assert result.success is True
    assert result.output is not None

    assert result.output[
        "window_handle"
    ] == 1234

    assert result.output[
        "characters"
    ] == 3

    assert user32.key_events == [
        (
            0,
            ord("a"),
            KEYEVENTF_UNICODE,
            0,
        ),
        (
            0,
            ord("a"),
            KEYEVENTF_UNICODE | KEYEVENTF_KEYUP,
            0,
        ),
        (
            0,
            ord("b"),
            KEYEVENTF_UNICODE,
            0,
        ),
        (
            0,
            ord("b"),
            KEYEVENTF_UNICODE | KEYEVENTF_KEYUP,
            0,
        ),
        (
            0,
            ord("c"),
            KEYEVENTF_UNICODE,
            0,
        ),
        (
            0,
            ord("c"),
            KEYEVENTF_UNICODE | KEYEVENTF_KEYUP,
            0,
        ),
    ]


def test_type_text_supports_spaces_and_newlines(
    monkeypatch,
):
    tool = TypeTextTool(
        interval_seconds=0,
    )

    user32 = FakeUser32()

    install_fake_windows(
        monkeypatch,
        user32,
    )

    result = tool.execute(
        {
            "text": "ciao\nmondo",
        }
    )

    assert result.success is True
    assert result.output is not None

    assert result.output[
        "characters"
    ] == 10

    newline_events = [
        event
        for event in user32.key_events
        if event[1] == ord("\n")
    ]

    assert newline_events == [
        (
            0,
            ord("\n"),
            KEYEVENTF_UNICODE,
            0,
        ),
        (
            0,
            ord("\n"),
            KEYEVENTF_UNICODE | KEYEVENTF_KEYUP,
            0,
        ),
    ]


def test_type_text_supports_unicode_characters(
    monkeypatch,
):
    tool = TypeTextTool(
        interval_seconds=0,
    )

    user32 = FakeUser32()

    install_fake_windows(
        monkeypatch,
        user32,
    )

    result = tool.execute(
        {
            "text": "Ciao àéè",
        }
    )

    assert result.success is True
    assert result.output is not None

    assert result.output[
        "characters"
    ] == 8

    expected_code_units = [
        ord("C"),
        ord("i"),
        ord("a"),
        ord("o"),
        ord(" "),
        ord("à"),
        ord("é"),
        ord("è"),
    ]

    actual_scan_codes = [
        event[1]
        for event in user32.key_events
        if not (
            event[2]
            & KEYEVENTF_KEYUP
        )
    ]

    assert actual_scan_codes == (
        expected_code_units
    )


def test_type_text_supports_emoji_surrogate_pair(
    monkeypatch,
):
    tool = TypeTextTool(
        interval_seconds=0,
    )

    user32 = FakeUser32()

    install_fake_windows(
        monkeypatch,
        user32,
    )

    result = tool.execute(
        {
            "text": "A😀B",
        }
    )

    assert result.success is True
    assert result.output is not None

    assert result.output[
        "characters"
    ] == 4

    encoded = "A😀B".encode(
        "utf-16-le"
    )

    expected_code_units = [
        int.from_bytes(
            encoded[index:index + 2],
            byteorder="little",
        )
        for index in range(
            0,
            len(encoded),
            2,
        )
    ]

    actual_code_units = [
        event[1]
        for event in user32.key_events
        if not (
            event[2]
            & KEYEVENTF_KEYUP
        )
    ]

    assert actual_code_units == (
        expected_code_units
    )


# ============================================================================
# INTERVAL
# ============================================================================


def test_type_text_applies_interval_between_characters(
    monkeypatch,
):
    tool = TypeTextTool(
        interval_seconds=0.123,
    )

    user32 = FakeUser32()

    install_fake_windows(
        monkeypatch,
        user32,
    )

    sleeps: list[float] = []

    monkeypatch.setattr(
        "app.tools.pc_gui.time.sleep",
        lambda seconds: sleeps.append(
            seconds
        ),
    )

    result = tool.execute(
        {
            "text": "abc",
        }
    )

    assert result.success is True

    assert sleeps == [
        0.123,
        0.123,
        0.123,
    ]


def test_type_text_does_not_sleep_when_interval_is_zero(
    monkeypatch,
):
    tool = TypeTextTool(
        interval_seconds=0,
    )

    user32 = FakeUser32()

    install_fake_windows(
        monkeypatch,
        user32,
    )

    sleeps: list[float] = []

    monkeypatch.setattr(
        "app.tools.pc_gui.time.sleep",
        lambda seconds: sleeps.append(
            seconds
        ),
    )

    result = tool.execute(
        {
            "text": "abc",
        }
    )

    assert result.success is True

    assert sleeps == []


# ============================================================================
# ERROR HANDLING
# ============================================================================


def test_type_text_handles_keybd_event_error(
    monkeypatch,
):
    tool = TypeTextTool(
        interval_seconds=0,
    )

    user32 = FakeUser32()

    def fail_keybd_event(
        virtual_key,
        scan_code,
        flags,
        extra_info,
    ) -> None:
        raise OSError(
            "Errore tastiera simulato"
        )

    user32.keybd_event = FakeFunction(
        fail_keybd_event
    )

    install_fake_windows(
        monkeypatch,
        user32,
    )

    result = tool.execute(
        {
            "text": "ciao",
        }
    )

    assert result.success is False
    assert result.error is not None

    assert "impossibile inviare il testo" in (
        result.error.lower()
    )