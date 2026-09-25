from __future__ import annotations

from app.agent.decision import AgentDecision
from app.agent.loop import AgentLoop
from app.agent.planner import AgentPlan, AgentPlanStep
from app.tools.call import ToolCall
from app.tools.result import ToolResult


class ReplayPlanner:
    def __init__(self) -> None:
        self.calls = 0

    def plan(self, **kwargs):
        self.calls += 1

        return AgentPlan(
            goal=kwargs["goal"],
            steps=(
                AgentPlanStep(
                    tool_name="search_files",
                    arguments={
                        "query": "*test*file*",
                        "location": r"C:\test",
                    },
                    description="Cerca il file.",
                    success_criteria="La ricerca termina correttamente.",
                ),
            ),
            decision=AgentDecision.CONTINUE,
            message=None,
        )


class SuccessfulExecutionService:
    def execute_call(
        self,
        tool_call: ToolCall,
        confirmed: bool = False,
    ) -> ToolResult:
        return ToolResult(
            success=True,
            output={
                "query": tool_call.arguments["query"],
                "location": tool_call.arguments["location"],
                "results": [],
                "count": 0,
            },
        )


def test_replay_only_replan_never_becomes_done() -> None:
    planner = ReplayPlanner()

    loop = AgentLoop(
        planner=planner,
        execution_service=SuccessfulExecutionService(),
    )

    result = loop.run(
        goal="Sposta il file di test in un altra posizione",
        context="AMBIENTE REALE DEL PROCESSO:",
        tool_definitions=[
            {
                "name": "search_files",
                "description": "Cerca file.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "location": {"type": "string"},
                    },
                    "required": ["query", "location"],
                    "additionalProperties": False,
                },
            },
        ],
    )

    assert planner.calls == 2
    assert result.decision == AgentDecision.ASK_USER
    assert result.completed is False
    assert len(result.steps) == 1
