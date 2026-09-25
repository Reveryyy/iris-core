from __future__ import annotations

import subprocess

from app.tools.pc_filesystem import (
    InspectPathTool,
    ListDirectoryTool,
    SearchFilesTool,
)
from app.tools.permissions import Permission


def test_inspect_path_definition() -> None:
    tool = InspectPathTool()

    definition = tool.definition

    assert definition.name == "inspect_path"
    assert definition.risk_level == "low"
    assert Permission.READ.value in definition.permissions
    assert definition.input_schema["required"] == ["path"]


def test_inspect_path_returns_dynamic_metadata(tmp_path) -> None:
    target = tmp_path / "example.txt"
    target.write_text("IRIS", encoding="utf-8")

    result = InspectPathTool().execute(
        {
            "path": str(target),
        }
    )

    assert result.success is True
    assert result.output["exists"] is True
    assert result.output["is_file"] is True
    assert result.output["is_directory"] is False
    assert result.output["size_bytes"] == 4
    assert result.output["path"] == str(target.resolve())


def test_inspect_path_reports_missing_path(tmp_path) -> None:
    target = tmp_path / "missing.txt"

    result = InspectPathTool().execute(
        {
            "path": str(target),
        }
    )

    assert result.success is False
    assert result.output["exists"] is False


def test_list_directory_returns_all_entries_without_default_limit(
    tmp_path,
) -> None:
    for index in range(25):
        (tmp_path / f"file-{index}.txt").write_text(
            str(index),
            encoding="utf-8",
        )

    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "inside.txt").write_text(
        "inside",
        encoding="utf-8",
    )

    result = ListDirectoryTool().execute(
        {
            "path": str(tmp_path),
        }
    )

    assert result.success is True
    assert result.output["count"] == 26

    names = {
        entry["name"]
        for entry in result.output["entries"]
    }

    assert "file-0.txt" in names
    assert "file-24.txt" in names
    assert "nested" in names


def test_list_directory_can_hide_dot_entries(tmp_path) -> None:
    (tmp_path / ".hidden").write_text(
        "hidden",
        encoding="utf-8",
    )
    (tmp_path / "visible.txt").write_text(
        "visible",
        encoding="utf-8",
    )

    result = ListDirectoryTool().execute(
        {
            "path": str(tmp_path),
            "include_hidden": False,
        }
    )

    assert result.success is True

    names = {
        entry["name"]
        for entry in result.output["entries"]
    }

    assert ".hidden" not in names
    assert "visible.txt" in names


def test_search_files_finds_nested_files(tmp_path) -> None:
    first = tmp_path / "first.py"
    second_directory = tmp_path / "nested"
    second_directory.mkdir()
    second = second_directory / "second.py"

    first.write_text("one", encoding="utf-8")
    second.write_text("two", encoding="utf-8")

    result = SearchFilesTool().execute(
        {
            "query": "*.py",
            "location": str(tmp_path),
        }
    )

    assert result.success is True
    assert result.output["count"] == 2

    found_paths = {
        entry["path"]
        for entry in result.output["results"]
    }

    assert str(first.resolve()) in found_paths
    assert str(second.resolve()) in found_paths


def test_search_files_is_case_insensitive_by_default(tmp_path) -> None:
    target = tmp_path / "Important.PY"
    target.write_text("ok", encoding="utf-8")

    result = SearchFilesTool().execute(
        {
            "query": "*.py",
            "location": str(tmp_path),
        }
    )

    assert result.success is True
    assert result.output["count"] == 1


def test_search_files_can_include_directories(tmp_path) -> None:
    directory = tmp_path / "build"
    directory.mkdir()

    result = SearchFilesTool().execute(
        {
            "query": "*",
            "location": str(tmp_path),
            "include_directories": True,
        }
    )

    assert result.success is True

    paths = {
        entry["path"]
        for entry in result.output["results"]
    }

    assert str(directory.resolve()) in paths



def test_search_files_exposes_git_tracking_state(
    tmp_path,
    monkeypatch,
) -> None:
    (tmp_path / ".git").mkdir()

    tracked = tmp_path / "tracked.txt"
    untracked = tmp_path / "test_file.txt"

    tracked.write_text("tracked", encoding="utf-8")
    untracked.write_text("untracked", encoding="utf-8")

    tracked_relative = tracked.name

    def fake_git(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args[0] if args else [],
            returncode=0,
            stdout=f"{tracked_relative}\x00",
            stderr="",
        )

    monkeypatch.setattr(
        "app.tools.pc_filesystem.subprocess.run",
        fake_git,
    )

    result = SearchFilesTool().execute(
        {
            "query": "*.txt",
            "location": str(tmp_path),
        }
    )

    assert result.success is True

    by_name = {
        entry["name"]: entry
        for entry in result.output["results"]
    }

    assert by_name["tracked.txt"]["is_git_tracked"] is True
    assert by_name["test_file.txt"]["is_git_tracked"] is False


def test_search_files_requires_location() -> None:
    result = SearchFilesTool().execute(
        {
            "query": "*.py",
        }
    )

    assert result.success is False
