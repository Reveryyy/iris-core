from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
ROOT = Path(__file__).resolve().parent
def snapshot_python_files(
    root: Path = ROOT,
) -> dict[Path, tuple[int, int]]:
    """
    Restituisce uno snapshot compatto dei sorgenti Python di IRIS.

    Vengono esclusi automaticamente __pycache__ e le directory nascoste
    generate dal runtime. L'ordine è deterministico così lo snapshot può
    essere confrontato direttamente.
    """
    snapshot: dict[Path, tuple[int, int]] = {}

    watch_directory = root / "app"

    try:
        if not watch_directory.exists():
            return snapshot
    except OSError:
        return snapshot

    directory = watch_directory
        for path in directory.rglob("*.py"):
            parts = path.parts

            if "__pycache__" in parts:
                continue

            try:
                stat = path.stat()
            except OSError:
                continue

            snapshot[path] = (
                stat.st_mtime_ns,
                stat.st_size,
            )

    return dict(
        sorted(
            snapshot.items(),
            key=lambda item: str(item[0]).lower(),
        )
    )


def start_iris() -> subprocess.Popen:
    """Avvia IRIS come processo figlio con lo stesso interprete Python."""
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "app.main",
        ],
        cwd=ROOT,
    )


def stop_iris(
    process: subprocess.Popen,
) -> None:
    """Termina IRIS e, se necessario, forza la chiusura."""
    if process.poll() is not None:
        return

    process.terminate()

    try:
        process.wait(timeout=5.0)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def main() -> None:
    """
    Supervisore di sviluppo.

    Avvio:
        py dev.py

    Da quel momento:
    - IRIS parte normalmente;
    - ogni modifica a un .py dentro app/ viene rilevata;
    - IRIS viene riavviato automaticamente;
    - non serve chiudere e rilanciare manualmente il terminale.

    La memoria persistente resta nel database; lo stato puramente in-memory
    della sessione, invece, viene ricreato a ogni reload.
    """
    previous_snapshot = snapshot_python_files()
    process = start_iris()

    print(
        "[DEV] IRIS avviato in modalità auto-reload."
    )
    print(
        "[DEV] Modifica un file in app/ per applicare automaticamente "
        "le modifiche senza riavviare manualmente IRIS."
    )

    try:
        while True:
            time.sleep(0.5)

            current_snapshot = snapshot_python_files()

            if current_snapshot != previous_snapshot:
                print(
                    "[DEV] Modifica rilevata nei sorgenti: "
                    "riavvio automatico di IRIS..."
                )

                stop_iris(process)
                process = start_iris()
                previous_snapshot = current_snapshot

                print(
                    "[DEV] IRIS riavviato."
                )
                continue

            return_code = process.poll()

            if return_code is not None:
                if return_code == 0:
                    return

                print(
                    "[DEV] IRIS terminato con codice "
                    f"{return_code}; riavvio automatico..."
                )

                process = start_iris()
                previous_snapshot = current_snapshot

    except KeyboardInterrupt:
        print(
            "\n[DEV] Arresto del supervisore..."
        )

        stop_iris(process)


if __name__ == "__main__":
    main()
