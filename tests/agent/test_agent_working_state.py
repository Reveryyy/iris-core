from __future__ import annotations

import json

from app.agent.planner import AgentPlanner


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
