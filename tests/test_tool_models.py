from typing import Any

import pytest

from app.tools.call import ToolCall
from app.tools.result import ToolResult


def test_tool_call_accepts_valid_data():
    call = ToolCall(
        name="echo",
        arguments={"text": "ciao"},
    )

    assert call.name == "echo"
    assert call.arguments == {"text": "ciao"}
    assert call.to_dict() == {
        "name": "echo",
        "arguments": {"text": "ciao"},
    }


def test_tool_call_rejects_invalid_name():
    with pytest.raises(TypeError):
        ToolCall(name=123, arguments={})

    with pytest.raises(ValueError):
        ToolCall(name="   ", arguments={})


def test_tool_call_rejects_invalid_arguments():
    with pytest.raises(TypeError):
        ToolCall(name="echo", arguments=[])

    with pytest.raises(TypeError):
        ToolCall(name="echo", arguments="ciao")


def test_tool_call_from_dict_round_trip():
    source = {
        "name": "echo",
        "arguments": {"text": "ciao"},
    }

    call = ToolCall.from_dict(source)

    assert call.to_dict() == source


def test_tool_call_from_dict_rejects_invalid_data():
    with pytest.raises(TypeError):
        ToolCall.from_dict([])

    with pytest.raises(ValueError):
        ToolCall.from_dict({"arguments": {}})

    with pytest.raises(ValueError):
        ToolCall.from_dict({"name": "echo"})


def test_tool_result_success():
    result = ToolResult(
        success=True,
        output="ciao",
    )

    assert result.to_dict() == {
        "success": True,
        "output": "ciao",
        "error": None,
    }


def test_tool_result_failure():
    result = ToolResult(
        success=False,
        error="errore",
    )

    assert result.to_dict() == {
        "success": False,
        "output": None,
        "error": "errore",
    }


def test_tool_result_rejects_inconsistent_state():
    with pytest.raises(ValueError):
        ToolResult(
            success=True,
            output="ok",
            error="errore",
        )

    with pytest.raises(ValueError):
        ToolResult(
            success=False,
            output="ok",
            error=None,
        )


def test_tool_result_rejects_invalid_success_type():
    with pytest.raises(TypeError):
        ToolResult(
            success="true",
            output="ok",
        )


def test_tool_result_from_dict_round_trip():
    source = {
        "success": True,
        "output": {"value": 42},
        "error": None,
    }

    result = ToolResult.from_dict(source)

    assert result.to_dict() == source


def test_tool_result_from_dict_requires_success():
    with pytest.raises(ValueError):
        ToolResult.from_dict({"output": "ok"})


def test_tool_result_from_dict_rejects_non_dict():
    with pytest.raises(TypeError):
        ToolResult.from_dict("invalid")
