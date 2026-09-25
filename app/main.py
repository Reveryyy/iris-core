from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv


# ============================================================================
# DIRECT SCRIPT SUPPORT
# ============================================================================

if __package__ in {
    None,
    "",
}:
    sys.path.insert(
        0,
        str(
            Path(__file__).resolve().parent.parent
        ),
    )


from app.agent.loop import AgentLoop
from app.agent.planner import AgentPlanner
from app.core import IRISCore
from app.database import SessionLocal
from app.llm.anthropic import ClaudeProvider
from app.llm.gemma import GemmaProvider
from app.llm.openai_compatible import (
    OpenAICompatibleProvider,
)
from app.llm.router import LLMRouter
from app.memory.local_embedding import (
    LocalEmbeddingProvider,
)
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
from app.tools.pc_clipboard import (
    GetClipboardTool,
    SetClipboardTool,
)
from app.tools.pc_close import CloseApplicationTool
from app.tools.pc_discovery import (
    DiscoverPCStateTool,
)
from app.tools.pc_gui import TypeTextTool
from app.tools.pc_keyboard import PressKeyTool
from app.tools.pc_minimize import MinimizeWindowTool
from app.tools.pc_mouse import ClickMouseTool
from app.tools.pc_screenshot import ScreenshotTool
from app.tools.pc_state import GetForegroundWindowTool
from app.tools.pc_wait import WaitTool
from app.tools.pc_window import FocusWindowTool
from app.tools.permissions import (
    Permission,
    PermissionManager,
)
from app.tools.registry import ToolRegistry
from app.ui.events import IRISEventBus
from app.ui.terminal import TerminalUI


# ============================================================================
# OPTIONAL PROVIDERS
# ============================================================================

def _add_optional_provider(
    providers,
    provider_factory,
    key_env: str,
) -> None:
    if not os.getenv(key_env):
        return

    try:
        provider = provider_factory()

        providers.append(
            provider
        )

    except Exception as error:
        print(
            f"[LLM] Provider {key_env} non configurato: "
            f"{error}"
        )


# ============================================================================
# MAIN
# ============================================================================

