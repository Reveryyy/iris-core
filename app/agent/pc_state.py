from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RunningProcess:
    pid: int
    name: str
    executable: str | None = None
    command_line: str | None = None


@dataclass(frozen=True)
class WindowState:
    title: str
    process_name: str | None = None
    pid: int | None = None
    visible: bool = True
    minimized: bool = False
    foreground: bool = False


@dataclass(frozen=True)
class InstalledApplication:
    name: str
    target: str | None = None
    source: str | None = None
    app_id: str | None = None


@dataclass
class PCState:
    """
    Stato conosciuto del PC.

    IRIS non deve necessariamente conoscere tutto il computer
    contemporaneamente. Lo stato viene aggiornato man mano che
    vengono effettuate nuove discovery.
    """

    platform: str = "unknown"
    hostname: str | None = None
    username: str | None = None

    foreground_window: WindowState | None = None

    processes: list[RunningProcess] = field(
        default_factory=list
    )

    windows: list[WindowState] = field(
        default_factory=list
    )

    applications: list[InstalledApplication] = field(
        default_factory=list
    )

    facts: dict[str, Any] = field(
        default_factory=dict
    )

    discovered_at: float | None = None

    def process(
        self,
        name: str,
    ) -> RunningProcess | None:
        normalized = name.casefold()

        for process in self.processes:
            if process.name.casefold() == normalized:
                return process

        return None

    def processes_named(
        self,
        name: str,
    ) -> list[RunningProcess]:
        normalized = name.casefold()

        return [
            process
            for process in self.processes
            if process.name.casefold() == normalized
        ]

    def window(
        self,
        title: str,
    ) -> WindowState | None:
        normalized = title.casefold()

        for window in self.windows:
            if window.title.casefold() == normalized:
                return window

        return None

    def application(
        self,
        name: str,
    ) -> InstalledApplication | None:
        normalized = name.casefold()

        for application in self.applications:
            if application.name.casefold() == normalized:
                return application

        return None

    def set_fact(
        self,
        key: str,
        value: Any,
    ) -> None:
        self.facts[key] = value

    def get_fact(
        self,
        key: str,
        default: Any = None,
    ) -> Any:
        return self.facts.get(
            key,
            default,
        )

    def to_context(
        self,
        max_items: int = 30,
    ) -> str:
        """
        Converte lo stato in un contesto compatto per il Planner.
        """

        lines: list[str] = [
            "PC STATE:"
        ]

        if self.platform != "unknown":
            lines.append(
                f"- platform: {self.platform}"
            )

        if self.hostname:
            lines.append(
                f"- hostname: {self.hostname}"
            )

        if self.username:
            lines.append(
                f"- username: {self.username}"
            )

        if self.foreground_window:
            lines.append(
                "- foreground_window: "
                f"{self.foreground_window.title}"
            )

        if self.processes:
            lines.append(
                "- running_processes:"
            )

            for process in self.processes[:max_items]:
                lines.append(
                    f"  - {process.name} "
                    f"(pid={process.pid})"
                )

        if self.windows:
            lines.append(
                "- windows:"
            )

            for window in self.windows[:max_items]:
                lines.append(
                    f"  - {window.title}"
                )

        if self.applications:
            lines.append(
                "- installed_applications:"
            )

            for application in self.applications[:max_items]:
                lines.append(
                    f"  - {application.name}"
                )

        if self.facts:
            lines.append(
                "- facts:"
            )

            for key, value in list(
                self.facts.items()
            )[:max_items]:
                lines.append(
                    f"  - {key}: {value}"
                )

        return "\n".join(lines)