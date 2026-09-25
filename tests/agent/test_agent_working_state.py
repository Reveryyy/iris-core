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
    assert len(plan.steps) == 1
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
    assert path.startswith("C:\\Users\\picco\\IRIS\\iris-core\\")
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
        "C:\\Users\\picco\\IRIS\\iris-core\\test\\"
    )
    assert plan.steps[0].arguments["path"] != (
        r"C:\Users\picco\IRIS\iris-core\test"
    )
    assert plan.steps[0].arguments["content"] == "Testo creato da IRIS."


class CopyRouter:
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, *args, **kwargs):
        self.calls += 1
        return json.dumps(
            {
                "goal": "copia quel file in un'altra posizione",
                "decision": "ask_user",
                "message": "Specifica la destinazione.",
                "steps": [
                    {
                        "tool_name": "copy_path",
                        "arguments": {
                            "source": r"C:\Users\picco\IRIS\iris-core\test\file.txt",
                            "destination": "",
                        },
                        "description": "Copia il file.",
                        "success_criteria": "Il file è copiato.",
                    }
                ],
            }
        )


def test_generic_copy_uses_recent_file_and_project_root() -> None:
    router = CopyRouter()
    planner = AgentPlanner(router)

    source = r"C:\Users\picco\IRIS\iris-core\test\file.txt"
    root = r"C:\Users\picco\IRIS\iris-core"

    context = "\n".join(
        [
            "STATO OPERATIVO RECENTE:",
            json.dumps(
                {
                    "tool_name": "read_file",
                    "arguments": {"path": source},
                    "output": {
                        "path": source,
                        "content": "Testo creato da IRIS.",
                    },
                }
            ),
            "AMBIENTE REALE DEL PROCESSO:",
            f"- RADICE GIT DEL PROGETTO: {root}",
        ]
    )

    plan = planner.plan(
        goal="copia quel file in un'altra posizione",
        context=context,
        tool_definitions=[
            {
                "name": "copy_path",
                "description": "Copia un file.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "source": {"type": "string"},
                        "destination": {"type": "string"},
                    },
                    "required": ["source", "destination"],
                    "additionalProperties": False,
                },
            }
        ],
    )

    assert router.calls == 0
    assert plan.steps[0].tool_name == "copy_path"
    assert plan.steps[0].arguments["source"] == source
    destination = plan.steps[0].arguments["destination"]
    assert destination.startswith(root + "\\")
    assert destination != source
    assert PureWindowsPath(destination).suffix == ".txt"


def test_generic_copy_creates_secondary_directory_when_project_root_is_source_parent() -> None:
    planner = AgentPlanner(CopyRouter())

    source = r"C:\Users\picco\IRIS\iris-core\file.txt"
    root = r"C:\Users\picco\IRIS\iris-core"

    context = "\n".join(
        [
            "STATO OPERATIVO RECENTE:",
            json.dumps(
                {
                    "tool_name": "read_file",
                    "arguments": {"path": source},
                    "output": {"path": source},
                }
            ),
            "AMBIENTE REALE DEL PROCESSO:",
            f"- RADICE GIT DEL PROGETTO: {root}",
        ]
    )

    plan = planner.plan(
        goal="copia quel file in un'altra posizione",
        context=context,
        tool_definitions=[
            {
                "name": "copy_path",
                "description": "Copia un file.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "source": {"type": "string"},
                        "destination": {"type": "string"},
                    },
                    "required": ["source", "destination"],
                    "additionalProperties": False,
                },
            },
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
            },
        ],
    )

    assert plan.steps[0].tool_name == "create_directory"
    assert plan.steps[1].tool_name == "copy_path"
    assert plan.steps[1].arguments["source"] == source


class MoveRouter:
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, *args, **kwargs):
        self.calls += 1
        return json.dumps(
            {
                "goal": "sposta quel file",
                "decision": "done",
                "message": None,
                "steps": [
                    {
                        "tool_name": "copy_path",
                        "arguments": {
                            "source": r"C:\Users\picco\IRIS\iris-core\test\file.txt",
                            "destination": r"C:\Users\picco\IRIS\iris-core\test\file.txt",
                        },
                        "description": "Copia il file.",
                        "success_criteria": "Il file è disponibile.",
                    }
                ],
            }
        )