def main() -> None:
    load_dotenv()

    event_bus = IRISEventBus()

    providers = []

    # =========================================================================
    # LOCAL
    # =========================================================================

    gemma = GemmaProvider()

    providers.append(
        gemma
    )

    # =========================================================================
    # GEMINI
    # =========================================================================

    _add_optional_provider(
        providers,
        lambda: OpenAICompatibleProvider(
            name="gemini",
            base_url=(
                "https://generativelanguage.googleapis.com/"
                "v1beta/openai"
            ),
            api_key_env="GEMINI_API_KEY",
            model="gemini-3.8-flash",
            timeout=90.0,
            strict_structured_outputs=False,
        ),
        "GEMINI_API_KEY",
    )

    # =========================================================================
    # GROQ
    # =========================================================================

    _add_optional_provider(
        providers,
        lambda: OpenAICompatibleProvider(
            name="groq",
            base_url="https://api.groq.com/openai/v1",
            api_key_env="GROQ_API_KEY",
            model="qwen/qwen3.8-27b",
            timeout=60.0,
            strict_structured_outputs=False,
        ),
        "GROQ_API_KEY",
    )

    # =========================================================================
    # MISTRAL
    # =========================================================================

    _add_optional_provider(
        providers,
        lambda: OpenAICompatibleProvider(
            name="mistral",
            base_url=(
                "https://api.mistral.ai/v1"
            ),
            api_key_env="MISTRAL_API_KEY",
            model="mistral-small-latest",
            timeout=90.0,
            strict_structured_outputs=True,
        ),
        "MISTRAL_API_KEY",
    )

    # =========================================================================
    # CEREBRAS
    # =========================================================================

    _add_optional_provider(
        providers,
        lambda: OpenAICompatibleProvider(
            name="cerebras",
            base_url=(
                "https://api.cerebras.ai/v1"
            ),
            api_key_env="CEREBRAS_API_KEY",
            model="gpt-oss-120b",
            timeout=60.0,
            strict_structured_outputs=False,
        ),
        "CEREBRAS_API_KEY",
    )

    # =========================================================================
    # OPENROUTER
    # =========================================================================

    _add_optional_provider(
        providers,
        lambda: OpenAICompatibleProvider(
            name="openrouter",
            base_url=(
                "https://openrouter.ai/api/v1"
            ),
            api_key_env="OPENROUTER_API_KEY",
            model="openrouter/free",
            timeout=120.0,
            strict_structured_outputs=True,
        ),
        "OPENROUTER_API_KEY",
    )

    # =========================================================================
    # CLAUDE
    # =========================================================================

    _add_optional_provider(
        providers,
        lambda: ClaudeProvider(),
        "ANTHROPIC_API_KEY",
    )

    # =========================================================================
    # ROUTER
    # =========================================================================

    router = LLMRouter(
        providers=providers,
        event_bus=event_bus,
    )

    # =========================================================================
    # TOOL REGISTRY
    # =========================================================================

    tool_registry = ToolRegistry()

    tool_registry.register(
        EchoTool()
    )

    iris_directory = Path.cwd()

    # =========================================================================
    # APPLICATION CONTROL
    # =========================================================================

    tool_registry.register(
        OpenApplicationTool()
    )

    tool_registry.register(
        CloseApplicationTool()
    )

    # =========================================================================
    # PC DISCOVERY
    # =========================================================================

    tool_registry.register(
        DiscoverPCStateTool()
    )

    # =========================================================================
    # WINDOW CONTROL
    # =========================================================================

    tool_registry.register(
        FocusWindowTool()
    )

    tool_registry.register(
        MinimizeWindowTool()
    )

    tool_registry.register(
        WaitTool()
    )

    tool_registry.register(
        GetForegroundWindowTool()
    )

    # =========================================================================
    # SCREEN / GUI
    # =========================================================================

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

    # =========================================================================
    # CLIPBOARD
    # =========================================================================

    tool_registry.register(
        GetClipboardTool()
    )

    tool_registry.register(
        SetClipboardTool()
    )

    # =========================================================================
    # FILESYSTEM
    # =========================================================================

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

    # =========================================================================
    # COMMAND EXECUTION
    # =========================================================================

    tool_registry.register(
        RunCommandTool()
    )

    # =========================================================================
    # PERMISSIONS
    # =========================================================================

    permission_manager = PermissionManager(
        granted={
            Permission.GUI,
            Permission.READ,
            Permission.WRITE,
            Permission.EXECUTE,
        }
    )

    # =========================================================================
    # TOOL SYSTEM
    # =========================================================================

    tool_dispatcher = ToolDispatcher(
        registry=tool_registry,
        permissions=permission_manager,
    )

    tool_execution_service = (
        ToolExecutionService(
            dispatcher=tool_dispatcher,
        )
    )

    tool_handler = CoreToolHandler(
        execution_service=tool_execution_service,
    )

    # =========================================================================
    # AGENT LOOP
    # =========================================================================

    agent_planner = AgentPlanner(
        router=router,
    )

    agent_loop = AgentLoop(
        planner=agent_planner,
        execution_service=tool_execution_service,
        event_bus=event_bus,
    )

    # =========================================================================
    # TERMINAL UI
    # =========================================================================

    terminal = TerminalUI(
        event_bus=event_bus,
        router=router,
        tool_registry=tool_registry,
        permission_manager=permission_manager,
    )

    # =========================================================================
    # DATABASE / MEMORY
    # =========================================================================

    with SessionLocal() as db:
        embedding_provider = (
            LocalEmbeddingProvider()
        )

        memory_manager = MemoryManager(
            db,
            embedding_provider=embedding_provider,
        )

        memory_service = MemoryService(
            memory_manager
        )

        # =====================================================================
        # CORE
        # =====================================================================

        core = IRISCore(
            router=router,
            memory=memory_service,
            tool_handler=tool_handler,
            agent_loop=agent_loop,
            event_bus=event_bus,
        )

        # =====================================================================
        # START UI
        # =====================================================================

        terminal.start()

        # =====================================================================
        # CALLBACKS
        # =====================================================================

        terminal.set_callbacks(
            chat_callback=lambda message: (
                core.chat(message)
            ),
            agent_callback=lambda goal: (
                core.run_agent(goal=goal)
            ),
        )

        # =====================================================================
        # START PERSISTENT UI
        # =====================================================================

        terminal.run_session(
            chat_callback=lambda message: (
                core.chat(message)
            ),
            agent_callback=lambda goal: (
                core.run_agent(goal=goal)
            ),
        )


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    main()