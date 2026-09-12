from app.tools.application_resolver import ApplicationResolver
from app.tools.permissions import Permission
from app.tools.pc import OpenApplicationTool


def test_open_application_definition_requires_gui_permission() -> None:
    resolver = ApplicationResolver()
    tool = OpenApplicationTool(resolver=resolver)

    definition = tool.definition

    assert definition.name == "open_application"
    assert Permission.GUI.value in definition.permissions


def test_open_application_rejects_unknown_application() -> None:
    resolver = ApplicationResolver()

    tool = OpenApplicationTool(resolver=resolver)

    result = tool.execute(
        {"name": "questa applicazione sicuramente non esiste 123456"}
    )

    assert result.success is False
    assert result.error is not None
    assert "non riesco a trovare" in result.error.lower()


def test_open_application_accepts_resolver() -> None:
    resolver = ApplicationResolver()
    tool = OpenApplicationTool(resolver=resolver)

    assert tool.resolver is resolver