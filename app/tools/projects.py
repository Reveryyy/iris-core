from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.projects.manager import ProjectManager
from app.tools.base import Tool, ToolDefinition
from app.tools.permissions import Permission
from app.tools.result import ToolResult


class CreateProjectTool(Tool):
    def __init__(self, manager: ProjectManager):
        self.manager = manager
        self._definition = ToolDefinition(
            name="create_project",
            description=(
                "Crea un nuovo progetto persistente nel database di IRIS. "
                "Usalo quando l'utente vuole iniziare o registrare un progetto."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["name"],
                "additionalProperties": False,
            },
            risk_level="medium",
            permissions=frozenset({Permission.WRITE.value}),
        )

    @property
    def definition(self) -> ToolDefinition:
        return self._definition

    def execute(self, arguments: dict[str, Any]) -> ToolResult:
        try:
            project = self.manager.create_project(
                name=arguments.get("name"),
                description=arguments.get("description"),
            )
            return ToolResult(
                success=True,
                output={
                    "project": _project_dict(project),
                    "user_message": f"Ho creato il progetto '{project.name}'.",
                },
            )
        except (TypeError, ValueError) as error:
            return ToolResult(success=False, error=str(error))


class ListProjectsTool(Tool):
    def __init__(self, manager: ProjectManager):
        self.manager = manager
        self._definition = ToolDefinition(
            name="list_projects",
            description=(
                "Elenca i progetti persistenti di IRIS, opzionalmente filtrati per stato."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["active", "completed", "archived"],
                    },
                },
                "required": [],
                "additionalProperties": False,
            },
            risk_level="low",
            permissions=frozenset({Permission.READ.value}),
        )

    @property
    def definition(self) -> ToolDefinition:
        return self._definition

    def execute(self, arguments: dict[str, Any]) -> ToolResult:
        try:
            projects = self.manager.list_projects(
                status=arguments.get("status"),
            )
            return ToolResult(
                success=True,
                output={
                    "count": len(projects),
                    "projects": [_project_dict(project) for project in projects],
                    "user_message": _projects_message(projects),
                },
            )
        except (TypeError, ValueError) as error:
            return ToolResult(success=False, error=str(error))


class UpdateProjectTool(Tool):
    def __init__(self, manager: ProjectManager):
        self.manager = manager
        self._definition = ToolDefinition(
            name="update_project",
            description=(
                "Aggiorna nome, descrizione o stato di un progetto esistente."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "project_id": {"type": "integer", "minimum": 1},
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "status": {
                        "type": "string",
                        "enum": ["active", "completed", "archived"],
                    },
                },
                "required": ["project_id"],
                "additionalProperties": False,
            },
            risk_level="medium",
            permissions=frozenset({Permission.WRITE.value}),
        )

    @property
    def definition(self) -> ToolDefinition:
        return self._definition

    def execute(self, arguments: dict[str, Any]) -> ToolResult:
        try:
            project = self.manager.update_project(
                project_id=arguments["project_id"],
                name=arguments.get("name"),
                description=arguments.get("description"),
                status=arguments.get("status"),
            )
            if project is None:
                return ToolResult(
                    success=False,
                    error=f"Progetto con ID {arguments['project_id']} non trovato.",
                )
            return ToolResult(
                success=True,
                output={
                    "project": _project_dict(project),
                    "user_message": f"Ho aggiornato il progetto '{project.name}'.",
                },
            )
        except (TypeError, ValueError) as error:
            return ToolResult(success=False, error=str(error))


class CreateTaskTool(Tool):
    def __init__(self, manager: ProjectManager):
        self.manager = manager
        self._definition = ToolDefinition(
            name="create_task",
            description=(
                "Crea un task persistente, collegandolo opzionalmente a un progetto."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "project_id": {"type": "integer", "minimum": 1},
                    "description": {"type": "string"},
                    "priority": {
                        "type": "string",
                        "enum": ["low", "medium", "high", "urgent"],
                    },
                    "due_at": {
                        "type": "string",
                        "description": "Data/ora ISO 8601, per esempio 2026-10-10T18:00:00+02:00.",
                    },
                },
                "required": ["title"],
                "additionalProperties": False,
            },
            risk_level="medium",
            permissions=frozenset({Permission.WRITE.value}),
        )

    @property
    def definition(self) -> ToolDefinition:
        return self._definition

    def execute(self, arguments: dict[str, Any]) -> ToolResult:
        try:
            task = self.manager.create_task(
                title=arguments.get("title"),
                project_id=arguments.get("project_id"),
                description=arguments.get("description"),
                priority=arguments.get("priority", "medium"),
                due_at=_parse_datetime(arguments.get("due_at")),
            )
            return ToolResult(
                success=True,
                output={
                    "task": _task_dict(task),
                    "user_message": f"Ho creato il task '{task.title}'.",
                },
            )
        except (TypeError, ValueError) as error:
            return ToolResult(success=False, error=str(error))


