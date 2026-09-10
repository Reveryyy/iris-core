from pathlib import Path

from app.agent.loop import AgentLoop
from app.agent.planner import AgentPlanner
from app.core import IRISCore
from app.database import SessionLocal
from app.llm.gemma import GemmaProvider
from app.llm.router import LLMRouter
from app.memory.local_embedding import LocalEmbeddingProvider
from app.memory.manager import MemoryManager
from app.memory.service import MemoryService
from app.tools.builtin import EchoTool
from app.tools.core import CoreToolHandler
from app.tools.dispatcher import ToolDispatcher
from app.tools.executor import ToolExecutionService
from app.tools.pc import (
    OpenApplicationTool,
    ReadFileTool,
    RunCommandTool,
    WriteFileTool,
)
from app.tools.pc_gui import TypeTextTool
from app.tools.pc_keyboard import PressKeyTool
from app.tools.pc_mouse import ClickMouseTool
from app.tools.pc_screenshot import ScreenshotTool
from app.tools.pc_state import GetForegroundWindowTool
from app.tools.pc_window import FocusWindowTool
from app.tools.permissions import Permission, PermissionManager
from app.tools.registry import ToolRegistry


def main() -> None:
    gemma = GemmaProvider()

    router = LLMRouter(
        providers=[
            gemma,
        ]
    )

    tool_registry = ToolRegistry()

    tool_registry.register(
        EchoTool()
    )

    iris_directory = Path.cwd()

    tool_registry.register(
        OpenApplicationTool(
            allowed_applications={
                "notepad": "notepad.exe",
                "blocco note": "notepad.exe",
                "editor di testo": "notepad.exe",
                "calcolatrice": "calc.exe",
                "calculator": "calc.exe",
                "calcolatrice di Windows": "calc.exe",
            }
        )
    )

    tool_registry.register(
        FocusWindowTool()
    )

    tool_registry.register(
        GetForegroundWindowTool()
    )

    tool_registry.register(
        ScreenshotTool(
            allowed_root=iris_directory,
        )
    )

    tool_registry.register(
        TypeTextTool()
    )

    tool_registry.register(
        ClickMouseTool()
    )

    tool_registry.register(
        PressKeyTool()
    )

    tool_registry.register(
        ReadFileTool(
            allowed_roots=[
                iris_directory,
            ]
        )
    )

    tool_registry.register(
        WriteFileTool(
            allowed_roots=[
                iris_directory,
            ]
        )
    )

    tool_registry.register(
        RunCommandTool(
            allowed_commands={
                "python_version": [
                    "python",
                    "--version",
                ],
                "whoami": [
                    "whoami",
                ],
            }
        )
    )

    permission_manager = PermissionManager(
        granted={
            Permission.GUI,
            Permission.READ,
            Permission.WRITE,
            Permission.EXECUTE,
        }
    )

    tool_dispatcher = ToolDispatcher(
        registry=tool_registry,
        permissions=permission_manager,
    )

    tool_execution_service = ToolExecutionService(
        dispatcher=tool_dispatcher,
    )

    tool_handler = CoreToolHandler(
        execution_service=tool_execution_service,
    )

    agent_planner = AgentPlanner(
        router=router,
    )

    agent_loop = AgentLoop(
        planner=agent_planner,
        execution_service=tool_execution_service,
    )

    with SessionLocal() as db:
        embedding_provider = LocalEmbeddingProvider()

        memory_manager = MemoryManager(
            db,
            embedding_provider=embedding_provider,
        )

        memory_service = MemoryService(
            memory_manager
        )

        core = IRISCore(
            router=router,
            memory=memory_service,
            tool_handler=tool_handler,
            agent_loop=agent_loop,
        )

        print("I.R.I.S. avviata.")
        print("Scrivi 'exit' per uscire.")
        print("Usa '/agent <obiettivo>' per usare l'Agent Loop.")

        while True:
            user_input = input("Tu: ").strip()

            if user_input.lower() == "exit":
                print("I.R.I.S. chiusa.")
                break

            if not user_input:
                continue

            if user_input.startswith("/agent"):
                goal = user_input[
                    len("/agent"):
                ].strip()

                if not goal:
                    print(
                        "I.R.I.S: specifica un obiettivo dopo "
                        "'/agent'."
                    )
                    continue

                try:
                    result = core.run_agent(
                        goal=goal,
                    )

                    print(
                        f"I.R.I.S: {result.message}"
                    )

                    print(
                        f"[Agent: {result.decision.value} | "
                        f"step: {len(result.steps)} | "
                        f"planner: {result.planner_calls}]"
                    )

                    print(
                        f"[Tempo: totale {result.total_seconds:.2f}s | "
                        f"planning {result.planning_seconds:.2f}s | "
                        f"tool {result.execution_seconds:.4f}s | "
                        f"verifica {result.verification_seconds:.4f}s]"
                    )

                except Exception as error:
                    print(
                        f"I.R.I.S: Errore Agent Loop: {error}"
                    )

                continue

            try:
                risposta = core.chat(
                    user_input
                )

                print(
                    f"I.R.I.S: {risposta}"
                )

            except Exception as error:
                print(
                    f"I.R.I.S: Errore: {error}"
                )


if __name__ == "__main__":
    main()