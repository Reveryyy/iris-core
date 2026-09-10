from pathlib import Path
from app.tools.permissions import Permission
from app.tools.pc import (
    OpenApplicationTool,
    ReadFileTool,
    RunCommandTool,
    WriteFileTool,
)


def test_open_application_rejects_unknown_application() -> None:
    tool = OpenApplicationTool(
        allowed_applications={
            "allowed": "notepad.exe",
        }
    )

    result = tool.execute(
        {
            "name": "unknown",
        }
    )

    assert result.success is False
    assert "allowlist" in (result.error or "")


def test_read_file_reads_authorized_file(
    tmp_path: Path,
) -> None:

    file_path = tmp_path / "test.txt"

    file_path.write_text(
        "ciao IRIS",
        encoding="utf-8",
    )

    tool = ReadFileTool(
        allowed_roots=[
            tmp_path,
        ]
    )

    result = tool.execute(
        {
            "path": str(file_path),
        }
    )

    assert result.success is True

    assert result.output["content"] == "ciao IRIS"


def test_read_file_rejects_file_outside_root(
    tmp_path: Path,
) -> None:

    allowed_root = tmp_path / "allowed"
    outside_root = tmp_path / "outside"

    allowed_root.mkdir()
    outside_root.mkdir()

    file_path = outside_root / "secret.txt"

    file_path.write_text(
        "secret",
        encoding="utf-8",
    )

    tool = ReadFileTool(
        allowed_roots=[
            allowed_root,
        ]
    )

    result = tool.execute(
        {
            "path": str(file_path),
        }
    )

    assert result.success is False


def test_write_file_writes_authorized_file(
    tmp_path: Path,
) -> None:

    file_path = tmp_path / "output.txt"

    tool = WriteFileTool(
        allowed_roots=[
            tmp_path,
        ]
    )

    result = tool.execute(
        {
            "path": str(file_path),
            "content": "ciao IRIS",
        }
    )

    assert result.success is True

    assert file_path.read_text(
        encoding="utf-8"
    ) == "ciao IRIS"


def test_write_file_rejects_file_outside_root(
    tmp_path: Path,
) -> None:

    allowed_root = tmp_path / "allowed"
    outside_root = tmp_path / "outside"

    allowed_root.mkdir()
    outside_root.mkdir()

    file_path = outside_root / "output.txt"

    tool = WriteFileTool(
        allowed_roots=[
            allowed_root,
        ]
    )

    result = tool.execute(
        {
            "path": str(file_path),
            "content": "test",
        }
    )

    assert result.success is False


def test_run_command_rejects_unknown_command() -> None:
    tool = RunCommandTool(
        allowed_commands={
            "python_version": [
                "python",
                "--version",
            ],
        }
    )

    result = tool.execute(
        {
            "command": "format_c_drive",
        }
    )

    assert result.success is False
    assert "allowlist" in (result.error or "")


def test_run_command_executes_allowed_command() -> None:
    tool = RunCommandTool(
        allowed_commands={
            "python_version": [
                "python",
                "--version",
            ],
        }
    )

    result = tool.execute(
        {
            "command": "python_version",
        }
    )

    assert result.success is True
    assert result.output["returncode"] == 0
    assert result.output["stdout"]


def test_tool_permissions_are_declared() -> None:
    open_tool = OpenApplicationTool()
    read_tool = ReadFileTool()
    write_tool = WriteFileTool()
    command_tool = RunCommandTool()

    assert Permission.GUI.value in (
        open_tool.definition.permissions
    )

    assert Permission.READ.value in (
        read_tool.definition.permissions
    )

    assert Permission.WRITE.value in (
        write_tool.definition.permissions
    )

    assert Permission.EXECUTE.value in (
        command_tool.definition.permissions
    )


def test_tool_definitions_have_required_metadata() -> None:
    tools = [
        OpenApplicationTool(),
        ReadFileTool(),
        WriteFileTool(),
        RunCommandTool(),
    ]

    for tool in tools:
        definition = tool.definition

        assert definition.name
        assert definition.description
        assert definition.input_schema
        assert definition.risk_level
        assert isinstance(
            definition.permissions,
            frozenset,
        )