from __future__ import annotations

from app.tools.pc_filesystem_ops import (
    CopyPathTool,
    CreateDirectoryTool,
    MovePathTool,
    OpenPathTool,
)


def test_filesystem_operation_definitions() -> None:
    tools = [
        OpenPathTool(),
        CreateDirectoryTool(),
        CopyPathTool(),
        MovePathTool(),
    ]

    names = {
        tool.definition.name
        for tool in tools
    }

    assert names == {
        "open_path",
        "create_directory",
        "copy_path",
        "move_path",
    }


def test_create_directory_is_not_limited_to_project_root(tmp_path) -> None:
    target = tmp_path / "outside" / "nested"

    result = CreateDirectoryTool().execute(
        {
            "path": str(target),
        }
    )

    assert result.success is True
    assert target.is_dir()


def test_copy_path_copies_file(tmp_path) -> None:
    source = tmp_path / "source.txt"
    destination = tmp_path / "destination.txt"

    source.write_text(
        "IRIS",
        encoding="utf-8",
    )

    result = CopyPathTool().execute(
        {
            "source": str(source),
            "destination": str(destination),
        }
    )

    assert result.success is True
    assert destination.read_text(
        encoding="utf-8"
    ) == "IRIS"


def test_copy_path_copies_directory(tmp_path) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "destination"

    source.mkdir()
    (source / "file.txt").write_text(
        "IRIS",
        encoding="utf-8",
    )

    result = CopyPathTool().execute(
        {
            "source": str(source),
            "destination": str(destination),
        }
    )

    assert result.success is True
    assert (destination / "file.txt").read_text(
        encoding="utf-8"
    ) == "IRIS"


def test_move_path_moves_file(tmp_path) -> None:
    source = tmp_path / "source.txt"
    destination = tmp_path / "destination.txt"

    source.write_text(
        "IRIS",
        encoding="utf-8",
    )

    result = MovePathTool().execute(
        {
            "source": str(source),
            "destination": str(destination),
        }
    )

    assert result.success is True
    assert not source.exists()
    assert destination.read_text(
        encoding="utf-8"
    ) == "IRIS"


def test_open_path_rejects_missing_path(tmp_path) -> None:
    result = OpenPathTool().execute(
        {
            "path": str(tmp_path / "missing"),
        }
    )

    assert result.success is False
    assert "non esiste" in result.error.lower()
