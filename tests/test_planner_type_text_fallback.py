from __future__ import annotations

from app.agent.planner import AgentPlanner


TYPE_TEXT_TOOL = {
    "name": "type_text",
    "description": (
        "Inserisce testo Unicode nella finestra "
        "attualmente in primo piano."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
            },
        },
        "required": [
            "text",
        ],
        "additionalProperties": False,
    },
}


class BrokenRouter:
    def generate(
        self,
        *args,
        **kwargs,
    ) -> str:
        return "{invalid-json"


def test_type_text_fallback_handles_quoted_text() -> None:
    planner = AgentPlanner(
        BrokenRouter()
    )

    plan = planner.plan(
        goal='/agent scrivi "Ciao Valerio, questo è un test di IRIS!"',
        tool_definitions=[
            TYPE_TEXT_TOOL,
        ],
    )

    assert len(
        plan.steps
    ) == 1

    assert plan.steps[0].tool_name == "type_text"

    assert plan.steps[0].arguments == {
        "text": "Ciao Valerio, questo è un test di IRIS!",
    }


def test_type_text_fallback_handles_unicode_text() -> None:
    planner = AgentPlanner(
        BrokenRouter()
    )

    plan = planner.plan(
        goal='/agent scrivi "àèéìòù € 😀"',
        tool_definitions=[
            TYPE_TEXT_TOOL,
        ],
    )

    assert len(
        plan.steps
    ) == 1

    assert plan.steps[0].tool_name == "type_text"

    assert plan.steps[0].arguments == {
        "text": "àèéìòù € 😀",
    }


def test_type_text_fallback_handles_unquoted_text() -> None:
    planner = AgentPlanner(
        BrokenRouter()
    )

    plan = planner.plan(
        goal="/agent scrivi Ciao mondo",
        tool_definitions=[
            TYPE_TEXT_TOOL,
        ],
    )

    assert len(
        plan.steps
    ) == 1

    assert plan.steps[0].tool_name == "type_text"

    assert plan.steps[0].arguments == {
        "text": "Ciao mondo",
    }


def test_type_text_fallback_does_not_trigger_without_tool() -> None:
    planner = AgentPlanner(
        BrokenRouter()
    )

    plan = planner._build_gui_control_fallback(
        goal='/agent scrivi "Ciao"',
        tool_definitions=[],
    )

    assert plan is None