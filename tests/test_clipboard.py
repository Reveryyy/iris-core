from __future__ import annotations

import ctypes
from ctypes import wintypes
from types import SimpleNamespace
from typing import Any

import pytest

from app.tools.permissions import Permission
from app.tools.pc_clipboard import (
    CF_UNICODETEXT,
    GMEM_MOVEABLE,
    GMEM_ZEROINIT,
    GetClipboardTool,
    SetClipboardTool,
)


class FakeClipboardState:
    def __init__(self) -> None:
        self.text = ""
        self.has_unicode = False

        self.open_calls = 0
        self.close_calls = 0
        self.empty_calls = 0
        self.get_data_calls = 0
        self.lock_calls = 0
        self.unlock_calls = 0
        self.alloc_calls = 0
        self.free_calls = 0
        self.set_data_calls = 0

        self.open_success = True
        self.format_available = True
        self.get_data_success = True
        self.lock_success = True
        self.alloc_success = True
        self.empty_success = True
        self.set_data_success = True

        self.allocations: dict[int, tuple[Any, int]] = {}

        self._clipboard_buffer: Any | None = None

    def set_clipboard_text(self, text: str) -> None:
        self.text = text
        self.has_unicode = True
        self._clipboard_buffer = ctypes.create_unicode_buffer(text)

    def clipboard_pointer(self) -> int | None:
        if self._clipboard_buffer is None:
            return None

        return ctypes.addressof(self._clipboard_buffer)


class FakeUser32:
    def __init__(self, state: FakeClipboardState) -> None:
        self.state = state

    def OpenClipboard(self, _owner) -> int:
        self.state.open_calls += 1
        return int(self.state.open_success)

    def CloseClipboard(self) -> int:
        self.state.close_calls += 1
        return 1

    def IsClipboardFormatAvailable(self, format_id: int) -> int:
        if format_id != CF_UNICODETEXT:
            return 0

        return int(self.state.format_available)

    def GetClipboardData(self, format_id: int):
        self.state.get_data_calls += 1

        if format_id != CF_UNICODETEXT:
            return 0

        if not self.state.get_data_success:
            return 0

        return self.state.clipboard_pointer()

    def EmptyClipboard(self) -> int:
        self.state.empty_calls += 1

        if not self.state.empty_success:
            return 0

        self.state.text = ""
        self.state.has_unicode = False
        self.state._clipboard_buffer = None

        return 1

    def SetClipboardData(self, format_id: int, handle):
        self.state.set_data_calls += 1

        if format_id != CF_UNICODETEXT:
            return 0

        if not self.state.set_data_success:
            return 0

        numeric_handle = int(handle)

        allocation = self.state.allocations.get(numeric_handle)

        if allocation is None:
            return 0

        buffer, size = allocation

        raw_data = ctypes.string_at(
            ctypes.addressof(buffer),
            size,
        )

        decoded_text = raw_data.decode(
            "utf-16-le",
            errors="strict",
        )

        decoded_text = decoded_text.split(
            "\x00",
            1,
        )[0]

        self.state.text = decoded_text
        self.state.has_unicode = True

        self.state._clipboard_buffer = ctypes.create_unicode_buffer(
            decoded_text
        )

        # SetClipboardData trasferisce la proprietà della memoria
        # alla clipboard. Il chiamante non deve più liberarla.
        self.state.allocations.pop(
            numeric_handle,
            None,
        )

        return handle


class FakeKernel32:
    def __init__(self, state: FakeClipboardState) -> None:
        self.state = state

    def GlobalLock(self, handle):
        self.state.lock_calls += 1

        if not self.state.lock_success:
            return 0

        return handle

    def GlobalUnlock(self, _handle) -> int:
        self.state.unlock_calls += 1
        return 1

    def GlobalAlloc(self, _flags, size: int):
        self.state.alloc_calls += 1

        if not self.state.alloc_success:
            return 0

        buffer = ctypes.create_string_buffer(
            size,
        )

        handle = ctypes.addressof(
            buffer,
        )

        self.state.allocations[handle] = (
            buffer,
            size,
        )

        return handle

    def GlobalFree(self, handle):
        self.state.free_calls += 1

        numeric_handle = int(handle)

        self.state.allocations.pop(
            numeric_handle,
            None,
        )

        return 0


