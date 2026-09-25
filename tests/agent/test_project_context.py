from __future__ import annotations

from app.agent.planner import AgentPlanner
from app.core import IRISCore


class FakeRouter:
    def generate(self, *args, **kwargs):
        return "{}"


class FakeMemory:
    def search_semantic(self, query: str, limit: int = 5):
        return []

    def search_by_type(self, memory_type: str):
        return []


def test_runtime_agent_context_contains_real_working_directory(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "app.core.os.getcwd",
        lambda: r"C:\Users\picco\IRIS\iris-core",
    )

    context = IRISCore._build_runtime_agent_context()

    assert (
        r"DIRECTORY DI LAVORO CORRENTE: C:\Users\picco\IRIS\iris-core"
        in context
    )


def test_planner_forbids_invented_project_paths() -> None:
    planner = AgentPlanner(
        router=FakeRouter(),
    )

    prompt = planner._build_system_prompt(
        tool_definitions=[],
        context=(
            "AMBIENTE REALE DEL PROCESSO:\n"
            "DIRECTORY DI LAVORO CORRENTE: C:\\Users\\picco\\IRIS\\iris-core"
        ),
        observations=None,
    )

    assert "RADICE GIT DEL PROGETTO" in prompt
    assert "non inventare mai percorsi" in prompt
    assert "non sintetizzare o inventare percorsi assoluti" in prompt
