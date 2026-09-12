from __future__ import annotations

import os
import re
import subprocess
import unicodedata
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ResolvedApplication:
    """
    Rappresenta un'applicazione trovata sul sistema.
    """

    name: str
    target: str
    source: str
    app_id: str | None = None


class ApplicationResolver:
    """
    Cerca automaticamente applicazioni Windows.

    Fonti utilizzate:

    1. Start Menu dell'utente
    2. Start Menu globale
    3. Windows Get-StartApps
    4. Registry App Paths
    5. Eseguibili presenti nel PATH

    Non utilizza una allowlist hardcoded.
    """

    def __init__(self) -> None:
        self._cache: list[ResolvedApplication] | None = None

    # ========================================================================
    # PUBLIC
    # ========================================================================

    def resolve(
        self,
        query: str,
    ) -> ResolvedApplication | None:
        """
        Cerca l'applicazione richiesta.
        """

        if not isinstance(
            query,
            str,
        ):
            raise TypeError(
                "Il nome dell'applicazione deve essere una stringa."
            )

        query = query.strip()

        if not query:
            raise ValueError(
                "Il nome dell'applicazione non può essere vuoto."
            )

        applications = self._discover()

        normalized_query = self._normalize(
            query
        )

        # --------------------------------------------------------------------
        # MATCH ESATTO
        # --------------------------------------------------------------------

        for application in applications:
            if (
                self._normalize(
                    application.name
                )
                == normalized_query
            ):
                return application

        # --------------------------------------------------------------------
        # MATCH ESATTO SENZA ESTENSIONE
        # --------------------------------------------------------------------

        for application in applications:
            stem = Path(
                application.name
            ).stem

            if (
                self._normalize(
                    stem
                )
                == normalized_query
            ):
                return application

        # --------------------------------------------------------------------
        # MATCH PARZIALE
        # --------------------------------------------------------------------

        candidates = [
            application
            for application in applications
            if normalized_query
            in self._normalize(
                application.name
            )
        ]

        if candidates:
            candidates.sort(
                key=self._candidate_sort_key
            )

            return candidates[0]

        # --------------------------------------------------------------------
        # MATCH INVERSO
        # --------------------------------------------------------------------

        candidates = [
            application
            for application in applications
            if self._normalize(
                application.name
            )
            in normalized_query
        ]

        if candidates:
            candidates.sort(
                key=self._candidate_sort_key
            )

            return candidates[0]

        return None

    def refresh(self) -> None:
        """
        Svuota la cache delle applicazioni.
        """

        self._cache = None

    # ========================================================================
    # DISCOVERY
    # ========================================================================

    def _discover(
        self,
    ) -> list[ResolvedApplication]:

        if self._cache is not None:
            return self._cache

        found: dict[str, ResolvedApplication] = {}

        self._discover_start_menu(
            found
        )

        self._discover_start_apps(
            found
        )

        self._discover_registry(
            found
        )

        self._discover_path(
            found
        )

        self._cache = list(
            found.values()
        )

        return self._cache

    # ========================================================================
    # START MENU
    # ========================================================================

    def _discover_start_menu(
        self,
        found: dict[str, ResolvedApplication],
    ) -> None:

        locations = []

        appdata = os.environ.get(
            "APPDATA"
        )

        programdata = os.environ.get(
            "PROGRAMDATA"
        )

        if appdata:
            locations.append(
                Path(appdata)
                / "Microsoft"
                / "Windows"
                / "Start Menu"
                / "Programs"
            )

        if programdata:
            locations.append(
                Path(programdata)
                / "Microsoft"
                / "Windows"
                / "Start Menu"
                / "Programs"
            )

        for root in locations:

            if not root.exists():
                continue

            try:
                for path in root.rglob("*"):

                    if not path.is_file():
                        continue

                    extension = path.suffix.lower()

                    if extension != ".lnk":
                        continue

                    name = path.stem.strip()

                    if not name:
                        continue

                    self._add_application(
                        found=found,
                        application=ResolvedApplication(
                            name=name,
                            target=str(path),
                            source="start_menu",
                        ),
                    )

            except OSError:
                continue

    # ========================================================================
    # WINDOWS GET-STARTAPPS
    # ========================================================================

    def _discover_start_apps(
        self,
        found: dict[str, ResolvedApplication],
    ) -> None:

        if os.name != "nt":
            return

        command = [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            (
                "Get-StartApps | "
                "ForEach-Object { "
                "$_.Name + \"`t\" + $_.AppID "
                "}"
            ),
        ]

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=10.0,
                shell=False,
                check=False,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )

        except (
            OSError,
            subprocess.SubprocessError,
        ):
            return

        if result.returncode != 0:
            return

        for raw_line in result.stdout.splitlines():

            line = raw_line.strip()

            if not line:
                continue

            if "\t" not in line:
                continue

            name, app_id = line.split(
                "\t",
                1,
            )

            name = name.strip()
            app_id = app_id.strip()

            if not name or not app_id:
                continue

            self._add_application(
                found=found,
                application=ResolvedApplication(
                    name=name,
                    target=app_id,
                    source="windows_start_apps",
                    app_id=app_id,
                ),
            )

    # ========================================================================
    # REGISTRY
    # ========================================================================

    def _discover_registry(
        self,
        found: dict[str, ResolvedApplication],
    ) -> None:

        if os.name != "nt":
            return

        try:
            import winreg
        except ImportError:
            return

        locations = [
            (
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\App Paths",
            ),
            (
                winreg.HKEY_LOCAL_MACHINE,
                r"Software\Microsoft\Windows\CurrentVersion\App Paths",
            ),
        ]

        for root_key, base_path in locations:

            try:
                with winreg.OpenKey(
                    root_key,
                    base_path,
                ) as root:

                    index = 0

                    while True:
                        try:
                            subkey_name = (
                                winreg.EnumKey(
                                    root,
                                    index,
                                )
                            )

                        except OSError:
                            break

                        index += 1

                        try:
                            with winreg.OpenKey(
                                root,
                                subkey_name,
                            ) as application_key:

                                executable = winreg.QueryValue(
                                    application_key,
                                    None,
                                )

                                if not executable:
                                    continue

                                name = Path(
                                    subkey_name
                                ).stem.strip()

                                if not name:
                                    continue

                                self._add_application(
                                    found=found,
                                    application=ResolvedApplication(
                                        name=name,
                                        target=str(executable),
                                        source="registry",
                                    ),
                                )

                        except OSError:
                            continue

            except OSError:
                continue

    # ========================================================================
    # PATH
    # ========================================================================

    def _discover_path(
        self,
        found: dict[str, ResolvedApplication],
    ) -> None:

        if os.name != "nt":
            return

        path_value = os.environ.get(
            "PATH",
            "",
        )

        for raw_directory in path_value.split(
            os.pathsep
        ):

            directory = raw_directory.strip()

            if not directory:
                continue

            try:
                root = Path(
                    directory
                )

                if not root.exists():
                    continue

                for executable in root.glob(
                    "*.exe"
                ):

                    name = executable.stem.strip()

                    if not name:
                        continue

                    self._add_application(
                        found=found,
                        application=ResolvedApplication(
                            name=name,
                            target=str(executable),
                            source="path",
                        ),
                    )

            except OSError:
                continue

    # ========================================================================
    # HELPERS
    # ========================================================================

    @staticmethod
    def _add_application(
        found: dict[str, ResolvedApplication],
        application: ResolvedApplication,
    ) -> None:

        key = ApplicationResolver._normalize(
            application.name
        )

        if not key:
            return

        # La prima fonte trovata mantiene la precedenza.
        found.setdefault(
            key,
            application,
        )

    @staticmethod
    def _candidate_sort_key(
        application: ResolvedApplication,
    ) -> tuple[int, int, str]:

        source_priority = {
            "start_menu": 0,
            "windows_start_apps": 1,
            "registry": 2,
            "path": 3,
        }

        return (
            source_priority.get(
                application.source,
                99,
            ),
            len(application.name),
            application.name.lower(),
        )

    @staticmethod
    def _normalize(
        value: str,
    ) -> str:

        value = value.strip().lower()

        value = unicodedata.normalize(
            "NFKD",
            value,
        )

        value = "".join(
            character
            for character in value
            if not unicodedata.combining(
                character
            )
        )

        value = re.sub(
            r"\s+",
            " ",
            value,
        )

        return value