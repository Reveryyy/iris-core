
from app.tools.builtin import EchoTool
from app.tools.system import ToolSystem


def create_tool_system() -> ToolSystem:
    """
    Crea il Tool System standard di IRIS.

    I tool built-in vengono registrati automaticamente.
    """

    system = ToolSystem()

    system.register(
        EchoTool()
    )

    return system

