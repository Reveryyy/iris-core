from __future__ import annotations

from app.agent.planner import AgentPlanner


SET_CLIPBOARD_TOOL = {
    "name": "set_clipboard",
    "description": (
        "Copia testo Unicode negli appunti di Windows."
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


GET_CLIPBOARD_TOOL = {
    "name": "get_clipboard",
    "description": (
        "Legge il testo presente negli appunti di Windows."
    ),
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False,
    },
}


PRESS_KEY_TOOL = {
    "name": "press_key",
    "description": (
        "Premi una combinazione di tasti."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "key": {
                "type": "string",
            },
        },
        "required": [
            "key",
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


def test_copy_quoted_text_uses_set_clipboard() -> None:
    planner = AgentPlanner(
        BrokenRouter()
    )

    plan = planner.plan(
        goal='/agent copia "Ciao IRIS, questo è un test àèé € 😀"',
        tool_definitions=[
            SET_CLIPBOARD_TOOL,
            GET_CLIPBOARD_TOOL,
            PRESS_KEY_TOOL,
        ],
    )

    assert len(
        plan.steps
    ) == 1

    assert plan.steps[0].tool_name == "set_clipboard"

    assert plan.steps[0].arguments == {
        "text": "Ciao IRIS, questo è un test àèé € 😀",
    }


def test_quoted_comma_does_not_make_goal_multi_step() -> None:
    planner = AgentPlanner(
        BrokenRouter()
    )

    assert (
        planner._looks_like_multi_step_goal(
            '/agent copia "Ciao IRIS, questo è un test"'
        )
        is False
    )


def test_copy_selected_content_uses_ctrl_c() -> None:
    planner = AgentPlanner(
        BrokenRouter()
    )

    plan = planner.plan(
        goal="/agent copia il testo",
        tool_definitions=[
            SET_CLIPBOARD_TOOL,
            PRESS_KEY_TOOL,
        ],
    )

    assert len(
        plan.steps
    ) == 1

    assert plan.steps[0].tool_name == "press_key"

    assert plan.steps[0].arguments == {
        "key": "CTRL+C",
    }


def test_paste_uses_ctrl_v() -> None:
    planner = AgentPlanner(
        BrokenRouter()
    )

    plan = planner.plan(
        goal="/agent incolla",
        tool_definitions=[
            PRESS_KEY_TOOL,
        ],
    )

    assert len(
        plan.steps
    ) == 1

    assert plan.steps[0].tool_name == "press_key"

    assert plan.steps[0].arguments == {
        "key": "CTRL+V",
    }


def test_get_clipboard_uses_get_clipboard_tool() -> None:
    planner = AgentPlanner(
        BrokenRouter()
    )

    plan = planner.plan(
        goal="/agent leggi gli appunti",
        tool_definitions=[
            GET_CLIPBOARD_TOOL,
        ],
    )

    assert len(
        plan.steps
    ) == 1

    assert plan.steps[0].tool_name == "get_clipboard"

    assert plan.steps[0].arguments == {}


def test_clipboard_fallback_requires_registered_tool() -> None:
    planner = AgentPlanner(
        BrokenRouter()
    )

    plan = planner._build_gui_control_fallback(
        goal='/agent copia "Ciao"',
        tool_definitions=[],
    )

    assert plan is None


def test_copy_text_fallback_is_not_used_for_known_ctrl_c_phrase() -> None:
    planner = AgentPlanner(
        BrokenRouter()
    )

    plan = planner._build_gui_control_fallback(
        goal="/agent copia il contenuto",
        tool_definitions=[
            SET_CLIPBOARD_TOOL,
            PRESS_KEY_TOOL,
        ],
    )

    assert plan is not None

    assert len(
        plan.steps
    ) == 1

    assert plan.steps[0].tool_name == "press_key"

    assert plan.steps[0].arguments == {
        "key": "CTRL+C",
    }