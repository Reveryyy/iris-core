from __future__ import annotations

import getpass
import json
import os
import platform
import subprocess
import time
from collections import Counter
from typing import Any

from app.agent.pc_state import (
    PCState,
    RunningProcess,
)
from app.tools.base import Tool, ToolDefinition
from app.tools.permissions import Permission
from app.tools.result import ToolResult


class DiscoverPCStateTool(Tool):
    """
    Scopre lo stato corrente del PC.

    I dati completi rimangono disponibili internamente a IRIS,
    mentre user_message contiene una risposta naturale destinata
    direttamente all'utente.
    """

    def __init__(
        self,
        include_processes: bool = True,
        max_processes: int = 100,
    ) -> None:
        self.include_processes = include_processes
        self.max_processes = max_processes

        self._definition = ToolDefinition(
            name="discover_pc_state",
            description=(
                "Scopre lo stato corrente del PC, "
                "inclusi sistema, utente e processi "
                "in esecuzione."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "include_processes": {
                        "type": "boolean",
                        "description": (
                            "Indica se includere i processi "
                            "in esecuzione."
                        ),
                    },
                },
                "required": [],
                "additionalProperties": False,
            },
            risk_level="low",
            permissions=frozenset(
                {
                    Permission.READ.value,
                }
            ),
        )

    @property
    def definition(
        self,
    ) -> ToolDefinition:
        return self._definition

    def execute(
        self,
        arguments: dict[str, Any],
    ) -> ToolResult:
        include_processes = arguments.get(
            "include_processes",
            self.include_processes,
        )

        if not isinstance(
            include_processes,
            bool,
        ):
            return ToolResult(
                success=False,
                error=(
                    "include_processes deve essere "
                    "boolean."
                ),
            )

        try:
            state = PCState(
                platform=platform.platform(),
                hostname=platform.node() or None,
                username=getpass.getuser() or None,
                discovered_at=time.time(),
            )

            state.set_fact(
                "os_name",
                os.name,
            )

            state.set_fact(
                "cwd",
                os.getcwd(),
            )

            state.set_fact(
                "python_version",
                platform.python_version(),
            )

            if include_processes:
                state.processes.extend(
                    self._discover_processes()
                )

            user_message = self._build_user_message(
                state=state,
                include_processes=include_processes,
            )

            return ToolResult(
                success=True,
                output={
                    # Dati completi per Planner / Agent Loop.
                    "state": state.to_context(
                        max_items=self.max_processes
                    ),

                    "platform": state.platform,
                    "hostname": state.hostname,
                    "username": state.username,

                    "process_count": len(
                        state.processes
                    ),

                    "processes": [
                        {
                            "pid": process.pid,
                            "name": process.name,
                            "executable": process.executable,
                            "command_line": process.command_line,
                        }
                        for process in state.processes
                    ],

                    "facts": dict(
                        state.facts
                    ),

                    # Risposta naturale destinata all'utente.
                    "user_message": user_message,
                },
            )

        except (
            OSError,
            subprocess.SubprocessError,
            json.JSONDecodeError,
        ) as error:
            return ToolResult(
                success=False,
                error=(
                    "Impossibile effettuare la "
                    f"discovery del PC: {error}"
                ),
            )

    def _build_user_message(
        self,
        state: PCState,
        include_processes: bool,
    ) -> str:
        """
        Costruisce una risposta naturale per l'utente.

        I dettagli tecnici rimangono nell'output strutturato
        e non vengono mostrati direttamente.
        """

        if not include_processes:
            return (
                "Ho controllato lo stato del PC. "
                f"Il computer si chiama {state.hostname or 'sconosciuto'} "
                f"e l'utente attivo è {state.username or 'sconosciuto'}."
            )

        processes = state.processes

        if not processes:
            return (
                "Ho controllato i processi in esecuzione, "
                "ma non ne ho trovati."
            )

        process_counter = Counter(
            process.name
            for process in processes
        )

        process_count = len(processes)

        grouped_processes = sorted(
            process_counter.items(),
            key=lambda item: (
                -item[1],
                item[0].casefold(),
            ),
        )

        if len(grouped_processes) <= 8:
            process_parts: list[str] = []

            for name, count in grouped_processes:
                if count == 1:
                    process_parts.append(
                        name
                    )
                else:
                    process_parts.append(
                        f"{name} ({count} istanze)"
                    )

            process_text = ", ".join(
                process_parts
            )

            return (
                f"Ho trovato {process_count} "
                f"processi attualmente in esecuzione sul PC. "
                f"Tra questi ci sono {process_text}."
            )

        visible_processes = grouped_processes[:8]

        process_parts = []

        for name, count in visible_processes:
            if count == 1:
                process_parts.append(
                    name
                )
            else:
                process_parts.append(
                    f"{name} ({count} istanze)"
                )

        process_text = ", ".join(
            process_parts
        )

        remaining = (
            len(grouped_processes)
            - len(visible_processes)
        )

        return (
            f"Ho trovato {process_count} "
            f"processi attualmente in esecuzione sul PC. "
            f"Tra i principali ci sono {process_text} "
            f"e altri {remaining} tipi di processo."
        )

    def _discover_processes(
        self,
    ) -> list[RunningProcess]:
        if os.name == "nt":
            return self._discover_processes_windows()

        return self._discover_processes_posix()

    def _discover_processes_windows(
        self,
    ) -> list[RunningProcess]:
        command = [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            (
                "Get-Process | "
                "Select-Object Id,ProcessName,Path | "
                "ConvertTo-Json -Compress"
            ),
        ]

        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            shell=False,
        )

        if completed.returncode != 0:
            raise OSError(
                completed.stderr.strip()
                or "Get-Process ha restituito un errore."
            )

        return self._parse_powershell_processes(
            completed.stdout
        )

    def _discover_processes_posix(
        self,
    ) -> list[RunningProcess]:
        completed = subprocess.run(
            [
                "ps",
                "-eo",
                "pid=,comm=",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            shell=False,
        )

        if completed.returncode != 0:
            raise OSError(
                completed.stderr.strip()
                or "ps ha restituito un errore."
            )

        processes: list[RunningProcess] = []

        for line in completed.stdout.splitlines():
            line = line.strip()

            if not line:
                continue

            parts = line.split(
                maxsplit=1
            )

            if len(parts) != 2:
                continue

            try:
                pid = int(parts[0])
            except ValueError:
                continue

            processes.append(
                RunningProcess(
                    pid=pid,
                    name=parts[1],
                )
            )

            if len(processes) >= self.max_processes:
                break

        return processes

    def _parse_powershell_processes(
        self,
        raw_output: str,
    ) -> list[RunningProcess]:
        if not raw_output.strip():
            return []

        data = json.loads(
            raw_output
        )

        if isinstance(
            data,
            dict,
        ):
            data = [data]

        if not isinstance(
            data,
            list,
        ):
            return []

        processes: list[RunningProcess] = []

        for item in data:
            if not isinstance(
                item,
                dict,
            ):
                continue

            raw_pid = item.get("Id")
            raw_name = item.get("ProcessName")

            if not isinstance(
                raw_pid,
                int,
            ):
                continue

            if not isinstance(
                raw_name,
                str,
            ):
                continue

            path = item.get("Path")

            processes.append(
                RunningProcess(
                    pid=raw_pid,
                    name=raw_name,
                    executable=(
                        path
                        if isinstance(
                            path,
                            str,
                        )
                        else None
                    ),
                )
            )

            if len(processes) >= self.max_processes:
                break

        return processes