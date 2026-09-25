from __future__ import annotations

import ctypes
from types import SimpleNamespace

from app.tools.pc_gui import (
    INPUT,
    INPUT_KEYBOARD,
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

        self.input_events: list[
            tuple[int, int, int]
        ] = []

        self.send_input_calls: list[
            tuple[int, int]
        ] = []

        self.send_input_result: int | None = None

        self.GetForegroundWindow = FakeFunction(
            self._get_foreground_window
        )

        self.SendInput = FakeFunction(
            self._send_input
        )

    def _get_foreground_window(
        self,
    ) -> int:
        if self.foreground_window is None:
            return 0

        return self.foreground_window

    def _send_input(
        self,
        count,
        inputs,
        size,
    ) -> int:
        count = int(count)
        size = int(size)

        self.send_input_calls.append(
            (
                count,
                size,
            )
        )

        input_pointer = ctypes.cast(
            inputs,
            ctypes.POINTER(INPUT),
        )

        for index in range(
            count
        ):
            current = input_pointer[
                index
            ]

            self.input_events.append(
                (
                    int(current.type),
                    int(current.ki.wScan),
                    int(current.ki.dwFlags),
                )
            )

        if self.send_input_result is not None:
            return self.send_input_result

        return count


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

    assert user32.input_events == []

    assert user32.send_input_calls == []


# ============================================================================
# TEXT INPUT
# ============================================================================


def test_type_text_sends_unicode_input_events(
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

    assert user32.input_events == [
        (
            INPUT_KEYBOARD,
            ord("a"),
            KEYEVENTF_UNICODE,
        ),
        (
            INPUT_KEYBOARD,
            ord("a"),
            KEYEVENTF_UNICODE
            | KEYEVENTF_KEYUP,
        ),
        (
            INPUT_KEYBOARD,
            ord("b"),
            KEYEVENTF_UNICODE,
        ),
        (
            INPUT_KEYBOARD,
            ord("b"),
            KEYEVENTF_UNICODE
            | KEYEVENTF_KEYUP,
        ),
        (
            INPUT_KEYBOARD,
            ord("c"),
            KEYEVENTF_UNICODE,
        ),
        (
            INPUT_KEYBOARD,
            ord("c"),
            KEYEVENTF_UNICODE
            | KEYEVENTF_KEYUP,
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
        for event in user32.input_events
        if event[1] == ord("\n")
    ]

    assert newline_events == [
        (
            INPUT_KEYBOARD,
            ord("\n"),
            KEYEVENTF_UNICODE,
        ),
        (
            INPUT_KEYBOARD,
            ord("\n"),
            KEYEVENTF_UNICODE
            | KEYEVENTF_KEYUP,
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
        for event in user32.input_events
        if not (
            event[2]
            & KEYEVENTF_KEYUP
        )
    ]

    assert actual_scan_codes == (
        expected_code_units
    )


def test_type_text_supports_euro_symbol(
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
            "text": "€",
        }
    )

    assert result.success is True

    assert [
        event[1]
        for event in user32.input_events
        if not (
            event[2]
            & KEYEVENTF_KEYUP
        )
    ] == [
        0x20AC,
    ]


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
        for event in user32.input_events
        if not (
            event[2]
            & KEYEVENTF_KEYUP
        )
    ]

    assert actual_code_units == (
        expected_code_units
    )

    assert actual_code_units == [
        0x0041,
        0xD83D,
        0xDE00,
        0x0042,
    ]


def test_type_text_supports_mixed_unicode(
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
            "text": "àèéìòù € 😀",
        }
    )

    assert result.success is True
    assert result.output is not None

    encoded = "àèéìòù € 😀".encode(
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
        for event in user32.input_events
        if not (
            event[2]
            & KEYEVENTF_KEYUP
        )
    ]

    assert actual_code_units == (
        expected_code_units
    )

    assert result.output[
        "characters"
    ] == len(
        expected_code_units
    )


# ============================================================================
# SENDINPUT
# ============================================================================


def test_type_text_reports_send_input_partial_failure(
    monkeypatch,
):
    tool = TypeTextTool(
        interval_seconds=0,
    )

    user32 = FakeUser32()

    user32.send_input_result = 1

    install_fake_windows(
        monkeypatch,
        user32,
    )

    result = tool.execute(
        {
            "text": "a",
        }
    )

    assert result.success is False
    assert result.error is not None

    assert "sendinput" in (
        result.error.lower()
    )

    assert "1/2" in result.error


def test_type_text_records_send_input_size(
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
            "text": "a",
        }
    )

    assert result.success is True

    assert user32.send_input_calls == [
        (
            2,
            ctypes.sizeof(INPUT),
        )
    ]


# ============================================================================
# INTERVAL
# ============================================================================


def test_type_text_applies_interval_between_code_units(
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


def test_type_text_handles_send_input_failure(
    monkeypatch,
):
    tool = TypeTextTool(
        interval_seconds=0,
    )

    user32 = FakeUser32()

    def fail_send_input(
        count,
        inputs,
        size,
    ) -> int:
        raise OSError(
            "Errore SendInput simulato"
        )

    user32.SendInput = FakeFunction(
        fail_send_input
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

    assert "errore sendinput simulato" in (
        result.error.lower()
    )