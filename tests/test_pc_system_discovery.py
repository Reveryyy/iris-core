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


def test_list_processes_executes_discovery(monkeypatch):
    from app.agent.pc_state import RunningProcess

    monkeypatch.setattr(
        "app.tools.pc_system.DiscoverPCStateTool._discover_processes",
        lambda self: [
            RunningProcess(
                pid=101,
                name="chrome",
                executable=r"C:\Program Files\Google\chrome.exe",
            ),
        ],
    )

    result = ListProcessesTool().execute({})

    assert result.success is True
    assert result.output["count"] == 1
    assert result.output["processes"] == [
        {
            "pid": 101,
            "name": "chrome",
            "executable": r"C:\Program Files\Google\chrome.exe",
            "command_line": None,
        }
    ]


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


def test_planner_falls_back_to_list_processes_for_process_discovery():
    from app.agent.planner import AgentDecision, AgentPlanner

    planner = AgentPlanner(
        router=None,
    )

    plan = planner._build_process_discovery_fallback(
        goal="/agent dimmi quali processi sono in esecuzione",
        tool_definitions=[
            {
                "name": "list_processes",
            }
        ],
    )

    assert plan is not None
    assert plan.decision == AgentDecision.DONE
    assert len(plan.steps) == 1
    assert plan.steps[0].tool_name == "list_processes"
    assert plan.steps[0].arguments == {}


def test_planner_process_fallback_does_not_capture_mutating_requests():
    from app.agent.planner import AgentPlanner

    planner = AgentPlanner(
        router=None,
    )

    plan = planner._build_process_discovery_fallback(
        goal="/agent chiudi il processo Discord",
        tool_definitions=[
            {
                "name": "list_processes",
            }
        ],
    )

    assert plan is None


def test_planner_process_discovery_fallback_runs_before_llm():
    from app.agent.planner import AgentPlanner

    class ExplodingRouter:
        def generate(self, *args, **kwargs):
            raise AssertionError(
                "Il router LLM non deve essere chiamato per una "
                "richiesta semplice di discovery dei processi."
            )

    planner = AgentPlanner(
        router=ExplodingRouter(),
    )

    plan = planner.plan(
        goal="/agent dimmi quali processi sono in esecuzione",
        tool_definitions=[
            {
                "name": "list_processes",
            }
        ],
    )

    assert plan.steps[0].tool_name == "list_processes"
    assert plan.steps[0].arguments == {}


def test_parse_powershell_processes_accepts_minimal_utf8_json():
    tool = ListProcessesTool()

    raw = (
        '[{"Id":101,"ProcessName":"chrome","Path":"'
        'C:\\\\Program Files\\\\Google\\\\chrome.exe"},'
        '{"Id":202,"ProcessName":"Telegram","Path":null}]'
    )

    parsed = tool._parse_powershell_processes(raw)

    assert [
        {
            "pid": process.pid,
            "name": process.name,
            "executable": process.executable,
        }
        for process in parsed
    ] == [
        {
            "pid": 101,
            "name": "chrome",
            "executable": r"C:\Program Files\Google\chrome.exe",
        },
        {
            "pid": 202,
            "name": "Telegram",
            "executable": None,
        },
    ]


def test_windows_process_discovery_falls_back_to_tasklist(monkeypatch):
    from app.tools.pc_discovery import DiscoverPCStateTool

    tasklist_result = type(
        "Completed",
        (),
        {
            "returncode": 0,
            "stderr": b"",
            "stdout": (
                '"chrome.exe","101","Console","1","100,000 K"\r\n'
                '"IRIS-é.exe","202","Console","1","50,000 K"\r\n'
            ).encode("cp1252"),
        },
    )()

    monkeypatch.setattr(
        "app.tools.pc_discovery.os.name",
        "nt",
    )
    monkeypatch.setattr(
        "app.tools.pc_discovery.OpenApplicationTool._discover_processes",
        lambda: (_ for _ in ()).throw(
            OSError("PowerShell indisponibile")
        ),
    )
    monkeypatch.setattr(
        "app.tools.pc_discovery.os.path.exists",
        lambda path: True,
    )
    monkeypatch.setattr(
        "app.tools.pc_discovery.subprocess.run",
        lambda *args, **kwargs: tasklist_result,
    )
    monkeypatch.setattr(
        "app.tools.pc_discovery.os.environ",
        {"SystemRoot": r"C:\Windows"},
    )

    tool = DiscoverPCStateTool(
        include_processes=True,
    )

    processes = tool._discover_processes_windows()

    assert [
        {
            "pid": process.pid,
            "name": process.name,
            "executable": process.executable,
        }
        for process in processes
    ] == [
        {
            "pid": 101,
            "name": "chrome.exe",
            "executable": None,
        },
        {
            "pid": 202,
            "name": "IRIS-é.exe",
            "executable": None,
        },
    ]


def test_windows_process_discovery_reuses_open_application_discovery(monkeypatch):
    from app.tools.pc_discovery import DiscoverPCStateTool

    expected = [
        {
            "pid": 101,
            "name": "chrome",
            "path": r"C:Program FilesGooglechrome.exe",
        },
        {
            "pid": 202,
            "name": "Telegram",
            "path": None,
        },
    ]

    monkeypatch.setattr(
        "app.tools.pc_discovery.OpenApplicationTool._discover_processes",
        lambda: expected,
    )

    tool = DiscoverPCStateTool(
        include_processes=True,
    )

    processes = tool._discover_processes_windows()

    assert [
        {
            "pid": process.pid,
            "name": process.name,
            "executable": process.executable,
        }
        for process in processes
    ] == [
        {
            "pid": 101,
            "name": "chrome",
            "executable": r"C:Program FilesGooglechrome.exe",
        },
        {
            "pid": 202,
            "name": "Telegram",
            "executable": None,
        },
    ]
