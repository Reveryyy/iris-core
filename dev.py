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
    Restituisce uno snapshot dei sorgenti Python di IRIS.

    Vengono osservati i file dentro app/ e ignorate le directory
    __pycache__. Lo snapshot può essere confrontato direttamente per
    rilevare modifiche, aggiunte e rimozioni.
    """
    snapshot: dict[Path, tuple[int, int]] = {}

    watch_directory = root / "app"

    try:
        if not watch_directory.exists():
            return snapshot
    except OSError:
        return snapshot

    for path in watch_directory.rglob("*.py"):
        if "__pycache__" in path.parts:
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
    """Avvia IRIS come processo figlio usando lo stesso interprete Python."""
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
    """Termina IRIS e forza la chiusura se non risponde entro il timeout."""
    if process.poll() is not None:
        return

    process.terminate()

    try:
        process.wait(
            timeout=5.0,
        )
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def main() -> None:
    """
    Supervisore di sviluppo di IRIS.

    Avvio:
        py dev.py

    Da quel momento IRIS viene avviato automaticamente e ogni modifica
    ai file Python dentro app/ provoca un riavvio automatico del processo.

    La memoria persistente nel database non viene persa. Lo stato
    esclusivamente in-memory della sessione viene invece ricreato dopo
    ogni reload.
    """
    previous_snapshot = snapshot_python_files()
    process = start_iris()

    print(
        "[DEV] IRIS avviato in modalità auto-reload."
    )
    print(
        "[DEV] Modifica un file in app/ per applicare automaticamente "
        "le nuove modifiche."
    )

    try:
        while True:
            time.sleep(
                0.5
            )

            current_snapshot = snapshot_python_files()

            if current_snapshot != previous_snapshot:
                print(
                    "[DEV] Modifica rilevata nei sorgenti: "
                    "riavvio automatico di IRIS..."
                )

                stop_iris(
                    process
                )

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

        stop_iris(
            process
        )


if __name__ == "__main__":
    main()
