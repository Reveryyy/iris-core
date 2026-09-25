from __future__ import annotations

import ctypes
import json
import os
import subprocess
from typing import Any

from app.tools.base import Tool, ToolDefinition
from app.tools.permissions import Permission
from app.tools.result import ToolResult


def _windows_no_console_flags() -> int:
    if os.name != "nt":
        return 0

    return getattr(
        subprocess,
        "CREATE_NO_WINDOW",
        0x08000000,
    )


class ListUIElementsTool(Tool):
    """
    Ispeziona i controlli di una finestra Windows tramite UI Automation.
    """

    def __init__(self) -> None:
        self._definition = ToolDefinition(
            name="list_ui_elements",
            description=(
                "Ispeziona dinamicamente i controlli accessibili di una "
                "finestra Windows tramite UI Automation. Restituisce "
                "nome, automation id, tipo di controllo, classe, stato "
                "e rettangolo del controllo."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "window_title": {
                        "type": "string",
                        "description": (
                            "Titolo o parte del titolo della finestra "
                            "da ispezionare."
                        ),
                    },
                },
                "required": [
                    "window_title",
                ],
                "additionalProperties": False,
            },
            risk_level="low",
            permissions=frozenset(
                {
                    Permission.READ.value,
                    Permission.GUI.value,
                }
            ),
        )

    @property
    def definition(self) -> ToolDefinition:
        return self._definition

    def execute(
        self,
        arguments: dict[str, Any],
    ) -> ToolResult:
        window_title = arguments.get("window_title")

        if not isinstance(window_title, str):
            return ToolResult(
                success=False,
                error="window_title deve essere una stringa.",
            )

        window_title = window_title.strip()

        if not window_title:
            return ToolResult(
                success=False,
                error="window_title non può essere vuoto.",
            )

        if os.name != "nt" or not hasattr(ctypes, "windll"):
            return ToolResult(
                success=False,
                error=(
                    "La UI Automation è disponibile "
                    "solo su Windows."
                ),
            )

        script = r"""
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

$query = [Environment]::GetEnvironmentVariable("IRIS_UI_WINDOW_TITLE")
$root = [System.Windows.Automation.AutomationElement]::RootElement

$windows = $root.FindAll(
    [System.Windows.Automation.TreeScope]::Children,
    [System.Windows.Automation.Condition]::TrueCondition
)

$targetWindow = $null

foreach ($window in $windows) {
    try {
        $name = $window.Current.Name

        if (
            $name -and (
                $name -like "*$query*"
                -or $query -like "*$name*"
            )
        ) {
            $targetWindow = $window
            break
        }
    }
    catch {
    }
}

if ($null -eq $targetWindow) {
    Write-Output (
        [pscustomobject]@{
            success = $false
            error = "Finestra non trovata."
        } | ConvertTo-Json -Compress
    )
    exit 0
}

$elements = $targetWindow.FindAll(
    [System.Windows.Automation.TreeScope]::Descendants,
    [System.Windows.Automation.Condition]::TrueCondition
)

$result = @()

foreach ($element in $elements) {
    try {
        $current = $element.Current
        $rect = $current.BoundingRectangle

        $result += [pscustomobject]@{
            name = [string]$current.Name
            automation_id = [string]$current.AutomationId
            control_type = [string]$current.ControlType.ProgrammaticName
            class_name = [string]$current.ClassName
            enabled = [bool]$current.IsEnabled
            offscreen = [bool]$current.IsOffscreen
            process_id = [int]$current.ProcessId
            hwnd = [Int64]$current.NativeWindowHandle
            x = [double]$rect.X
            y = [double]$rect.Y
            width = [double]$rect.Width
            height = [double]$rect.Height
        }
    }
    catch {
    }
}

[pscustomobject]@{
    success = $true
    window_title = [string]$targetWindow.Current.Name
    hwnd = [Int64]$targetWindow.Current.NativeWindowHandle
    elements = $result
    count = @($result).Count
} | ConvertTo-Json -Compress -Depth 8
"""

        environment = dict(
            os.environ
        )

        environment["IRIS_UI_WINDOW_TITLE"] = window_title

        powershell = self._powershell_executable()

        try:
            completed = subprocess.run(
                [
                    powershell,
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    script,
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=20.0,
                stdin=subprocess.DEVNULL,
                shell=False,
                env=environment,
                creationflags=_windows_no_console_flags(),
            )

        except (
            OSError,
            subprocess.SubprocessError,
        ) as error:
            return ToolResult(
                success=False,
                error=(
                    f"Impossibile eseguire la UI Automation: {error}"
                ),
            )

        if completed.returncode != 0:
            return ToolResult(
                success=False,
                error=(
                    completed.stderr.strip()
                    or "UI Automation ha restituito un errore."
                ),
            )

        raw_output = completed.stdout.strip()

        if not raw_output:
            return ToolResult(
                success=False,
                error=(
                    "UI Automation non ha restituito dati."
                ),
            )

        try:
            data = json.loads(
                raw_output
            )
        except json.JSONDecodeError as error:
            return ToolResult(
                success=False,
                error=(
                    f"Risposta UI Automation non valida: {error}"
                ),
            )

        if not isinstance(data, dict):
            return ToolResult(
                success=False,
                error="Risposta UI Automation non valida.",
            )

        if data.get("success") is not True:
            return ToolResult(
                success=False,
                output=data,
                error=(
                    str(
                        data.get(
                            "error",
                            "Finestra non trovata.",
                        )
                    )
                ),
            )

        elements = data.get(
            "elements",
            [],
        )

        if not isinstance(elements, list):
            elements = []

        return ToolResult(
            success=True,
            output={
                "window_title": data.get(
                    "window_title"
                ),
                "hwnd": data.get(
                    "hwnd"
                ),
                "count": len(elements),
                "elements": elements,
                "user_message": (
                    f"Ho ispezionato la finestra "
                    f"'{data.get('window_title', window_title)}' "
                    f"e rilevato {len(elements)} controlli UI."
                ),
            },
        )

    @staticmethod
    def _powershell_executable() -> str:
        system_root = os.environ.get(
            "SystemRoot"
        )

        if not system_root:
            raise OSError(
                "La variabile SystemRoot non è disponibile."
            )

        executable = (
            os.path.join(
                system_root,
                "System32",
                "WindowsPowerShell",
                "v1.0",
                "powershell.exe",
            )
        )

        if not os.path.exists(executable):
            raise OSError(
                f"PowerShell non trovata in '{executable}'."
            )

        return executable


__all__ = [
    "ListUIElementsTool",
]
