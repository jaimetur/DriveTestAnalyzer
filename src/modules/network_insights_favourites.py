"""Network Insights favourites: Analysis Selections saved with a name to analyse them again.

A favourite keeps the selection of the page as the page remembers it: the value of each selection control (NR Mode,
Technology, Split by, thresholds, map grid, inventory snapshot…) and the values of each filter (Campaigns, Operators,
Vendors, area and Environments). They belong to the workspace and travel with the Network Insights Favourites element
of Admin → Import / Export / Transfer, with Full Workspace transfers and with backups.
"""
import json
import sqlite3
from datetime import datetime
from typing import Any

FAVOURITES_TABLE = 'network_insights_favourites'
FAVOURITES_FORMAT = 'drivetest-analyzer-network-insights-favourites'
MAX_FAVOURITES = 200
SCHEMA = f"""
CREATE TABLE IF NOT EXISTS {FAVOURITES_TABLE} (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    selection_json TEXT NOT NULL DEFAULT '{{}}',
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_network_insights_favourites_name ON {FAVOURITES_TABLE}(name COLLATE NOCASE);
"""


def ensure_tables(repository: Any) -> None:
    with repository.connection() as connection:
        connection.executescript(SCHEMA)


def normalize_selection(raw: Any) -> dict[str, Any]:
    """The selection as the page keeps it: ``controls`` (control ID → value or values), ``filters`` (filter ID →
    values) and ``map_group``."""
    raw = raw if isinstance(raw, dict) else {}

    def value(item: Any) -> Any:
        if isinstance(item, list):
            return [str(entry)[:200] for entry in item][:500]
        return str(item)[:200] if item is not None else ''

    controls = raw.get('controls') if isinstance(raw.get('controls'), dict) else {}
    filters = raw.get('filters') if isinstance(raw.get('filters'), dict) else {}
    return {
        'controls': {str(key)[:80]: value(item) for key, item in controls.items() if str(key).startswith('ni-')},
        'filters': {str(key)[:80]: [str(entry)[:200] for entry in item][:2000] for key, item in filters.items()
                    if str(key).startswith('ni-') and isinstance(item, list)},
        'map_group': str(raw.get('map_group') or '')[:200],
    }


def _favourite(row: sqlite3.Row) -> dict[str, Any]:
    try:
        selection = json.loads(row['selection_json'] or '{}')
    except json.JSONDecodeError:
        selection = {}
    return {'id': int(row['id']), 'name': str(row['name']), 'selection': normalize_selection(selection),
            'created_by': str(row['created_by']), 'created_at': str(row['created_at']), 'updated_at': str(row['updated_at'])}


def list_favourites(repository: Any) -> list[dict[str, Any]]:
    ensure_tables(repository)
    with repository.connection() as connection:
        rows = connection.execute(f'SELECT * FROM {FAVOURITES_TABLE} ORDER BY name COLLATE NOCASE, id').fetchall()
    return [_favourite(row) for row in rows]


def get_favourite(repository: Any, favourite_id: int) -> dict[str, Any] | None:
    ensure_tables(repository)
    with repository.connection() as connection:
        row = connection.execute(f'SELECT * FROM {FAVOURITES_TABLE} WHERE id = ?', (int(favourite_id),)).fetchone()
    return _favourite(row) if row else None


def save_favourite(repository: Any, favourite_id: int | None, name: str, selection: Any, username: str) -> dict[str, Any]:
    """Create (``favourite_id`` None) or update a favourite; names are unique, ignoring case."""
    name = ' '.join(str(name or '').split())[:120]
    if not name:
        raise ValueError('Enter a name for the favourite Analysis Selection.')
    normalized = normalize_selection(selection)
    now = datetime.now().isoformat(timespec='seconds')
    ensure_tables(repository)
    with repository.connection() as connection:
        clash = connection.execute(f'SELECT id FROM {FAVOURITES_TABLE} WHERE name = ? COLLATE NOCASE', (name,)).fetchone()
        if clash and (favourite_id is None or int(clash['id']) != int(favourite_id)):
            raise ValueError(f'A favourite Analysis Selection named "{name}" already exists.')
        if favourite_id is None:
            if connection.execute(f'SELECT COUNT(*) FROM {FAVOURITES_TABLE}').fetchone()[0] >= MAX_FAVOURITES:
                raise ValueError(f'A workspace keeps up to {MAX_FAVOURITES} favourite Analysis Selections.')
            cursor = connection.execute(
                f'INSERT INTO {FAVOURITES_TABLE} (name, selection_json, created_by, created_at, updated_at) VALUES (?, ?, ?, ?, ?)',
                (name, json.dumps(normalized, ensure_ascii=False), username, now, now))
            favourite_id = int(cursor.lastrowid)
        elif not connection.execute(f'UPDATE {FAVOURITES_TABLE} SET name = ?, selection_json = ?, updated_at = ? WHERE id = ?',
                                    (name, json.dumps(normalized, ensure_ascii=False), now, int(favourite_id))).rowcount:
            raise LookupError('The favourite Analysis Selection no longer exists.')
    return get_favourite(repository, int(favourite_id))


def delete_favourite(repository: Any, favourite_id: int) -> dict[str, Any] | None:
    favourite = get_favourite(repository, favourite_id)
    if favourite is not None:
        with repository.connection() as connection:
            connection.execute(f'DELETE FROM {FAVOURITES_TABLE} WHERE id = ?', (int(favourite_id),))
    return favourite


def export_document(repository: Any) -> bytes:
    """The favourites of a workspace as a portable document."""
    favourites = [{'name': item['name'], 'selection': item['selection'], 'created_by': item['created_by']}
                  for item in list_favourites(repository)]
    return json.dumps({'format': FAVOURITES_FORMAT, 'version': 1, 'favourites': favourites}, ensure_ascii=False,
                      indent=2).encode('utf-8')


def import_document(repository: Any, content: bytes | str, username: str) -> int:
    """Add or replace (by name) the favourites of a portable document; returns how many it had."""
    document = json.loads(content)
    if not isinstance(document, dict) or document.get('format') != FAVOURITES_FORMAT:
        raise ValueError('The file is not a DriveTest Analyzer Network Insights Favourites export.')
    existing = {item['name'].casefold(): item['id'] for item in list_favourites(repository)}
    imported = 0
    for entry in document.get('favourites') or []:
        if not isinstance(entry, dict) or not str(entry.get('name') or '').strip():
            continue
        name = ' '.join(str(entry['name']).split())[:120]
        save_favourite(repository, existing.get(name.casefold()), name, entry.get('selection'), username)
        imported += 1
    return imported