def test_move_request_with_agent_prefix_never_uses_copy() -> None:
    planner = AgentPlanner(MoveRouter())

    source = r"C:\Users\picco\IRIS\iris-core\test\file.txt"
    root = r"C:\Users\picco\IRIS\iris-core"

    context = "\n".join(
        [
            "STATO OPERATIVO RECENTE:",
            json.dumps(
                {
                    "tool_name": "write_file",
                    "arguments": {"path": source},
                    "output": {"path": source},
                }
            ),
            "AMBIENTE REALE DEL PROCESSO:",
            f"- RADICE GIT DEL PROGETTO: {root}",
        ]
    )

    plan = planner.plan(
        goal="/agent sposta quel file",
        context=context,
        tool_definitions=[
            {
                "name": "copy_path",
                "description": "Copia un file.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "source": {"type": "string"},
                        "destination": {"type": "string"},
                    },
                    "required": ["source", "destination"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "move_path",
                "description": "Sposta un file.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "source": {"type": "string"},
                        "destination": {"type": "string"},
                    },
                    "required": ["source", "destination"],
                    "additionalProperties": False,
                },
            },
        ],
    )

    assert plan.steps[0].tool_name == "create_directory"
    assert plan.steps[1].tool_name == "move_path"
    assert plan.steps[1].arguments["source"] == source
    destination = PureWindowsPath(plan.steps[1].arguments["destination"])
    assert destination.parent != PureWindowsPath(source).parent
    assert destination.name == PureWindowsPath(source).name
    assert str(destination.parent).startswith(root + "\\")


def test_move_request_uses_recent_copy_destination() -> None:
    router = MoveRouter()
    planner = AgentPlanner(router)

    source = r"C:\Users\picco\IRIS\iris-core\test\file.txt"
    copied = r"C:\Users\picco\IRIS\iris-core\file-copy.txt"
    root = r"C:\Users\picco\IRIS\iris-core"

    context = "\n".join(
        [
            "STATO OPERATIVO RECENTE:",
            json.dumps(
                {
                    "tool_name": "copy_path",
                    "arguments": {
                        "source": source,
                        "destination": copied,
                    },
                    "output": {
                        "source": source,
                        "destination": copied,
                        "verified_destination_exists": True,
                    },
                }
            ),
            "AMBIENTE REALE DEL PROCESSO:",
            f"- RADICE GIT DEL PROGETTO: {root}",
        ]
    )

    plan = planner.plan(
        goal="sposta quel file",
        context=context,
        tool_definitions=[
            {
                "name": "copy_path",
                "description": "Copia un file.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "source": {"type": "string"},
                        "destination": {"type": "string"},
                    },
                    "required": ["source", "destination"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "move_path",
                "description": "Sposta un file.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "source": {"type": "string"},
                        "destination": {"type": "string"},
                    },
                    "required": ["source", "destination"],
                    "additionalProperties": False,
                },
            },
        ],
    )

    assert router.calls == 0
    assert plan.steps[0].tool_name == "create_directory"
    assert plan.steps[1].tool_name == "move_path"
    assert plan.steps[1].arguments["source"] == copied
    destination = PureWindowsPath(plan.steps[1].arguments["destination"])
    assert destination.parent != PureWindowsPath(copied).parent
    assert destination.name == PureWindowsPath(copied).name


def test_move_request_discovers_described_file_after_session_restart() -> None:
    router = MoveRouter()
    planner = AgentPlanner(router)

    root = r"C:\Users\picco\IRIS\iris-core"

    plan = planner.plan(
        goal="Sposta il file di test in un altra posizione",
        context=(
            "AMBIENTE REALE DEL PROCESSO:\n"
            f"- RADICE GIT DEL PROGETTO: {root}\n"
        ),
        tool_definitions=[
            {
                "name": "search_files",
                "description": "Cerca file.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "location": {"type": "string"},
                        "include_directories": {"type": "boolean"},
                        "case_sensitive": {"type": "boolean"},
                    },
                    "required": ["query", "location"],
                    "additionalProperties": False,
                },
            },
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
            },
            {
                "name": "move_path",
                "description": "Sposta un file.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "source": {"type": "string"},
                        "destination": {"type": "string"},
                    },
                    "required": ["source", "destination"],
                    "additionalProperties": False,
                },
            },
        ],
    )

    assert router.calls == 0
    assert len(plan.steps) == 1
    assert plan.steps[0].tool_name == "search_files"
    assert plan.steps[0].arguments["query"] == "*test*"
    assert plan.steps[0].arguments["location"] == root


