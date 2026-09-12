from __future__ import annotations

from pathlib import Path

from app.tools.application_resolver import (
    ApplicationResolver,
    ResolvedApplication,
)


def test_normalize_removes_accents_and_normalizes_spaces():
    resolver = ApplicationResolver()

    assert (
        resolver._normalize(
            "  Calcolàtrice   di   Windows  "
        )
        == "calcolatrice di windows"
    )


def test_resolve_exact_match():
    resolver = ApplicationResolver()

    resolver._cache = [
        ResolvedApplication(
            name="Google Chrome",
            target=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            source="registry",
        ),
        ResolvedApplication(
            name="Visual Studio Code",
            target=r"C:\Program Files\Microsoft VS Code\Code.exe",
            source="registry",
        ),
    ]

    result = resolver.resolve(
        "Google Chrome"
    )

    assert result is not None
    assert result.name == "Google Chrome"
    assert result.source == "registry"


def test_resolve_is_case_insensitive():
    resolver = ApplicationResolver()

    resolver._cache = [
        ResolvedApplication(
            name="Discord",
            target=r"C:\Discord\Discord.exe",
            source="start_menu",
        )
    ]

    result = resolver.resolve(
        "dIsCoRd"
    )

    assert result is not None
    assert result.name == "Discord"


def test_resolve_matches_without_exe_extension():
    resolver = ApplicationResolver()

    resolver._cache = [
        ResolvedApplication(
            name="python.exe",
            target=r"C:\Python\python.exe",
            source="path",
        )
    ]

    result = resolver.resolve(
        "python"
    )

    assert result is not None
    assert result.name == "python.exe"


def test_resolve_matches_partial_name():
    resolver = ApplicationResolver()

    resolver._cache = [
        ResolvedApplication(
            name="Visual Studio Code",
            target=r"C:\VSCode\Code.exe",
            source="start_menu",
        ),
        ResolvedApplication(
            name="Visual Studio Installer",
            target=r"C:\VS\Installer.exe",
            source="start_menu",
        ),
    ]

    result = resolver.resolve(
        "Visual Studio Code"
    )

    assert result is not None
    assert result.name == "Visual Studio Code"


def test_resolve_returns_none_when_not_found():
    resolver = ApplicationResolver()

    resolver._cache = [
        ResolvedApplication(
            name="Discord",
            target=r"C:\Discord\Discord.exe",
            source="start_menu",
        )
    ]

    result = resolver.resolve(
        "Minecraft"
    )

    assert result is None


def test_resolve_rejects_empty_query():
    resolver = ApplicationResolver()

    try:
        resolver.resolve("")
    except ValueError as error:
        assert (
            str(error)
            == "Il nome dell'applicazione non può essere vuoto."
        )
    else:
        raise AssertionError(
            "Era atteso ValueError."
        )


def test_discovery_keeps_first_application_for_same_name():
    resolver = ApplicationResolver()

    found = {}

    first = ResolvedApplication(
        name="Discord",
        target=r"C:\First\Discord.lnk",
        source="start_menu",
    )

    second = ResolvedApplication(
        name="discord",
        target=r"C:\Second\Discord.exe",
        source="path",
    )

    resolver._add_application(
        found,
        first,
    )

    resolver._add_application(
        found,
        second,
    )

    assert len(found) == 1
    assert found["discord"] == first


def test_candidate_priority_prefers_start_menu():
    resolver = ApplicationResolver()

    resolver._cache = [
        ResolvedApplication(
            name="Test Application",
            target=r"C:\Path\Test.exe",
            source="path",
        ),
        ResolvedApplication(
            name="Test Application Extended",
            target=r"C:\Start\Test.lnk",
            source="start_menu",
        ),
    ]

    result = resolver.resolve(
        "test application"
    )

    assert result is not None
    assert result.name == "Test Application"


def test_refresh_clears_cache():
    resolver = ApplicationResolver()

    resolver._cache = [
        ResolvedApplication(
            name="Discord",
            target="discord.exe",
            source="path",
        )
    ]

    resolver.refresh()

    assert resolver._cache is None


def test_start_menu_discovery_reads_lnk_files(
    tmp_path: Path,
):
    resolver = ApplicationResolver()

    start_menu = (
        tmp_path
        / "Programs"
    )

    start_menu.mkdir()

    shortcut = (
        start_menu
        / "Google Chrome.lnk"
    )

    shortcut.write_text(
        "placeholder",
        encoding="utf-8",
    )

    original_appdata = resolver

    found = {}

    resolver._add_application(
        found,
        ResolvedApplication(
            name=shortcut.stem,
            target=str(shortcut),
            source="start_menu",
        ),
    )

    assert "google chrome" in found
    assert (
        found["google chrome"].target
        == str(shortcut)
    )

    del original_appdata