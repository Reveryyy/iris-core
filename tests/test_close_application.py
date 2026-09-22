from __future__ import annotations

import os

import pytest

from app.tools.application_resolver import (
    ResolvedApplication,
)
from app.tools.pc_close import (
    CloseApplicationTool,
)


# ============================================================================
# FAKE RESOLVER
# ============================================================================

class FakeResolver:
    def __init__(
        self,
        application: ResolvedApplication | None,
    ) -> None:
        self.application = application
        self.queries: list[str] = []

    def resolve(
        self,
        query: str,
    ) -> ResolvedApplication | None:
        self.queries.append(
            query
        )

        return self.application


# ============================================================================
# DEFINITION / VALIDATION
# ============================================================================

def test_close_application_definition():

    tool = CloseApplicationTool(
        resolver=FakeResolver(None)
    )

    definition = tool.definition

    assert definition.name == "close_application"

    assert definition.risk_level == "medium"

    assert "name" in definition.input_schema[
        "properties"
    ]

    assert definition.input_schema[
        "required"
    ] == ["name"]


def test_close_application_rejects_missing_name():

    tool = CloseApplicationTool(
        resolver=FakeResolver(None)
    )

    result = tool.execute({})

    assert result.success is False
    assert result.error is not None

    assert "nome" in result.error.lower()


def test_close_application_rejects_non_string_name():

    tool = CloseApplicationTool(
        resolver=FakeResolver(None)
    )

    result = tool.execute(
        {
            "name": 123,
        }
    )

    assert result.success is False
    assert result.error is not None


def test_close_application_rejects_empty_name():

    tool = CloseApplicationTool(
        resolver=FakeResolver(None)
    )

    result = tool.execute(
        {
            "name": "   ",
        }
    )

    assert result.success is False
    assert result.error is not None


def test_close_application_reports_missing_application():

    resolver = FakeResolver(None)

    tool = CloseApplicationTool(
        resolver=resolver
    )

    result = tool.execute(
        {
            "name": "Applicazione inesistente",
        }
    )

    assert result.success is False
    assert result.error is not None

    assert (
        "non riesco a trovare"
        in result.error.lower()
    )

    assert resolver.queries == [
        "Applicazione inesistente"
    ]


# ============================================================================
# NORMALIZATION
# ============================================================================

def test_normalize_text():

    assert (
        CloseApplicationTool._normalize_text(
            "  Windows   Terminal  "
        )
        == "windows terminal"
    )


# ============================================================================
# PROCESS MATCHING
# ============================================================================

def test_expected_process_names():

    application = ResolvedApplication(
        name="Notepad",
        target=r"C:\Windows\System32\notepad.exe",
        source="path",
    )

    names = (
        CloseApplicationTool._expected_process_names(
            application
        )
    )

    assert "notepad" in names


def test_score_application_match_by_process():

    application = ResolvedApplication(
        name="Notepad",
        target=r"C:\Windows\System32\notepad.exe",
        source="path",
    )

    result = (
        CloseApplicationTool._score_application_match(
            query="notepad",
            title="",
            process="notepad",
            window_class="",
            expected_process_names={
                "notepad",
            },
            application=application,
        )
    )

    assert result is not None
    assert result[1] == "process_exact"


def test_score_application_match_by_title():

    application = ResolvedApplication(
        name="Notepad",
        target=r"C:\Windows\System32\notepad.exe",
        source="path",
    )

    result = (
        CloseApplicationTool._score_application_match(
            query="blocco note",
            title="blocco note",
            process="notepad",
            window_class="",
            expected_process_names={
                "notepad",
            },
            application=application,
        )
    )

    assert result is not None
    assert result[1] == "title_exact"


def test_score_application_match_rejects_unrelated_window():

    application = ResolvedApplication(
        name="Notepad",
        target=r"C:\Windows\System32\notepad.exe",
        source="path",
    )

    result = (
        CloseApplicationTool._score_application_match(
            query="notepad",
            title="Google Chrome",
            process="chrome",
            window_class="Chrome_WidgetWin_1",
            expected_process_names={
                "notepad",
            },
            application=application,
        )
    )

    assert result is None


# ============================================================================
# CLOSE / VERIFICATION
# ============================================================================

class FakeUser32:

    def __init__(
        self,
        *,
        valid: bool = True,
        visible: bool = True,
        post_success: bool = True,
    ) -> None:
        self.valid = valid
        self.visible = visible
        self.post_success = post_success
        self.messages: list[
            tuple[
                int,
                int,
                int,
                int,
            ]
        ] = []

    def IsWindow(
        self,
        hwnd,
    ):
        return self.valid

    def IsWindowVisible(
        self,
        hwnd,
    ):
        return self.visible

    def PostMessageW(
        self,
        hwnd,
        message,
        wparam,
        lparam,
    ):
        self.messages.append(
            (
                hwnd,
                message,
                wparam,
                lparam,
            )
        )

        return self.post_success


def test_send_close_posts_wm_close():

    user32 = FakeUser32()

    result = (
        CloseApplicationTool._send_close(
            user32=user32,
            hwnd=1234,
        )
    )

    assert result is True

    assert user32.messages == [
        (
            1234,
            CloseApplicationTool.WM_CLOSE,
            0,
            0,
        )
    ]


def test_send_close_rejects_invalid_window():

    user32 = FakeUser32(
        valid=False
    )

    result = (
        CloseApplicationTool._send_close(
            user32=user32,
            hwnd=1234,
        )
    )

    assert result is False


def test_send_close_reports_post_failure():

    user32 = FakeUser32(
        post_success=False
    )

    result = (
        CloseApplicationTool._send_close(
            user32=user32,
            hwnd=1234,
        )
    )

    assert result is False


def test_verify_closed_when_window_is_destroyed():

    user32 = FakeUser32(
        valid=False
    )

    result = (
        CloseApplicationTool._verify_closed(
            user32=user32,
            hwnd=1234,
        )
    )

    assert result is True


def test_verify_closed_when_window_is_not_visible():

    user32 = FakeUser32(
        valid=True,
        visible=False,
    )

    result = (
        CloseApplicationTool._verify_closed(
            user32=user32,
            hwnd=1234,
        )
    )

    assert result is True


@pytest.mark.skipif(
    os.name != "nt",
    reason="Test disponibile solo su Windows.",
)
def test_close_application_real_validation_path():

    tool = CloseApplicationTool(
        resolver=FakeResolver(None)
    )

    result = tool.execute(
        {
            "name": "ApplicazioneCheNonEsiste",
        }
    )

    assert result.success is False
    assert result.error is not None