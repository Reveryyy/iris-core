from __future__ import annotations

import os

from app.tools.pc_system import (
    DiscoverApplicationsTool,
    DiscoverCommandsTool,
    DiscoverSystemInfoTool,
    ListProcessesTool,
)


def test_discover_system_info_returns_dynamic_environment() -> None:
    result = DiscoverSystemInfoTool().execute({})

    assert result.success is True
    assert result.output["cpu_count"] == os.cpu_count()
    assert os.getcwd() == result.output["host"]["cwd"]
    assert isinstance(
        result.output["environment_variable_names"],
        list,
    )


def test_discover_commands_uses_actual_path(tmp_path) -> None:
    command_name = "iris-dynamic-command"

    if os.name == "nt":
        executable = tmp_path / f"{command_name}.cmd"
        executable.write_text(
            "@echo off\necho iris",
            encoding="utf-8",
        )
        pathext = ".CMD"
    else:
        executable = tmp_path / command_name
        executable.write_text(
            "#!/bin/sh\necho iris",
            encoding="utf-8",
        )
        executable.chmod(
            executable.stat().st_mode | 0o111
        )
        pathext = ""

    tool = DiscoverCommandsTool(
        path_environment=str(tmp_path),
        pathext_environment=pathext,
    )

    result = tool.execute({})

    assert result.success is True

    commands = {
        item["name"]
        for item in result.output["commands"]
    }

    assert command_name in commands


def test_discover_applications_uses_resolver(monkeypatch) -> None:
    from app.tools.application_resolver import (
        ApplicationResolver,
        ResolvedApplication,
    )

    resolver = ApplicationResolver()

    applications = [
        ResolvedApplication(
            name="Application A",
            target="a.exe",
            source="path",
        ),
        ResolvedApplication(
            name="Application B",
            target="b.exe",
            source="path",
        ),
    ]

    monkeypatch.setattr(
        resolver,
        "discover",
        lambda: applications,
    )

    result = DiscoverApplicationsTool(
        resolver=resolver,
    ).execute({})

    assert result.success is True
    assert result.output["count"] == 2


def test_list_processes_definition() -> None:
    definition = ListProcessesTool().definition

    assert definition.name == "list_processes"
    assert definition.input_schema["required"] == []


def test_discovery_tools_reject_unexpected_arguments() -> None:
    tools = [
        DiscoverSystemInfoTool(),
        DiscoverCommandsTool(),
        DiscoverApplicationsTool(),
        ListProcessesTool(),
    ]

    for tool in tools:
        result = tool.execute(
            {
                "unexpected": True,
            }
        )

        assert result.success is False
