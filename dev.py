from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DEV_LOG = ROOT / ".iris-dev.log"
POLL_INTERVAL_SECONDS = 0.5
CHANGE_SETTLE_SECONDS = 0.4


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


def compile_python_sources(
    root: Path = ROOT,
) -> bool:
    """
    Controlla la sintassi dei sorgenti prima di riavviare IRIS.

    Se il file appena salvato è ancora incompleto o contiene un errore
    sintattico, il processo corrente non viene terminato: il reload verrà
    ritentato al successivo salvataggio.
    """
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "compileall",
            "-q",
            str(root / "app"),
        ],
        cwd=root,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )

    if completed.returncode == 0:
        return True

    write_dev_log(
        "Reload annullato: errore di sintassi nei sorgenti."
    )

    if completed.stderr.strip():
        write_dev_log(
            completed.stderr.strip()
        )

    return False


def wait_for_stable_snapshot(
    root: Path = ROOT,
) -> dict[Path, tuple[int, int]]:
    """
    Aspetta che il file system smetta di cambiare per un breve intervallo.

    Serve a evitare reload mentre un editor sta ancora scrivendo il file.
    """
    snapshot = snapshot_python_files(root)

    while True:
        time.sleep(
            CHANGE_SETTLE_SECONDS
        )

        stable_snapshot = snapshot_python_files(root)

        if stable_snapshot == snapshot:
            return stable_snapshot

        snapshot = stable_snapshot


def write_dev_log(
    message: str,
) -> None:
    """Scrive gli eventi del supervisore in un file separato dalla UI."""
    timestamp = time.strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    try:
        with DEV_LOG.open(
            "a",
            encoding="utf-8",
        ) as handle:
            handle.write(
                f"[{timestamp}] {message}\n"
            )
    except OSError:
        # Il logging non deve mai compromettere il supervisore.
        pass


def start_iris() -> subprocess.Popen:
    """Avvia IRIS come processo figlio usando lo stesso interprete Python."""
    write_dev_log(
        "Avvio del processo IRIS."
    )

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

    write_dev_log(
        "Arresto del processo IRIS."
    )

    process.terminate()

    try:
        process.wait(
            timeout=5.0,
        )
    except subprocess.TimeoutExpired:
        write_dev_log(
            "IRIS non ha terminato entro il timeout; "
            "uso kill."
        )

        process.kill()
        process.wait()


def main() -> None:
    """
    Supervisore di sviluppo di IRIS.

    Avvio:
        py dev.py

    Da quel momento IRIS viene avviato automaticamente e ogni modifica
    ai file Python dentro app/ provoca un reload automatico.

    Il supervisore non scrive mai nella console interattiva: tutti i suoi
    messaggi finiscono in .iris-dev.log, evitando di corrompere la UI
    prompt_toolkit di IRIS.

    Prima di un reload:
    - attende che la modifica sia stabile;
    - controlla la sintassi;
    - solo dopo sostituisce il processo IRIS.

    La memoria persistente nel database non viene persa. Lo stato
    esclusivamente in-memory della sessione viene invece ricreato dopo
    ogni reload.
    """
    previous_snapshot = snapshot_python_files()
    process = start_iris()

    write_dev_log(
        "Supervisore avviato in modalità auto-reload."
    )

    try:
        while True:
            time.sleep(
                POLL_INTERVAL_SECONDS
            )

            current_snapshot = snapshot_python_files()

            if current_snapshot != previous_snapshot:
                settled_snapshot = (
                    wait_for_stable_snapshot()
                )

                if settled_snapshot == previous_snapshot:
                    continue

                if not compile_python_sources():
                    previous_snapshot = settled_snapshot
                    continue

                write_dev_log(
                    "Modifica rilevata nei sorgenti: "
                    "reload automatico."
                )

                stop_iris(
                    process
                )

                process = start_iris()
                previous_snapshot = settled_snapshot

                write_dev_log(
                    "Reload completato."
                )

                continue

            return_code = process.poll()

            if return_code is not None:
                if return_code == 0:
                    write_dev_log(
                        "IRIS terminato normalmente."
                    )
                    return

                write_dev_log(
                    "IRIS terminato con codice "
                    f"{return_code}; riavvio automatico."
                )

                process = start_iris()
                previous_snapshot = current_snapshot

    except KeyboardInterrupt:
        write_dev_log(
            "Arresto del supervisore richiesto."
        )

        stop_iris(
            process
        )


if __name__ == "__main__":
    main()
