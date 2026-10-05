from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.projects.manager import ProjectManager
from app.projects.model import Project, Task
from app.tools.projects import (
    CreateProjectTool,
    CreateTaskTool,
    ListProjectsTool,
    ListTasksTool,
    UpdateTaskTool,
)


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Project.__table__.create(engine)
    Task.__table__.create(engine)
    return Session(engine)


def test_create_project_persists() -> None:
    db = _session()
    try:
        manager = ProjectManager(db)
        project = manager.create_project("IRIS M6", "Project and task manager")

        loaded = manager.get_project(project.id)

        assert loaded is not None
        assert loaded.name == "IRIS M6"
        assert loaded.status == "active"
    finally:
        db.close()


def test_duplicate_project_is_rejected() -> None:
    db = _session()
    try:
        manager = ProjectManager(db)
        manager.create_project("IRIS M6")

        try:
            manager.create_project("IRIS M6")
        except ValueError as error:
            assert "Esiste già" in str(error)
        else:
            raise AssertionError("Il duplicato doveva essere rifiutato.")
    finally:
        db.close()


def test_create_and_update_task() -> None:
    db = _session()
    try:
        manager = ProjectManager(db)
        project = manager.create_project("IRIS M6")
        due = datetime(2026, 10, 10, 18, 0, tzinfo=timezone.utc)

        task = manager.create_task(
            title="Implementare task manager",
            project_id=project.id,
            priority="high",
            due_at=due,
        )
        assert task.status == "todo"
        assert task.project_id == project.id

        updated = manager.update_task(
            task_id=task.id,
            status="completed",
        )
        assert updated is not None
        assert updated.status == "completed"
    finally:
        db.close()


def test_task_tools_use_persistent_manager() -> None:
    db = _session()
    try:
        manager = ProjectManager(db)

        project_result = CreateProjectTool(manager).execute({
            "name": "IRIS M6",
        })
        assert project_result.success is True

        project_id = project_result.output["project"]["id"]

        task_result = CreateTaskTool(manager).execute({
            "title": "Scrivere i test",
            "project_id": project_id,
            "priority": "high",
        })
        assert task_result.success is True

        listed = ListTasksTool(manager).execute({
            "project_id": project_id,
        })
        assert listed.success is True
        assert listed.output["count"] == 1

        task_id = listed.output["tasks"][0]["id"]

        updated = UpdateTaskTool(manager).execute({
            "task_id": task_id,
            "status": "completed",
        })
        assert updated.success is True
        assert updated.output["task"]["status"] == "completed"
    finally:
        db.close()


def test_list_projects_tool() -> None:
    db = _session()
    try:
        manager = ProjectManager(db)
        manager.create_project("Progetto A")
        manager.create_project("Progetto B")

        result = ListProjectsTool(manager).execute({})

        assert result.success is True
        assert result.output["count"] == 2
    finally:
        db.close()


def test_create_task_by_project_name() -> None:
    db = _session()
    try:
        manager = ProjectManager(db)
        project = manager.create_project("IRIS M6")

        task = manager.create_task(
            title="Task per progetto",
            project_name="IRIS M6",
        )

        assert task.project_id == project.id
    finally:
        db.close()


def test_list_tasks_by_project_name() -> None:
    db = _session()
    try:
        manager = ProjectManager(db)
        project = manager.create_project("IRIS M6")
        manager.create_task(
            title="Task collegato",
            project_name=project.name,
        )

        tasks = manager.list_tasks(
            project_name="IRIS M6",
        )

        assert len(tasks) == 1
        assert tasks[0].title == "Task collegato"
    finally:
        db.close()


def test_unknown_project_name_is_rejected() -> None:
    db = _session()
    try:
        manager = ProjectManager(db)

        try:
            manager.create_task(
                title="Task",
                project_name="Progetto inesistente",
            )
        except ValueError as error:
            assert "non trovato" in str(error)
        else:
            raise AssertionError(
                "Un progetto inesistente doveva essere rifiutato."
            )
    finally:
        db.close()


def test_project_id_and_name_cannot_be_combined() -> None:
    db = _session()
    try:
        manager = ProjectManager(db)
        project = manager.create_project("IRIS M6")

        try:
            manager.create_task(
                title="Task",
                project_id=project.id,
                project_name=project.name,
            )
        except ValueError as error:
            assert "oppure" in str(error)
        else:
            raise AssertionError(
                "ID e nome non devono essere usati insieme."
            )
    finally:
        db.close()


def test_task_tool_accepts_project_name() -> None:
    db = _session()
    try:
        manager = ProjectManager(db)
        project = manager.create_project("IRIS M6")

        result = CreateTaskTool(manager).execute({
            "title": "Test",
            "project_name": "IRIS M6",
        })

        assert result.success is True
        assert result.output["task"]["project_id"] == project.id
    finally:
        db.close()
