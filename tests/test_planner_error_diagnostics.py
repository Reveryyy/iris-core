from __future__ import annotations

import json

import pytest

from app.agent.planner import AgentPlanner


class FakeRouter:
    def generate(self, *args, **kwargs):
        return "{invalid-json"


def test_planner_error_includes_root_cause_type_and_message():
    planner = AgentPlanner(FakeRouter())

    with pytest.raises(ValueError) as captured:
        planner.plan(
            goal="scrivi qualcosa",
            tool_definitions=[],
        )

    error = captured.value

    assert "Il planner non ha prodotto un piano eseguibile" in str(error)
    assert "Errore: ValueError:" in str(error)
    assert "Il planner non ha restituito un JSON valido." in str(error)
    assert "causa: JSONDecodeError:" in str(error)
    assert isinstance(error.__cause__, ValueError)
    assert isinstance(error.__cause__.__cause__, json.JSONDecodeError)
