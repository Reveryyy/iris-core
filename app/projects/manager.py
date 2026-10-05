from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.projects.model import Project, Task


class ProjectManager:
    PROJECT_STATUSES = frozenset({
        "active",
        "completed",
        "archived",
    })
    TASK_STATUSES = frozenset({
        "todo",
        "in_progress",
        "completed",
        "cancelled",
    })
    TASK_PRIORITIES = frozenset({
        "low",
        "medium",
        "high",
        "urgent",
    })

    def __init__(self, db: Session):
        self.db = db

    def create_project(
        self,
        name: str,
        description: str | None = None,
    ) -> Project:
        name = self._required_text(name, "Il nome del progetto")

        existing = self.db.scalar(
            select(Project).where(Project.name == name)
        )
        if existing is not None:
            raise ValueError(
                f"Esiste già un progetto chiamato '{name}'."
            )

        project = Project(
            name=name,
            description=self._optional_text(description),
            status="active",
        )
        self.db.add(project)
        self.db.commit()
        self.db.refresh(project)
        return project

    def get_project(self, project_id: int) -> Project | None:
        return self.db.get(Project, project_id)

    def get_project_by_name(self, name: str) -> Project | None:
        name = self._required_text(name, "Il nome del progetto")
        return self.db.scalar(
            select(Project).where(Project.name == name)
        )

    def list_projects(
        self,
        status: str | None = None,
    ) -> list[Project]:
        if status is not None:
            self._validate_choice(status, self.PROJECT_STATUSES, "project status")

        statement = select(Project).order_by(
            Project.status.asc(),
            Project.created_at.desc(),
        )
        if status is not None:
            statement = statement.where(Project.status == status)

        return list(self.db.scalars(statement).all())

    def update_project(
        self,
        project_id: int,
        name: str | None = None,
        description: str | None = None,
        status: str | None = None,
    ) -> Project | None:
        project = self.get_project(project_id)
        if project is None:
            return None

        if name is not None:
            normalized_name = self._required_text(name, "Il nome del progetto")
            existing = self.db.scalar(
                select(Project).where(
                    Project.name == normalized_name,
                    Project.id != project_id,
                )
            )
            if existing is not None:
                raise ValueError(
                    f"Esiste già un progetto chiamato '{normalized_name}'."
                )
            project.name = normalized_name

        if description is not None:
            project.description = self._optional_text(description)

        if status is not None:
            self._validate_choice(status, self.PROJECT_STATUSES, "project status")
            project.status = status

        self.db.commit()
        self.db.refresh(project)
        return project

    def create_task(
        self,
        title: str,
        project_id: int | None = None,
        project_name: str | None = None,
        description: str | None = None,
        priority: str = "medium",
        due_at: datetime | None = None,
    ) -> Task:
        title = self._required_text(title, "Il titolo del task")
        self._validate_choice(priority, self.TASK_PRIORITIES, "task priority")

        resolved_project_id = self._resolve_project_id(
            project_id=project_id,
            project_name=project_name,
        )

        task = Task(
            project_id=resolved_project_id,
            title=title,
            description=self._optional_text(description),
            status="todo",
            priority=priority,
            due_at=due_at,
        )
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)
        return task

    def get_task(self, task_id: int) -> Task | None:
        return self.db.get(Task, task_id)

    def list_tasks(
        self,
        project_id: int | None = None,
        project_name: str | None = None,
        status: str | None = None,
    ) -> list[Task]:
        if status is not None:
            self._validate_choice(status, self.TASK_STATUSES, "task status")

        resolved_project_id = self._resolve_project_id(
            project_id=project_id,
            project_name=project_name,
            allow_none=True,
        )

        statement = select(Task).order_by(
            Task.status.asc(),
            Task.priority.desc(),
            Task.created_at.desc(),
        )
        if resolved_project_id is not None:
            statement = statement.where(
                Task.project_id == resolved_project_id
            )
        if status is not None:
            statement = statement.where(Task.status == status)

        return list(self.db.scalars(statement).all())

    def update_task(
        self,
        task_id: int,
        title: str | None = None,
        description: str | None = None,
        project_id: int | None = None,
        project_name: str | None = None,
        status: str | None = None,
        priority: str | None = None,
        due_at: datetime | None = None,
    ) -> Task | None:
        task = self.get_task(task_id)
        if task is None:
            return None

        if title is not None:
            task.title = self._required_text(title, "Il titolo del task")

        if description is not None:
            task.description = self._optional_text(description)

        if project_id is not None or project_name is not None:
            task.project_id = self._resolve_project_id(
                project_id=project_id,
                project_name=project_name,
            )

        if status is not None:
            self._validate_choice(status, self.TASK_STATUSES, "task status")
            task.status = status

        if priority is not None:
            self._validate_choice(priority, self.TASK_PRIORITIES, "task priority")
            task.priority = priority

        if due_at is not None:
            task.due_at = due_at

        self.db.commit()
        self.db.refresh(task)
        return task

    def _resolve_project_id(
        self,
        project_id: int | None,
        project_name: str | None,
        allow_none: bool = False,
    ) -> int | None:
        if project_id is not None and project_name is not None:
            raise ValueError(
                "Specificare project_id oppure project_name, non entrambi."
            )

        if project_id is not None:
            if not isinstance(project_id, int) or project_id <= 0:
                raise ValueError(
                    "project_id deve essere un intero positivo."
                )

            if self.get_project(project_id) is None:
                raise ValueError(
                    f"Progetto con ID {project_id} non trovato."
                )

            return project_id

        if project_name is not None:
            project = self.get_project_by_name(project_name)
            if project is None:
                raise ValueError(
                    f"Progetto chiamato '{project_name}' non trovato."
                )
            return project.id

        if allow_none:
            return None

        return None

    @staticmethod
    def _required_text(value: str, label: str) -> str:
        if not isinstance(value, str):
            raise TypeError(f"{label} deve essere una stringa.")
        value = value.strip()
        if not value:
            raise ValueError(f"{label} non può essere vuoto.")
        return value

    @staticmethod
    def _optional_text(value: str | None) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError("Il testo opzionale deve essere una stringa oppure None.")
        value = value.strip()
        return value or None

    @staticmethod
    def _validate_choice(
        value: str,
        choices: frozenset[str],
        label: str,
    ) -> None:
        if value not in choices:
            allowed = ", ".join(sorted(choices))
            raise ValueError(
                f"Valore non valido per {label}: '{value}'. Valori ammessi: {allowed}."
            )