class ListTasksTool(Tool):
    def __init__(self, manager: ProjectManager):
        self.manager = manager
        self._definition = ToolDefinition(
            name="list_tasks",
            description=(
                "Elenca i task persistenti, opzionalmente filtrati per progetto o stato."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "project_id": {"type": "integer", "minimum": 1},
                    "status": {
                        "type": "string",
                        "enum": ["todo", "in_progress", "completed", "cancelled"],
                    },
                },
                "required": [],
                "additionalProperties": False,
            },
            risk_level="low",
            permissions=frozenset({Permission.READ.value}),
        )

    @property
    def definition(self) -> ToolDefinition:
        return self._definition

    def execute(self, arguments: dict[str, Any]) -> ToolResult:
        try:
            tasks = self.manager.list_tasks(
                project_id=arguments.get("project_id"),
                status=arguments.get("status"),
            )
            return ToolResult(
                success=True,
                output={
                    "count": len(tasks),
                    "tasks": [_task_dict(task) for task in tasks],
                    "user_message": _tasks_message(tasks),
                },
            )
        except (TypeError, ValueError) as error:
            return ToolResult(success=False, error=str(error))


class UpdateTaskTool(Tool):
    def __init__(self, manager: ProjectManager):
        self.manager = manager
        self._definition = ToolDefinition(
            name="update_task",
            description=(
                "Aggiorna un task esistente. Usa status='completed' per segnare un task come completato."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "integer", "minimum": 1},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "project_id": {"type": "integer", "minimum": 1},
                    "status": {
                        "type": "string",
                        "enum": ["todo", "in_progress", "completed", "cancelled"],
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["low", "medium", "high", "urgent"],
                    },
                    "due_at": {
                        "type": "string",
                        "description": "Data/ora ISO 8601.",
                    },
                },
                "required": ["task_id"],
                "additionalProperties": False,
            },
            risk_level="medium",
            permissions=frozenset({Permission.WRITE.value}),
        )

    @property
    def definition(self) -> ToolDefinition:
        return self._definition

    def execute(self, arguments: dict[str, Any]) -> ToolResult:
        try:
            task = self.manager.update_task(
                task_id=arguments["task_id"],
                title=arguments.get("title"),
                description=arguments.get("description"),
                project_id=arguments.get("project_id"),
                status=arguments.get("status"),
                priority=arguments.get("priority"),
                due_at=_parse_datetime(arguments.get("due_at")),
            )
            if task is None:
                return ToolResult(
                    success=False,
                    error=f"Task con ID {arguments['task_id']} non trovato.",
                )
            return ToolResult(
                success=True,
                output={
                    "task": _task_dict(task),
                    "user_message": f"Ho aggiornato il task '{task.title}'.",
                },
            )
        except (TypeError, ValueError) as error:
            return ToolResult(success=False, error=str(error))


def _project_dict(project) -> dict[str, Any]:
    return {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "status": project.status,
        "created_at": project.created_at.isoformat(),
        "updated_at": project.updated_at.isoformat(),
    }


def _task_dict(task) -> dict[str, Any]:
    return {
        "id": task.id,
        "project_id": task.project_id,
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "priority": task.priority,
        "due_at": task.due_at.isoformat() if task.due_at else None,
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
    }


def _projects_message(projects) -> str:
    if not projects:
        return "Non ci sono progetti che corrispondono al filtro richiesto."
    names = ", ".join(project.name for project in projects[:8])
    if len(projects) > 8:
        names += f" e altri {len(projects) - 8}"
    return f"Ho trovato {len(projects)} progetti: {names}."


def _tasks_message(tasks) -> str:
    if not tasks:
        return "Non ci sono task che corrispondono al filtro richiesto."
    titles = ", ".join(task.title for task in tasks[:8])
    if len(tasks) > 8:
        titles += f" e altri {len(tasks) - 8}"
    return f"Ho trovato {len(tasks)} task: {titles}."


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("due_at deve essere una stringa ISO 8601.")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError("due_at deve usare una data/ora ISO 8601 valida.") from error

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


__all__ = [
    "CreateProjectTool",
    "ListProjectsTool",
    "UpdateProjectTool",
    "CreateTaskTool",
    "ListTasksTool",
    "UpdateTaskTool",
]
