from __future__ import annotations

from pathlib import Path

import pytest

from app.tools.application_resolver import (
    ApplicationResolver,
    ResolvedApplication,
)

from app.tools.pc import (
    OpenApplicationTool,
)


# ============================================================================
# APPLICATION RESOLVER
# ============================================================================


def test_resolved_application_contains_expected_data():
    application = ResolvedApplication(
        name="Notepad",
        target=r"C:\Windows\System32\notepad.exe",
        source="path",
    )

    assert application.name == "Notepad"

    assert application.target.endswith(
        "notepad.exe"
    )

    assert application.source == "path"

    assert application.app_id is None


def test_resolver_rejects_non_string_query():
    resolver = ApplicationResolver()

    with pytest.raises(TypeError):
        resolver.resolve(123)


def test_resolver_rejects_empty_query():
    resolver = ApplicationResolver()

    with pytest.raises(ValueError):
        resolver.resolve("   ")


def test_normalize_is_case_insensitive():
    resolver = ApplicationResolver()

    assert resolver._normalize(
        "Notepad"
    ) == resolver._normalize(
        "notepad"
    )


def test_normalize_removes_accents():
    resolver = ApplicationResolver()

    assert resolver._normalize(
        "Applicàzione"
    ) == "applicazione"


def test_normalize_collapses_whitespace():
    resolver = ApplicationResolver()

    assert resolver._normalize(
        "  Windows     Terminal  "
    ) == "windows terminal"


def test_resolver_exact_match(monkeypatch):
    resolver = ApplicationResolver()

    applications = [
        ResolvedApplication(
            name="Discord",
            target="discord.exe",
            source="path",
        ),
        ResolvedApplication(
            name="Google Chrome",
            target="chrome.exe",
            source="path",
        ),
    ]

    monkeypatch.setattr(
        resolver,
        "_discover",
        lambda: applications,
    )

    result = resolver.resolve(
        "Discord"
    )

    assert result is not None

    assert result.name == "Discord"

    assert result.target == "discord.exe"


def test_resolver_match_is_case_insensitive(
    monkeypatch,
):
    resolver = ApplicationResolver()

    applications = [
        ResolvedApplication(
            name="Discord",
            target="discord.exe",
            source="path",
        ),
    ]

    monkeypatch.setattr(
        resolver,
        "_discover",
        lambda: applications,
    )

    result = resolver.resolve(
        "discord"
    )

    assert result is not None

    assert result.name == "Discord"


def test_resolver_matches_without_extension(
    monkeypatch,
):
    resolver = ApplicationResolver()

    applications = [
        ResolvedApplication(
            name="notepad.exe",
            target=r"C:\Windows\System32\notepad.exe",
            source="path",
        ),
    ]

    monkeypatch.setattr(
        resolver,
        "_discover",
        lambda: applications,
    )

    result = resolver.resolve(
        "notepad"
    )

    assert result is not None

    assert result.name == "notepad.exe"


def test_resolver_partial_match(monkeypatch):
    resolver = ApplicationResolver()

    applications = [
        ResolvedApplication(
            name="Google Chrome",
            target="chrome.exe",
            source="path",
        ),
        ResolvedApplication(
            name="Discord",
            target="discord.exe",
            source="path",
        ),
    ]

    monkeypatch.setattr(
        resolver,
        "_discover",
        lambda: applications,
    )

    result = resolver.resolve(
        "Chrome"
    )

    assert result is not None

    assert result.name == "Google Chrome"


def test_resolver_application_name_can_be_contained_in_query(
    monkeypatch,
):
    resolver = ApplicationResolver()

    applications = [
        ResolvedApplication(
            name="Discord",
            target="discord.exe",
            source="path",
        ),
    ]

    monkeypatch.setattr(
        resolver,
        "_discover",
        lambda: applications,
    )

    result = resolver.resolve(
        "open discord application"
    )

    assert result is not None

    assert result.name == "Discord"


def test_resolver_returns_none_when_application_is_missing(
    monkeypatch,
):
    resolver = ApplicationResolver()

    monkeypatch.setattr(
        resolver,
        "_discover",
        lambda: [],
    )

    result = resolver.resolve(
        "ApplicazioneCheNonEsiste"
    )

    assert result is None


