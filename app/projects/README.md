# IRIS Projects

M6 introduce la gestione persistente di progetti e task.

## Modello

- Project: nome, descrizione, stato e timestamp.
- Task: titolo, descrizione, progetto opzionale, stato, priorità, scadenza e timestamp.

## Stati

Project: `active`, `completed`, `archived`.

Task: `todo`, `in_progress`, `completed`, `cancelled`.

## Tool

- `create_project`
- `list_projects`
- `update_project`
- `create_task`
- `list_tasks`
- `update_task`

La cancellazione non viene introdotta in M6: per i progetti si usa l'archiviazione e per i task lo stato `cancelled`.
