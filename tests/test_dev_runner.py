from __future__ import annotations

from pathlib import Path

import dev


from dev import compile_python_sources, snapshot_python_files


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


def test_compile_python_sources_accepts_valid_source(tmp_path: Path) -> None:
    app = tmp_path / "app"
    app.mkdir()

    (app / "main.py").write_text(
        "value = 42\n",
        encoding="utf-8",
    )

    assert compile_python_sources(tmp_path) is True


def test_compile_python_sources_rejects_invalid_source(
    tmp_path: Path,
) -> None:
    app = tmp_path / "app"
    app.mkdir()

    (app / "main.py").write_text(
        "def broken(:\n",
        encoding="utf-8",
    )

    assert compile_python_sources(tmp_path) is False


def test_write_dev_log_does_not_write_to_console(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    log_path = tmp_path / "dev.log"

    monkeypatch.setattr(
        dev,
        "DEV_LOG",
        log_path,
    )

    dev.write_dev_log(
        "test message",
    )

    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == ""
    assert "test message" in log_path.read_text(
        encoding="utf-8",
    )