def test_resolver_cache_is_reused():
    resolver = ApplicationResolver()

    applications = [
        ResolvedApplication(
            name="Notepad",
            target="notepad.exe",
            source="path",
        ),
    ]

    calls = 0

    original_discover = resolver._discover

    def discover():
        nonlocal calls

        calls += 1

        return original_discover()

    # Usiamo un resolver isolato con discovery controllata.
    resolver._cache = None

    def fake_discover():
        nonlocal calls

        calls += 1

        return applications

    resolver._cache = None

    # Il metodo resolve() normalmente richiama _discover().
    # La prima chiamata deve popolare la cache.
    resolver._discover = fake_discover

    first = resolver.resolve(
        "Notepad"
    )

    second = resolver.resolve(
        "Notepad"
    )

    assert first == second

    assert calls == 2


def test_resolver_refresh_clears_cache():
    resolver = ApplicationResolver()

    resolver._cache = [
        ResolvedApplication(
            name="Test",
            target="test.exe",
            source="path",
        )
    ]

    resolver.refresh()

    assert resolver._cache is None


def test_add_application_deduplicates_names():
    found = {}

    first = ResolvedApplication(
        name="Discord",
        target="first.exe",
        source="start_menu",
    )

    second = ResolvedApplication(
        name="discord",
        target="second.exe",
        source="path",
    )

    ApplicationResolver._add_application(
        found=found,
        application=first,
    )

    ApplicationResolver._add_application(
        found=found,
        application=second,
    )

    assert len(found) == 1

    assert found[
        ApplicationResolver._normalize("Discord")
    ] == first


def test_candidate_sort_prefers_start_menu():
    resolver = ApplicationResolver()

    start_menu = ResolvedApplication(
        name="Discord",
        target="discord.lnk",
        source="start_menu",
    )

    path = ResolvedApplication(
        name="Discord",
        target="discord.exe",
        source="path",
    )

    assert (
        resolver._candidate_sort_key(
            start_menu
        )
        < resolver._candidate_sort_key(
            path
        )
    )


def test_candidate_sort_prefers_shorter_name_for_same_source():
    resolver = ApplicationResolver()

    short_name = ResolvedApplication(
        name="Discord",
        target="discord.exe",
        source="path",
    )

    long_name = ResolvedApplication(
        name="Discord Canary",
        target="discordcanary.exe",
        source="path",
    )

    assert (
        resolver._candidate_sort_key(
            short_name
        )
        < resolver._candidate_sort_key(
            long_name
        )
    )


# ============================================================================
# OPEN APPLICATION TOOL
# ============================================================================

def test_open_application_process_discovery_preserves_verification_metadata(
    monkeypatch,
):
    application = ResolvedApplication(
        name="Calcolatrice",
        target="CalculatorApp.exe",
        source="path",
    )

    tool = OpenApplicationTool(
        resolver=FakeResolver(application)
    )

    powershell_result = type(
        "Completed",
        (),
        {
            "returncode": 0,
            "stderr": "",
            "stdout": (
                '{"Id":123,"ProcessName":"CalculatorApp",'
                '"Path":"C:\\Windows\\SystemApps\\CalculatorApp.exe",'
                '"Description":"Windows Calculator",'
                '"Product":"Windows Calculator",'
                '"MainWindowTitle":"Calcolatrice"}'
            ),
        },
    )()

    monkeypatch.setattr(
        "app.tools.pc.subprocess.run",
        lambda *args, **kwargs: powershell_result,
    )

    processes = tool._discover_processes()

    assert processes == [
        {
            "pid": 123,
            "name": "CalculatorApp",
            "path": r"C:\Windows\SystemApps\CalculatorApp.exe",
            "description": "Windows Calculator",
            "product": "Windows Calculator",
            "main_window_title": "Calcolatrice",
        }
    ]




class FakeResolver:
    def __init__(
        self,
        application: ResolvedApplication | None,
    ):
        self.application = application
        self.queries: list[str] = []

    def resolve(
        self,
        query: str,
    ) -> ResolvedApplication | None:
        self.queries.append(query)

        return self.application


def test_open_application_definition():
    tool = OpenApplicationTool(
        resolver=FakeResolver(None)
    )

    definition = tool.definition

    assert definition.name == "open_application"

    assert definition.risk_level == "medium"

    assert "name" in definition.input_schema[
        "properties"
    ]

    assert definition.input_schema[
        "required"
    ] == ["name"]


