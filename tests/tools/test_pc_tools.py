from app.tools.application_resolver import ApplicationResolver
from app.tools.permissions import Permission
from app.tools.pc import OpenApplicationTool


def test_open_application_definition_requires_gui_permission() -> None:
    resolver = ApplicationResolver()
    tool = OpenApplicationTool(resolver=resolver)

    definition = tool.definition

    assert definition.name == "open_application"
    assert Permission.GUI.value in definition.permissions


def test_open_application_rejects_unknown_application() -> None:
    resolver = ApplicationResolver()

    tool = OpenApplicationTool(resolver=resolver)

    result = tool.execute(
        {"name": "questa applicazione sicuramente non esiste 123456"}
    )

    assert result.success is False
    assert result.error is not None
    assert "non riesco a trovare" in result.error.lower()


def test_open_application_accepts_resolver() -> None:
    resolver = ApplicationResolver()
    tool = OpenApplicationTool(resolver=resolver)

    assert tool.resolver is resolver

def test_run_command_definition_accepts_arbitrary_command() -> None:
    from app.tools.pc import RunCommandTool

    tool = RunCommandTool()
    definition = tool.definition

    assert definition.name == "run_command"
    assert "command" in definition.input_schema["properties"]
    assert "cwd" in definition.input_schema["properties"]
    assert "timeout_seconds" in definition.input_schema["properties"]


def test_run_command_does_not_use_hardcoded_allowlist() -> None:
    from app.tools.pc import RunCommandTool

    tool = RunCommandTool(default_timeout_seconds=5)

    result = tool.execute(
        {
            "command": "python --version",
        }
    )

    assert result.success is True
    assert result.output is not None
    assert result.output["returncode"] == 0
    assert "python" in result.output["stdout"].lower()


def test_read_file_has_no_default_directory_restriction(tmp_path) -> None:
    from app.tools.pc import ReadFileTool

    target = tmp_path / "iris-test.txt"
    target.write_text("ciao IRIS", encoding="utf-8")

    tool = ReadFileTool()

    result = tool.execute(
        {
            "path": str(target),
        }
    )

    assert result.success is True
    assert result.output["content"] == "ciao IRIS"


def test_write_file_has_no_default_directory_restriction(tmp_path) -> None:
    from app.tools.pc import WriteFileTool

    target = tmp_path / "iris-test.txt"

    tool = WriteFileTool()

    result = tool.execute(
        {
            "path": str(target),
            "content": "ciao IRIS",
        }
    )

    assert result.success is True
    assert target.read_text(encoding="utf-8") == "ciao IRIS"


def test_file_tools_still_support_explicit_sandbox_roots(tmp_path) -> None:
    from app.tools.pc import ReadFileTool, WriteFileTool

    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()

    target = allowed / "file.txt"
    target.write_text("ok", encoding="utf-8")

    read_tool = ReadFileTool(allowed_roots=[allowed])
    write_tool = WriteFileTool(allowed_roots=[allowed])

    assert read_tool.execute({"path": str(target)}).success is True
    assert (
        read_tool.execute({"path": str(outside / "file.txt")}).success
        is False
    )
    assert (
        write_tool.execute(
            {
                "path": str(outside / "file.txt"),
                "content": "no",
            }
        ).success
        is False
    )
