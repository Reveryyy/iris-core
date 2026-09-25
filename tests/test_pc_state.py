from __future__ import annotations

from app.agent.pc_state import (
    PCState,
    RunningProcess,
)


def test_pc_state_context_can_include_all_processes() -> None:
    state = PCState(
        platform="Windows",
        hostname="test-host",
        username="test-user",
    )

    state.processes.extend(
        RunningProcess(
            pid=index,
            name=f"process-{index}",
        )
        for index in range(100)
    )

    context = state.to_context()

    for index in range(100):
        assert f"process-{index}" in context