def install_fake_windows(
    monkeypatch: pytest.MonkeyPatch,
    state: FakeClipboardState,
) -> None:
    fake_user32 = FakeUser32(
        state,
    )

    fake_kernel32 = FakeKernel32(
        state,
    )

    fake_windll = SimpleNamespace(
        user32=fake_user32,
        kernel32=fake_kernel32,
    )

    monkeypatch.setattr(
        ctypes,
        "windll",
        fake_windll,
        raising=False,
    )


def remove_windows_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delattr(
        ctypes,
        "windll",
        raising=False,
    )


def test_get_clipboard_definition() -> None:
    tool = GetClipboardTool()

    definition = tool.definition

    assert definition.name == "get_clipboard"

    assert (
        "appunti" in definition.description.lower()
        or "clipboard" in definition.description.lower()
    )

    assert definition.input_schema["type"] == "object"

    assert definition.input_schema["additionalProperties"] is False

    assert definition.permissions == frozenset(
        {
            Permission.READ.value,
        }
    )


def test_get_clipboard_rejects_non_dict_arguments() -> None:
    tool = GetClipboardTool()

    result = tool.execute(
        None,  # type: ignore[arg-type]
    )

    assert result.success is False
    assert "dizionario" in result.error.lower()


def test_get_clipboard_rejects_arguments() -> None:
    tool = GetClipboardTool()

    result = tool.execute(
        {
            "unexpected": True,
        }
    )

    assert result.success is False
    assert "non accetta argomenti" in result.error.lower()


def test_get_clipboard_requires_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    remove_windows_api(
        monkeypatch,
    )

    tool = GetClipboardTool()

    result = tool.execute(
        {}
    )

    assert result.success is False
    assert "solo su windows" in result.error.lower()


def test_get_clipboard_fails_when_open_clipboard_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = FakeClipboardState()
    state.open_success = False

    install_fake_windows(
        monkeypatch,
        state,
    )

    tool = GetClipboardTool()

    result = tool.execute(
        {}
    )

    assert result.success is False
    assert "aprire gli appunti" in result.error.lower()

    assert state.open_calls == 1
    assert state.close_calls == 0


def test_get_clipboard_fails_when_unicode_format_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = FakeClipboardState()
    state.format_available = False

    install_fake_windows(
        monkeypatch,
        state,
    )

    tool = GetClipboardTool()

    result = tool.execute(
        {}
    )

    assert result.success is False
    assert "testo unicode" in result.error.lower()

    assert state.open_calls == 1
    assert state.close_calls == 1
    assert state.get_data_calls == 0


def test_get_clipboard_fails_when_get_data_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = FakeClipboardState()
    state.set_clipboard_text(
        "Ciao"
    )
    state.get_data_success = False

    install_fake_windows(
        monkeypatch,
        state,
    )

    tool = GetClipboardTool()

    result = tool.execute(
        {}
    )

    assert result.success is False
    assert "recuperare" in result.error.lower()

    assert state.open_calls == 1
    assert state.close_calls == 1
    assert state.get_data_calls == 1


def test_get_clipboard_fails_when_global_lock_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = FakeClipboardState()
    state.set_clipboard_text(
        "Ciao"
    )
    state.lock_success = False

    install_fake_windows(
        monkeypatch,
        state,
    )

    tool = GetClipboardTool()

    result = tool.execute(
        {}
    )

    assert result.success is False
    assert "accedere al testo" in result.error.lower()

    assert state.open_calls == 1
    assert state.close_calls == 1
    assert state.lock_calls == 1
    assert state.unlock_calls == 0


