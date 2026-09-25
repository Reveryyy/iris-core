from __future__ import annotations

import json
from pathlib import PureWindowsPath

from app.agent.planner import AgentPlanner
from app.core import IRISCore


class FakeRouter:
    def generate(self, *args, **kwargs):
        return "{}"


WRITE_FILE_TOOLS = [
    {
        "name": "write_file",
        "description": "Scrive un file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
            "additionalProperties": False,
        },
    }
]


def test_file_creation_fallback_uses_recent_verified_directory() -> None:
    planner = AgentPlanner(FakeRouter())

    context = "\n".join(
        [
            "STATO OPERATIVO RECENTE:",
            json.dumps(
                {
                    "tool_name": "create_directory",
                    "arguments": {
                        "path": "/tmp/iris-test-dir",
                    },
                    "output": {
                        "path": "/tmp/iris-test-dir",
                        "created_or_existing": True,
                    },
                }
            ),
        ]
    )

    plan = planner._build_fallback_plan(
        goal="crea un file dentro quella cartella e scrivici del testo",
        tool_definitions=WRITE_FILE_TOOLS,
        context=context,
    )

    assert plan is not None
    assert plan.steps[0].tool_name == "write_file"
    assert plan.steps[0].arguments["path"].startswith(
        "/tmp/iris-test-dir/"
    )
    assert plan.steps[0].arguments["path"].endswith(".txt")
    assert plan.steps[0].arguments["content"]


def test_file_creation_fallback_accepts_explicit_filename_and_content() -> None:
    planner = AgentPlanner(FakeRouter())

    context = json.dumps(
        {
            "tool_name": "create_directory",
            "output": {
                "path": "/tmp/example",
            },
        }
    )

    plan = planner._build_fallback_plan(
        goal='crea un file chiamato prova.txt dentro quella cartella e scrivici "ciao IRIS"',
        tool_definitions=WRITE_FILE_TOOLS,
        context=context,
    )

    assert plan is not None
    assert plan.steps[0].arguments["path"] == "/tmp/example/prova.txt"
    assert plan.steps[0].arguments["content"] == "ciao IRIS"


def test_recent_directory_extraction_requires_verified_directory_shape() -> None:
    context = json.dumps(
        {
            "tool_name": "read_file",
            "output": {
                "path": "/tmp/a.txt",
            },
        }
    )

    assert AgentPlanner._extract_recent_directory(context) is None


def test_core_recent_agent_context_preserves_structured_observation_lines() -> None:
    core = object.__new__(IRISCore)
    core._recent_agent_state = [
        {
            "tool_name": "create_directory",
            "arguments": {"path": "/tmp/test-dir"},
            "output": {"path": "/tmp/test-dir", "created_or_existing": True},
        }
    ]

    context = core._build_recent_agent_context()

    lines = context.splitlines()

    assert lines[0] == "STATO OPERATIVO RECENTE:"
    assert json.loads(lines[2])["output"]["path"] == "/tmp/test-dir"


def test_directory_creation_fallback_uses_real_project_directory() -> None:
    planner = AgentPlanner(FakeRouter())

    context = (
        "AMBIENTE REALE DEL PROCESSO:\n"
        "- DIRECTORY DI LAVORO CORRENTE: C:\\Users\\picco\\IRIS\\iris-core\n"
        "- RADICE GIT DEL PROGETTO: C:\\Users\\picco\\IRIS\\iris-core\n"
    )

    plan = planner._build_fallback_plan(
        goal="crea una nuova cartella di test",
        tool_definitions=[
            {
                "name": "create_directory",
                "description": "Crea una directory.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                    },
                    "required": ["path"],
                    "additionalProperties": False,
                },
            }
        ],
        context=context,
    )

    assert plan is not None
    assert plan.steps[0].tool_name == "create_directory"
    path = plan.steps[0].arguments["path"]
    assert path.startswith(r"C:\Users\picco\IRIS\iris-core\")
    assert "workspace" not in path.lower()
    assert PureWindowsPath(path).name.startswith("iris-test-")


class WrongPathRouter:
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, *args, **kwargs):
        self.calls += 1
        return json.dumps(
            {
                "goal": "crea un file dentro quella cartella e scrivici del testo",
                "decision": "done",
                "message": None,
                "steps": [
                    {
                        "tool_name": "write_file",
                        "arguments": {
                            "path": r"C:\Users\picco\IRIS\iris-core\test",
                            "content": "test",
                        },
                        "description": "Scrivi il file.",
                        "success_criteria": "Il file esiste.",
                    }
                ],
            }
        )


def test_plan_prefers_verified_directory_over_llm_file_path() -> None:
    router = WrongPathRouter()
    planner = AgentPlanner(router)

    context = "\n".join(
        [
            "STATO OPERATIVO RECENTE:",
            json.dumps(
                {
                    "tool_name": "create_directory",
                    "arguments": {
                        "path": r"C:\Users\picco\IRIS\iris-core\test",
                    },
                    "output": {
                        "path": r"C:\Users\picco\IRIS\iris-core\test",
                        "created_or_existing": True,
                    },
                }
            ),
        ]
    )

    plan = planner.plan(
        goal="crea un file dentro quella cartella e scrivici del testo",
        context=context,
        tool_definitions=[
            {
                "name": "write_file",
                "description": "Scrive un file.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["path", "content"],
                    "additionalProperties": False,
                },
            }
        ],
    )

    assert router.calls == 0
    assert plan.steps[0].tool_name == "write_file"
    assert plan.steps[0].arguments["path"].startswith(
        r"C:\Users\picco\IRIS\iris-core\test\"
    )
    assert plan.steps[0].arguments["path"] != (
        r"C:\Users\picco\IRIS\iris-core\test"
    )
    assert plan.steps[0].arguments["content"] == "Testo creato da IRIS."
