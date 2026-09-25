from __future__ import annotations

from pathlib import Path

from dev import snapshot_python_files


def test_snapshot_python_files_detects_source_files(tmp_path: Path) -> None:
    app = tmp_path / "app"
    nested = app / "tools"
    nested.mkdir(parents=True)

    first = app / "main.py"
    second = nested / "example.py"
    ignored = nested / "__pycache__" / "ignored.pyc"
    ignored.parent.mkdir()
    ignored.write_bytes(b"ignored")

    first.write_text("print('a')", encoding="utf-8")
    second.write_text("print('b')", encoding="utf-8")

    snapshot = snapshot_python_files(tmp_path)

    assert first in snapshot
    assert second in snapshot
    assert ignored not in snapshot


def test_snapshot_changes_when_python_file_changes(tmp_path: Path) -> None:
    app = tmp_path / "app"
    app.mkdir()

    source = app / "main.py"
    source.write_text("version = 1", encoding="utf-8")

    before = snapshot_python_files(tmp_path)

    source.write_text("version = 2", encoding="utf-8")

    after = snapshot_python_files(tmp_path)

    assert before != after