def test_get_clipboard_reads_unicode_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = FakeClipboardState()

    text = "Ciao àèé ìòù € 😀"

    state.set_clipboard_text(
        text
    )

    install_fake_windows(
        monkeypatch,
        state,
    )

    tool = GetClipboardTool()

    result = tool.execute(
        {}
    )

    assert result.success is True

    assert result.output == {
        "text": text,
        "characters": len(text),
    }

    assert state.open_calls == 1
    assert state.close_calls == 1
    assert state.get_data_calls == 1
    assert state.lock_calls == 1
    assert state.unlock_calls == 1


def test_get_clipboard_closes_clipboard_after_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = FakeClipboardState()

    state.set_clipboard_text(
        "test"
    )

    install_fake_windows(
        monkeypatch,
        state,
    )

    tool = GetClipboardTool()

    result = tool.execute(
        {}
    )

    assert result.success is True
    assert state.close_calls == 1


def test_set_clipboard_definition() -> None:
    tool = SetClipboardTool()

    definition = tool.definition

    assert definition.name == "set_clipboard"

    assert (
        "scrive" in definition.description.lower()
        or "clipboard" in definition.description.lower()
    )

    assert definition.input_schema["type"] == "object"

    assert (
        definition.input_schema["additionalProperties"]
        is False
    )

    assert definition.input_schema["required"] == [
        "text",
    ]

    assert definition.permissions == frozenset(
        {
            Permission.WRITE.value,
        }
    )


def test_set_clipboard_rejects_non_dict_arguments() -> None:
    tool = SetClipboardTool()

    result = tool.execute(
        None,  # type: ignore[arg-type]
    )

    assert result.success is False
    assert "dizionario" in result.error.lower()


def test_set_clipboard_rejects_missing_text() -> None:
    tool = SetClipboardTool()

    result = tool.execute(
        {}
    )

    assert result.success is False
    assert "stringa" in result.error.lower()


def test_set_clipboard_rejects_non_string_text() -> None:
    tool = SetClipboardTool()

    result = tool.execute(
        {
            "text": 123,
        }
    )

    assert result.success is False
    assert "stringa" in result.error.lower()


def test_set_clipboard_rejects_empty_text() -> None:
    tool = SetClipboardTool()

    result = tool.execute(
        {
            "text": "",
        }
    )

    assert result.success is False
    assert "vuoto" in result.error.lower()


def test_set_clipboard_rejects_text_over_limit() -> None:
    tool = SetClipboardTool(
        max_characters=5,
    )

    result = tool.execute(
        {
            "text": "123456",
        }
    )

    assert result.success is False
    assert "limite" in result.error.lower()


def test_set_clipboard_requires_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    remove_windows_api(
        monkeypatch,
    )

    tool = SetClipboardTool()

    result = tool.execute(
        {
            "text": "Ciao",
        }
    )

    assert result.success is False
    assert "solo su windows" in result.error.lower()


def test_set_clipboard_fails_when_open_clipboard_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = FakeClipboardState()
    state.open_success = False

    install_fake_windows(
        monkeypatch,
        state,
    )

    tool = SetClipboardTool()

    result = tool.execute(
        {
            "text": "Ciao",
        }
    )

    assert result.success is False
    assert "aprire gli appunti" in result.error.lower()

    assert state.open_calls == 1
    assert state.close_calls == 0
    assert state.alloc_calls == 0


def test_set_clipboard_fails_when_memory_allocation_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = FakeClipboardState()
    state.alloc_success = False

    install_fake_windows(
        monkeypatch,
        state,
    )

    tool = SetClipboardTool()

    result = tool.execute(
        {
            "text": "Ciao",
        }
    )

    assert result.success is False
    assert "allocare la memoria" in result.error.lower()

    assert state.open_calls == 1
    assert state.close_calls == 1
    assert state.alloc_calls == 1
    assert state.free_calls == 0