def test_open_application_rejects_invalid_verification_timeout():
    with pytest.raises(ValueError):
        OpenApplicationTool(
            resolver=FakeResolver(None),
            verification_timeout=0,
        )


def test_open_application_rejects_invalid_verification_interval():
    with pytest.raises(ValueError):
        OpenApplicationTool(
            resolver=FakeResolver(None),
            verification_interval=0,
        )


def test_open_application_rejects_missing_name():
    tool = OpenApplicationTool(
        resolver=FakeResolver(None)
    )

    result = tool.execute({})

    assert result.success is False

    assert result.error is not None

    assert "nome" in result.error.lower()


def test_open_application_rejects_non_string_name():
    tool = OpenApplicationTool(
        resolver=FakeResolver(None)
    )

    result = tool.execute(
        {
            "name": 123,
        }
    )

    assert result.success is False

    assert result.error is not None


def test_open_application_rejects_empty_name():
    tool = OpenApplicationTool(
        resolver=FakeResolver(None)
    )

    result = tool.execute(
        {
            "name": "   ",
        }
    )

    assert result.success is False

    assert result.error is not None


def test_open_application_reports_missing_application():
    resolver = FakeResolver(None)

    tool = OpenApplicationTool(
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


def test_open_application_launches_and_verifies_resolved_application(
    monkeypatch,
):
    application = ResolvedApplication(
        name="Notepad",
        target=r"C:\Windows\System32\notepad.exe",
        source="path",
    )

    resolver = FakeResolver(
        application
    )

    tool = OpenApplicationTool(
        resolver=resolver
    )

    processes_before = [
        {
            "pid": 100,
            "name": "explorer",
            "path": r"C:\Windows\explorer.exe",
        }
    ]

    processes_after = [
        {
            "pid": 100,
            "name": "explorer",
            "path": r"C:\Windows\explorer.exe",
        },
        {
            "pid": 12345,
            "name": "notepad",
            "path": r"C:\Windows\System32\notepad.exe",
        },
    ]

    calls = 0

    def discover_processes():
        nonlocal calls

        calls += 1

        if calls == 1:
            return processes_before

        return processes_after

    monkeypatch.setattr(
        tool,
        "_discover_processes",
        discover_processes,
    )

    monkeypatch.setattr(
        tool,
        "_launch",
        lambda resolved: 12345,
    )

    result = tool.execute(
        {
            "name": "Notepad",
        }
    )

    assert result.success is True

    assert result.output is not None

    assert result.output[
        "requested_name"
    ] == "Notepad"

    assert result.output[
        "application"
    ] == "Notepad"

    assert result.output[
        "target"
    ] == r"C:\Windows\System32\notepad.exe"

    assert result.output[
        "source"
    ] == "path"

    assert result.output[
        "launch_pid"
    ] == 12345

    assert result.output[
        "verified_pid"
    ] == 12345

    assert result.output[
        "verified_process_name"
    ] == "notepad"

    assert result.output[
        "already_running"
    ] is False


def test_open_application_fails_when_process_cannot_be_verified(
    monkeypatch,
):
    application = ResolvedApplication(
        name="Notepad",
        target=r"C:\Windows\System32\notepad.exe",
        source="path",
    )

    tool = OpenApplicationTool(
        resolver=FakeResolver(application),
        verification_timeout=0.05,
        verification_interval=0.01,
    )

    processes = [
        {
            "pid": 100,
            "name": "explorer",
            "path": r"C:\Windows\explorer.exe",
        }
    ]

    monkeypatch.setattr(
        tool,
        "_discover_processes",
        lambda: processes,
    )

    monkeypatch.setattr(
        tool,
        "_launch",
        lambda resolved: 12345,
    )

    result = tool.execute(
        {
            "name": "Notepad",
        }
    )

    assert result.success is False

    assert result.output is not None

    assert result.output[
        "launch_pid"
    ] == 12345

    assert result.error is not None

    assert (
        "non sono riuscito a verificare"
        in result.error.lower()
    )


def test_open_application_accepts_preexisting_matching_process(
    monkeypatch,
):
    application = ResolvedApplication(
        name="Notepad",
        target=r"C:\Windows\System32\notepad.exe",
        source="path",
    )

    tool = OpenApplicationTool(
        resolver=FakeResolver(application),
        verification_timeout=0.05,
        verification_interval=0.01,
    )

    processes = [
        {
            "pid": 555,
            "name": "notepad",
            "path": r"C:\Windows\System32\notepad.exe",
        }
    ]

    launch_called = False

    def fake_launch(
        resolved,
    ):
        nonlocal launch_called

        launch_called = True

        return 12345

    monkeypatch.setattr(
        tool,
        "_discover_processes",
        lambda: processes,
    )

    monkeypatch.setattr(
        tool,
        "_launch",
        fake_launch,
    )

    result = tool.execute(
        {
            "name": "Notepad",
        }
    )

    assert result.success is True

    assert result.output is not None

    assert result.output[
        "requested_name"
    ] == "Notepad"

    assert result.output[
        "application"
    ] == "Notepad"

    assert result.output[
        "verified_pid"
    ] == 555

    assert result.output[
        "verified_process_name"
    ] == "notepad"

    assert result.output[
        "already_running"
    ] is True

    assert result.output[
        "launch_pid"
    ] is None

    assert (
        result.output[
            "user_message"
        ]
        == "Notepad è già in esecuzione."
    )

    assert launch_called is False


def test_open_application_accepts_new_matching_process_even_if_name_differs(
    monkeypatch,
):
    application = ResolvedApplication(
        name="Google Chrome",
        target=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        source="path",
    )

    tool = OpenApplicationTool(
        resolver=FakeResolver(application)
    )

    processes_before = [
        {
            "pid": 100,
            "name": "explorer",
            "path": r"C:\Windows\explorer.exe",
        }
    ]

    processes_after = [
        {
            "pid": 100,
            "name": "explorer",
            "path": r"C:\Windows\explorer.exe",
        },
        {
            "pid": 22222,
            "name": "chrome",
            "path": (
                r"C:\Program Files\Google\Chrome"
                r"\Application\chrome.exe"
            ),
        },
    ]

    calls = 0

    def discover_processes():
        nonlocal calls

        calls += 1

        if calls == 1:
            return processes_before

        return processes_after

    monkeypatch.setattr(
        tool,
        "_discover_processes",
        discover_processes,
    )

    monkeypatch.setattr(
        tool,
        "_launch",
        lambda resolved: 22222,
    )

    result = tool.execute(
        {
            "name": "Google Chrome",
        }
    )

    assert result.success is True

    assert result.output is not None

    assert result.output[
        "verified_pid"
    ] == 22222

    assert result.output[
        "verified_process_name"
    ] == "chrome"

    assert result.output[
        "already_running"
    ] is False


def test_open_application_handles_launch_failure(
    monkeypatch,
):
    application = ResolvedApplication(
        name="Notepad",
        target=r"C:\Windows\System32\notepad.exe",
        source="path",
    )

    resolver = FakeResolver(
        application
    )

    tool = OpenApplicationTool(
        resolver=resolver
    )

    def fail_launch(
        resolved,
    ):
        raise OSError(
            "Impossibile avviare il processo"
        )

    monkeypatch.setattr(
        tool,
        "_discover_processes",
        lambda: [],
    )

    monkeypatch.setattr(
        tool,
        "_launch",
        fail_launch,
    )

    result = tool.execute(
        {
            "name": "Notepad",
        }
    )

    assert result.success is False

    assert result.error is not None

    assert (
        "impossibile aprire"
        in result.error.lower()
    )


def test_open_application_preserves_windows_app_metadata(
    monkeypatch,
):
    application = ResolvedApplication(
        name="Windows Terminal",
        target=(
            "Microsoft.WindowsTerminal_"
            "8wekyb3d8bbwe!App"
        ),
        source="windows_start_apps",
        app_id=(
            "Microsoft.WindowsTerminal_"
            "8wekyb3d8bbwe!App"
        ),
    )

    resolver = FakeResolver(
        application
    )

    tool = OpenApplicationTool(
        resolver=resolver
    )

    processes_before = [
        {
            "pid": 100,
            "name": "explorer",
            "path": r"C:\Windows\explorer.exe",
        }
    ]

    processes_after = [
        {
            "pid": 100,
            "name": "explorer",
            "path": r"C:\Windows\explorer.exe",
        },
        {
            "pid": 45678,
            "name": "WindowsTerminal",
            "path": (
                r"C:\Program Files\WindowsApps"
                r"\Microsoft.WindowsTerminal"
                r"\WindowsTerminal.exe"
            ),
        },
    ]

    calls = 0

    def discover_processes():
        nonlocal calls

        calls += 1

        if calls == 1:
            return processes_before

        return processes_after

    monkeypatch.setattr(
        tool,
        "_discover_processes",
        discover_processes,
    )

    monkeypatch.setattr(
        tool,
        "_launch",
        lambda resolved: 45678,
    )

    result = tool.execute(
        {
            "name": "Windows Terminal",
        }
    )

    assert result.success is True

    assert result.output is not None

    assert result.output[
        "application"
    ] == "Windows Terminal"

    assert result.output[
        "source"
    ] == "windows_start_apps"

    assert result.output[
        "target"
    ] == (
        "Microsoft.WindowsTerminal_"
        "8wekyb3d8bbwe!App"
    )

    assert result.output[
        "launch_pid"
    ] == 45678

    assert result.output[
        "verified_pid"
    ] == 45678

    assert result.output[
        "already_running"
    ] is False


def test_open_application_normalizes_process_names():
    assert (
        OpenApplicationTool._normalize_name(
            "Windows-Terminal.exe"
        )
        == "windowsterminal"
    )

    assert (
        OpenApplicationTool._normalize_name(
            "Windows_Terminal"
        )
        == "windowsterminal"
    )


def test_process_matches_by_process_name():
    application = ResolvedApplication(
        name="Discord",
        target="discord.exe",
        source="path",
    )

    process = {
        "pid": 100,
        "name": "Discord",
        "path": None,
    }

    assert OpenApplicationTool._process_matches(
        process=process,
        expected_names={"discord"},
        application=application,
    )


def test_process_matches_by_executable_path():
    application = ResolvedApplication(
        name="Google Chrome",
        target="chrome.exe",
        source="path",
    )

    process = {
        "pid": 100,
        "name": "browser",
        "path": (
            r"C:\Program Files\Google\Chrome"
            r"\Application\chrome.exe"
        ),
    }

    assert OpenApplicationTool._process_matches(
        process=process,
        expected_names={"chrome"},
        application=application,
    )


def test_process_matches_modern_windows_app_by_display_metadata():
    application = ResolvedApplication(
        name="Calcolatrice",
        target=r"C:\Windows\SystemApps\CalculatorApp.lnk",
        source="start_menu",
    )

    process = {
        "pid": 100,
        "name": "CalculatorApp",
        "path": (
            r"C:\Program Files\WindowsApps"
            r"\Microsoft.WindowsCalculator\CalculatorApp.exe"
        ),
        "description": "Windows Calculator",
        "product": "Windows Calculator",
        "main_window_title": "Calcolatrice",
    }

    assert OpenApplicationTool._process_matches(
        process=process,
        expected_names={"calcolatrice"},
        application=application,
    )


def test_process_does_not_match_unrelated_process():
    application = ResolvedApplication(
        name="Discord",
        target="discord.exe",
        source="path",
    )

    process = {
        "pid": 100,
        "name": "chrome",
        "path": (
            r"C:\Program Files\Google\Chrome"
            r"\chrome.exe"
        ),
    }

    assert not OpenApplicationTool._process_matches(
        process=process,
        expected_names={"discord"},
        application=application,
    )


# ============================================================================
# WINDOWS-SPECIFIC DISCOVERY
# ============================================================================


@pytest.mark.skipif(
    __import__("os").name != "nt",
    reason="Test disponibile solo su Windows.",
)
def test_windows_process_discovery_returns_process_list():
    processes = OpenApplicationTool._discover_processes()

    assert isinstance(
        processes,
        list,
    )

    for process in processes:
        assert isinstance(
            process,
            dict,
        )

        assert isinstance(
            process.get("pid"),
            int,
        )

        assert isinstance(
            process.get("name"),
            str,
        )


@pytest.mark.skipif(
    __import__("os").name != "nt",
    reason="Test disponibile solo su Windows.",
)
def test_windows_process_discovery_contains_current_python_process():
    processes = OpenApplicationTool._discover_processes()

    python_processes = [
        process
        for process in processes
        if process["name"].casefold()
        in {
            "python",
            "python.exe",
        }
    ]

    assert python_processes