def test_move_request_uses_unique_search_result_as_source() -> None:
    planner = AgentPlanner(MoveRouter())

    source = r"C:\Users\picco\IRIS\iris-core\test_file4598589343584980934093540934.txt"
    root = r"C:\Users\picco\IRIS\iris-core"

    context = "\n".join(
        [
            "AMBIENTE REALE DEL PROCESSO:",
            f"- RADICE GIT DEL PROGETTO: {root}",
            "STATO ESECUZIONE:",
            json.dumps(
                {
                    "tool_name": "search_files",
                    "arguments": {
                        "query": "*test*",
                        "location": root,
                    },
                    "output": {
                        "query": "*test*",
                        "location": root,
                        "results": [
                            {
                                "path": source,
                                "name": "test_file4598589343584980934093540934.txt",
                                "type": "file",
                                "is_file": True,
                                "is_directory": False,
                            }
                        ],
                        "count": 1,
                    },
                }
            ),
        ]
    )

    plan = planner.plan(
        goal="Sposta il file di test in un altra posizione",
        context=context,
        tool_definitions=[
            {
                "name": "search_files",
                "description": "Cerca file.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "location": {"type": "string"},
                        "include_directories": {"type": "boolean"},
                        "case_sensitive": {"type": "boolean"},
                    },
                    "required": ["query", "location"],
                    "additionalProperties": False,
                },
            },
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
            },
            {
                "name": "move_path",
                "description": "Sposta un file.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "source": {"type": "string"},
                        "destination": {"type": "string"},
                    },
                    "required": ["source", "destination"],
                    "additionalProperties": False,
                },
            },
        ],
    )

    assert len(plan.steps) == 2
    assert plan.steps[0].tool_name == "create_directory"
    assert plan.steps[1].tool_name == "move_path"
    assert plan.steps[1].arguments["source"] == source
    assert PureWindowsPath(plan.steps[1].arguments["destination"]).parent != PureWindowsPath(source).parent


def test_move_request_never_degrades_to_copy() -> None:
    router = MoveRouter()
    planner = AgentPlanner(router)

    source = r"C:\Users\picco\IRIS\iris-core\test\file.txt"
    root = r"C:\Users\picco\IRIS\iris-core"

    context = "\n".join(
        [
            "STATO OPERATIVO RECENTE:",
            json.dumps(
                {
                    "tool_name": "read_file",
                    "arguments": {"path": source},
                    "output": {
                        "path": source,
                        "content": "Testo creato da IRIS.",
                    },
                }
            ),
            "AMBIENTE REALE DEL PROCESSO:",
            f"- RADICE GIT DEL PROGETTO: {root}",
        ]
    )

    plan = planner.plan(
        goal="sposta quel file",
        context=context,
        tool_definitions=[
            {
                "name": "copy_path",
                "description": "Copia un file.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "source": {"type": "string"},
                        "destination": {"type": "string"},
                    },
                    "required": ["source", "destination"],
                    "additionalProperties": False,
                },
            },
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
            },
            {
                "name": "move_path",
                "description": "Sposta un file.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "source": {"type": "string"},
                        "destination": {"type": "string"},
                    },
                    "required": ["source", "destination"],
                    "additionalProperties": False,
                },
            },
        ],
    )

    assert router.calls == 0
    assert plan.steps[0].tool_name == "create_directory"
    assert plan.steps[1].tool_name == "move_path"
    assert plan.steps[1].arguments["source"] == source
    assert plan.steps[1].arguments["destination"].startswith(root + "\\")
    assert PureWindowsPath(plan.steps[1].arguments["destination"]).parent != PureWindowsPath(source).parent


def test_move_request_accepts_descriptive_file_reference() -> None:
    router = MoveRouter()
    planner = AgentPlanner(router)

    source = r"C:\Users\picco\IRIS\iris-core\test\file.txt"
    root = r"C:\Users\picco\IRIS\iris-core"

    context = "\n".join(
        [
            "STATO OPERATIVO RECENTE:",
            json.dumps(
                {
                    "tool_name": "read_file",
                    "arguments": {"path": source},
                    "output": {
                        "path": source,
                        "content": "Testo creato da IRIS.",
                    },
                }
            ),
            "AMBIENTE REALE DEL PROCESSO:",
            f"- RADICE GIT DEL PROGETTO: {root}",
        ]
    )

    plan = planner.plan(
        goal="Sposta il file di test in un altra posizione",
        context=context,
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
            },
            {
                "name": "move_path",
                "description": "Sposta un file.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "source": {"type": "string"},
                        "destination": {"type": "string"},
                    },
                    "required": ["source", "destination"],
                    "additionalProperties": False,
                },
            },
        ],
    )

    assert router.calls == 0
    assert len(plan.steps) == 2
    assert plan.steps[0].tool_name == "create_directory"
    assert plan.steps[1].tool_name == "move_path"
    assert plan.steps[1].arguments["source"] == source
    destination = PureWindowsPath(plan.steps[1].arguments["destination"])
    assert destination.parent != PureWindowsPath(source).parent
    assert destination.name == PureWindowsPath(source).name
