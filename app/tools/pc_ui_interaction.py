from __future__ import annotations

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


class InteractUIElementTool(Tool):
    """
    Interagisce con un controllo UI identificato dinamicamente.
    """

    ALLOWED_ACTIONS = (
        "click",
        "focus",
        "set_text",
        "toggle",
        "select",
        "expand",
        "collapse",
        "scroll_into_view",
    )

    def __init__(self) -> None:
        self._definition = ToolDefinition(
            name="interact_ui_element",
            description=(
                "Trova dinamicamente un controllo UI all'interno di una "
                "finestra Windows usando nome o AutomationId e applica "
                "un'azione semantica compatibile con il controllo: "
                "click, focus, set_text, toggle, select, expand, "
                "collapse o scroll_into_view."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "window_title": {
                        "type": "string",
                        "description": (
                            "Titolo o parte del titolo della finestra."
                        ),
                    },
                    "element": {
                        "type": "string",
                        "description": (
                            "Nome o AutomationId del controllo UI."
                        ),
                    },
                    "action": {
                        "type": "string",
                        "enum": list(
                            InteractUIElementTool.ALLOWED_ACTIONS
                        ),
                        "description": (
                            "Azione semantica da eseguire sul controllo."
                        ),
                    },
                    "value": {
                        "type": "string",
                        "description": (
                            "Valore da impostare quando action è set_text."
                        ),
                    },
                },
                "required": [
                    "window_title",
                    "element",
                    "action",
                ],
                "additionalProperties": False,
            },
            risk_level="medium",
            permissions=frozenset(
                {
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
        element = arguments.get("element")
        action = arguments.get("action")
        value = arguments.get("value")

        if not isinstance(window_title, str):
            return ToolResult(
                success=False,
                error="window_title deve essere una stringa.",
            )

        if not isinstance(element, str):
            return ToolResult(
                success=False,
                error="element deve essere una stringa.",
            )

        if not isinstance(action, str):
            return ToolResult(
                success=False,
                error="action deve essere una stringa.",
            )

        window_title = window_title.strip()
        element = element.strip()
        action = action.strip().lower()

        if not window_title:
            return ToolResult(
                success=False,
                error="window_title non può essere vuoto.",
            )

        if not element:
            return ToolResult(
                success=False,
                error="element non può essere vuoto.",
            )

        if action not in self.ALLOWED_ACTIONS:
            return ToolResult(
                success=False,
                error=(
                    f"Azione UI non supportata: '{action}'."
                ),
            )

        if action == "set_text" and not isinstance(value, str):
            return ToolResult(
                success=False,
                error=(
                    "value deve essere una stringa quando "
                    "action è set_text."
                ),
            )

        if os.name != "nt":
            return ToolResult(
                success=False,
                error=(
                    "L'interazione UI è disponibile "
                    "solo su Windows."
                ),
            )

        environment = dict(
            os.environ
        )

        environment["IRIS_UI_WINDOW_TITLE"] = window_title
        environment["IRIS_UI_ELEMENT"] = element
        environment["IRIS_UI_ACTION"] = action

        if isinstance(value, str):
            environment["IRIS_UI_VALUE"] = value
        else:
            environment.pop(
                "IRIS_UI_VALUE",
                None,
            )

        script = r"""
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

$query = [Environment]::GetEnvironmentVariable("IRIS_UI_WINDOW_TITLE")
$elementQuery = [Environment]::GetEnvironmentVariable("IRIS_UI_ELEMENT")
$action = [Environment]::GetEnvironmentVariable("IRIS_UI_ACTION")
$value = [Environment]::GetEnvironmentVariable("IRIS_UI_VALUE")

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
    [pscustomobject]@{
        success = $false
        error = "Finestra non trovata."
    } | ConvertTo-Json -Compress
    exit 0
}

$elements = $targetWindow.FindAll(
    [System.Windows.Automation.TreeScope]::Descendants,
    [System.Windows.Automation.Condition]::TrueCondition
)

$best = $null
$bestScore = [int]::MaxValue

foreach ($candidate in $elements) {
    try {
        $current = $candidate.Current
        $name = [string]$current.Name
        $automationId = [string]$current.AutomationId

        $score = $null

        if (
            $name -and
            $name.Equals(
                $elementQuery,
                [System.StringComparison]::OrdinalIgnoreCase
            )
        ) {
            $score = 0
        }
        elseif (
            $automationId -and
            $automationId.Equals(
                $elementQuery,
                [System.StringComparison]::OrdinalIgnoreCase
            )
        ) {
            $score = 1
        }
        elseif (
            $name -and
            $name.IndexOf(
                $elementQuery,
                [System.StringComparison]::OrdinalIgnoreCase
            ) -ge 0
        ) {
            $score = 2
        }
        elseif (
            $automationId -and
            $automationId.IndexOf(
                $elementQuery,
                [System.StringComparison]::OrdinalIgnoreCase
            ) -ge 0
        ) {
            $score = 3
        }

        if (
            $null -ne $score -and
            $score -lt $bestScore
        ) {
            $best = $candidate
            $bestScore = $score
        }
    }
    catch {
    }
}

if ($null -eq $best) {
    [pscustomobject]@{
        success = $false
        error = "Controllo UI non trovato."
    } | ConvertTo-Json -Compress
    exit 0
}

try {
    $current = $best.Current
    $resultMessage = $null
    $verified = $false

    switch ($action) {
        "click" {
            $pattern = $null

            if (
                -not $best.TryGetCurrentPattern(
                    [System.Windows.Automation.InvokePattern]::Pattern,
                    [ref]$pattern
                )
            ) {
                throw "Il controllo non espone InvokePattern."
            }

            $pattern.Invoke()
            $resultMessage = "invoke"
            $verified = $true
        }

        "focus" {
            $best.SetFocus()

            $focused = [
                System.Windows.Automation.AutomationElement
            ]::FocusedElement

            if (
                $null -eq $focused
                -or
                $focused.Current.NativeWindowHandle -ne
                    $current.NativeWindowHandle
            ) {
                # Alcuni controlli condividono lo stesso HWND.
                # Verifichiamo anche Name e AutomationId.
                $focusedCurrent = $focused.Current

                if (
                    [string]$focusedCurrent.Name -ne
                        [string]$current.Name
                    -or
                    [string]$focusedCurrent.AutomationId -ne
                        [string]$current.AutomationId
                ) {
                    throw "Il controllo non risulta focalizzato."
                }
            }

            $resultMessage = "focus"
            $verified = $true
        }

        "set_text" {
            $pattern = $null

            if (
                -not $best.TryGetCurrentPattern(
                    [System.Windows.Automation.ValuePattern]::Pattern,
                    [ref]$pattern
                )
            ) {
                throw "Il controllo non espone ValuePattern."
            }

            if (
                $pattern.Current.IsReadOnly
            ) {
                throw "Il controllo è in sola lettura."
            }

            $pattern.SetValue(
                [string]$value
            )

            if (
                [string]$pattern.Current.Value -ne [string]$value
            ) {
                throw "Il valore del controllo non coincide con quello richiesto."
            }

            $resultMessage = "set_text"
            $verified = $true
        }

        "toggle" {
            $pattern = $null

            if (
                -not $best.TryGetCurrentPattern(
                    [System.Windows.Automation.TogglePattern]::Pattern,
                    [ref]$pattern
                )
            ) {
                throw "Il controllo non espone TogglePattern."
            }

            $before = $pattern.Current.ToggleState
            $pattern.Toggle()
            $after = $pattern.Current.ToggleState

            if ($before -eq $after) {
                throw "Lo stato del controllo non è cambiato."
            }

            $resultMessage = "toggle"
            $verified = $true
        }

        "select" {
            $pattern = $null

            if (
                -not $best.TryGetCurrentPattern(
                    [System.Windows.Automation.SelectionItemPattern]::Pattern,
                    [ref]$pattern
                )
            ) {
                throw "Il controllo non espone SelectionItemPattern."
            }

            $pattern.Select()

            if (-not $pattern.Current.IsSelected) {
                throw "Il controllo non risulta selezionato."
            }

            $resultMessage = "select"
            $verified = $true
        }

        "expand" {
            $pattern = $null

            if (
                -not $best.TryGetCurrentPattern(
                    [System.Windows.Automation.ExpandCollapsePattern]::Pattern,
                    [ref]$pattern
                )
            ) {
                throw "Il controllo non espone ExpandCollapsePattern."
            }

            $pattern.Expand()

            if (
                $pattern.Current.ExpandCollapseState
                -ne [System.Windows.Automation.ExpandCollapseState]::Expanded
            ) {
                throw "Il controllo non risulta espanso."
            }

            $resultMessage = "expand"
            $verified = $true
        }

        "collapse" {
            $pattern = $null

            if (
                -not $best.TryGetCurrentPattern(
                    [System.Windows.Automation.ExpandCollapsePattern]::Pattern,
                    [ref]$pattern
                )
            ) {
                throw "Il controllo non espone ExpandCollapsePattern."
            }

            $pattern.Collapse()

            if (
                $pattern.Current.ExpandCollapseState
                -ne [System.Windows.Automation.ExpandCollapseState]::Collapsed
            ) {
                throw "Il controllo non risulta compresso."
            }

            $resultMessage = "collapse"
            $verified = $true
        }

        "scroll_into_view" {
            $pattern = $null

            if (
                -not $best.TryGetCurrentPattern(
                    [System.Windows.Automation.ScrollItemPattern]::Pattern,
                    [ref]$pattern
                )
            ) {
                throw "Il controllo non espone ScrollItemPattern."
            }

            $pattern.ScrollIntoView()

            $resultMessage = "scroll_into_view"
            $verified = $true
        }
    }

    [pscustomobject]@{
        success = $true
        window_title = [string]$targetWindow.Current.Name
        hwnd = [Int64]$targetWindow.Current.NativeWindowHandle
        element_name = [string]$current.Name
        automation_id = [string]$current.AutomationId
        control_type = [string]$current.ControlType.ProgrammaticName
        action = $action
        result = $resultMessage
        verified = [bool]$verified
    } | ConvertTo-Json -Compress
}
catch {
    [pscustomobject]@{
        success = $false
        error = $_.Exception.Message
    } | ConvertTo-Json -Compress
}
"""

        try:
            completed = subprocess.run(
                [
                    self._powershell_executable(),
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
                    f"Impossibile eseguire l'interazione UI: {error}"
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
                error="UI Automation non ha restituito dati.",
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
                error=str(
                    data.get(
                        "error",
                        "Interazione UI fallita.",
                    )
                ),
            )

        return ToolResult(
            success=True,
            output={
                **data,
                "verified": True,
                "user_message": (
                    f"Ho eseguito '{action}' sul controllo "
                    f"'{data.get('element_name', element)}'."
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

        executable = os.path.join(
            system_root,
            "System32",
            "WindowsPowerShell",
            "v1.0",
            "powershell.exe",
        )

        if not os.path.exists(executable):
            raise OSError(
                f"PowerShell non trovata in '{executable}'."
            )

        return executable


__all__ = [
    "InteractUIElementTool",
]