def test_set_clipboard_fails_when_global_lock_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = FakeClipboardState()
    state.lock_success = False

    install_fake_windows(
        monkeypatch,
        state,
    )

    tool = SetClipboardTool()

    result = tool.execute(
        {
            "text": "Ciao",
        }
    )

    assert result.success is False
    assert "accedere alla memoria" in result.error.lower()

    assert state.open_calls == 1
    assert state.close_calls == 1
    assert state.alloc_calls == 1
    assert state.lock_calls == 1
    assert state.free_calls == 1

    assert state.allocations == {}


def test_set_clipboard_fails_when_empty_clipboard_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = FakeClipboardState()
    state.empty_success = False

    install_fake_windows(
        monkeypatch,
        state,
    )

    tool = SetClipboardTool()

    result = tool.execute(
        {
            "text": "Ciao",
        }
    )

    assert result.success is False
    assert "svuotare gli appunti" in result.error.lower()

    assert state.open_calls == 1
    assert state.close_calls == 1
    assert state.empty_calls == 1
    assert state.free_calls == 1

    assert state.allocations == {}


def test_set_clipboard_fails_when_set_data_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = FakeClipboardState()
    state.set_data_success = False

    install_fake_windows(
        monkeypatch,
        state,
    )

    tool = SetClipboardTool()

    result = tool.execute(
        {
            "text": "Ciao",
        }
    )

    assert result.success is False
    assert "salvare il testo" in result.error.lower()

    assert state.open_calls == 1
    assert state.close_calls == 1
    assert state.empty_calls == 1
    assert state.set_data_calls == 1

    assert state.free_calls == 1
    assert state.allocations == {}


def test_set_clipboard_writes_unicode_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = FakeClipboardState()

    install_fake_windows(
        monkeypatch,
        state,
    )

    tool = SetClipboardTool()

    text = "Ciao àèé € 😀"

    result = tool.execute(
        {
            "text": text,
        }
    )

    assert result.success is True

    assert result.output == {
        "characters": len(text),
    }

    assert state.text == text

    assert state.has_unicode is True

    assert state.open_calls == 1

    assert state.empty_calls == 1

    assert state.set_data_calls == 1

    assert state.close_calls == 1

    assert state.alloc_calls == 1

    assert state.lock_calls == 1

    assert state.unlock_calls == 1

    # La ownership della memoria passa a SetClipboardData.
    # Quindi GlobalFree non deve essere chiamato e
    # l'allocazione deve essere rimossa dal fake.
    assert state.free_calls == 0

    assert state.allocations == {}


def test_set_clipboard_handles_ascii_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = FakeClipboardState()

    install_fake_windows(
        monkeypatch,
        state,
    )

    tool = SetClipboardTool()

    text = "Hello from clipboard"

    result = tool.execute(
        {
            "text": text,
        }
    )

    assert result.success is True
    assert result.output == {
        "characters": len(text),
    }

    assert state.text == text
    assert state.has_unicode is True

    assert state.allocations == {}


def test_set_clipboard_handles_multiline_unicode_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = FakeClipboardState()

    install_fake_windows(
        monkeypatch,
        state,
    )

    tool = SetClipboardTool()

    text = (
        "Prima riga\n"
        "Seconda riga\n"
        "€ àèé ìòù 😀"
    )

    result = tool.execute(
        {
            "text": text,
        }
    )

    assert result.success is True

    assert state.text == text

    assert result.output == {
        "characters": len(text),
    }

    assert state.allocations == {}


def test_set_clipboard_custom_character_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = FakeClipboardState()

    install_fake_windows(
        monkeypatch,
        state,
    )

    tool = SetClipboardTool(
        max_characters=10,
    )

    result = tool.execute(
        {
            "text": "1234567890",
        }
    )

    assert result.success is True
    assert state.text == "1234567890"
    assert state.allocations == {}


def test_set_clipboard_rejects_text_above_custom_character_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = FakeClipboardState()

    install_fake_windows(
        monkeypatch,
        state,
    )

    tool = SetClipboardTool(
        max_characters=10,
    )

    result = tool.execute(
        {
            "text": "12345678901",
        }
    )

    assert result.success is False
    assert "limite" in result.error.lower()

    assert state.open_calls == 0
    assert state.allocations == {}