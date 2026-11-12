from __future__ import annotations

import sqlite3

from src.modules.core import kept_reads
from src.modules.core.kept_reads import kept
from src.modules.core.repository import Repository, schema_in_place, uncounted_workspace_writes, workspace_data_stamp
from src.modules.network import map_area_columns, map_areas
from src.modules.network.network_inventory import ensure_inventory_schema


def workspace(tmp_path) -> Repository:
    repository = Repository(tmp_path / 'workspace.db')
    repository.initialize()
    return repository


def test_a_read_is_kept_until_something_is_written_to_the_workspace(tmp_path) -> None:
    repository = workspace(tmp_path)
    repository.set_workspace_state('kept-test', 'first')
    reads: list[str] = []

    def read() -> dict[str, str]:
        reads.append('read')
        return {'value': repository.get_workspace_state('kept-test')}

    assert kept(repository, 'test', ['a'], read) == {'value': 'first'}
    given = kept(repository, 'test', ['a'], read)
    assert given == {'value': 'first'} and len(reads) == 1
    # Whoever changes what they were given changes nobody else's.
    given['value'] = 'changed by the caller'
    assert kept(repository, 'test', ['a'], read) == {'value': 'first'} and len(reads) == 1
    # Another key is another read.
    assert kept(repository, 'test', ['b'], read) == {'value': 'first'} and len(reads) == 2

    repository.set_workspace_state('kept-test', 'second')
    assert kept(repository, 'test', ['a'], read) == {'value': 'second'} and len(reads) == 3


def test_reading_the_workspace_changes_nothing_of_what_is_kept(tmp_path) -> None:
    repository = workspace(tmp_path)
    repository.set_workspace_state('kept-test', 'first')
    stamp = workspace_data_stamp(repository.db_path)
    # SQLite creates and removes the write-ahead log of the database as connections open and close: it tells nothing.
    for _ in range(3):
        assert repository.get_workspace_state('kept-test') == 'first'
        with sqlite3.connect(f'file:{repository.db_path}?mode=ro', uri=True) as connection:
            connection.execute('SELECT COUNT(*) FROM workspace_state').fetchone()
    assert workspace_data_stamp(repository.db_path) == stamp


def test_uncounted_writes_keep_what_was_read_and_best_effort_writes_do_not(tmp_path) -> None:
    repository = workspace(tmp_path)
    repository.set_workspace_state('settings', 'first')
    reads: list[int] = []

    def read() -> str:
        reads.append(1)
        return repository.get_workspace_state('settings')

    assert kept(repository, 'test', None, read) == 'first'
    # The last selection of a filters panel: saved on every change of it, read by nothing that is kept.
    with uncounted_workspace_writes():
        repository.set_workspace_state('selection', 'changed')
    assert repository.get_workspace_state('selection') == 'changed'
    assert kept(repository, 'test', None, read) == 'first' and len(reads) == 1
    # A best-effort update goes through a connection of its own, and is counted as every other write.
    assert repository.try_set_workspace_state('settings', 'second')
    assert kept(repository, 'test', None, read) == 'second' and len(reads) == 2


def test_the_schema_of_a_workspace_finds_the_saved_filters_that_finished_by_their_date(tmp_path) -> None:
    repository = workspace(tmp_path)
    with repository.connection() as connection:
        plan = ' '.join(str(row[3]) for row in connection.execute(
            'EXPLAIN QUERY PLAN SELECT id FROM saved_filters WHERE finished_at >= ?', ('2026-01-01',)))
    # The date is stored after the result of each Saved Filter: without its index every result was read to look at it.
    assert 'idx_saved_filters_finished' in plan


def test_nothing_is_kept_for_longer_than_its_time(tmp_path, monkeypatch) -> None:
    repository = workspace(tmp_path)
    reads: list[int] = []
    read = lambda: reads.append(1) or len(reads)
    assert kept(repository, 'test', None, read) == 1
    assert kept(repository, 'test', None, read) == 1
    monkeypatch.setattr(kept_reads, 'KEPT_SECONDS', 0.0)
    assert kept(repository, 'test', None, read) == 2


def test_a_schema_in_place_is_made_sure_of_without_writing(tmp_path) -> None:
    repository = workspace(tmp_path)
    script = 'CREATE TABLE IF NOT EXISTS kept_test (id INTEGER PRIMARY KEY); CREATE INDEX IF NOT EXISTS idx_kept_test ON kept_test (id);'
    with repository.connection() as connection:
        assert not schema_in_place(connection, script)
        connection.executescript(script)
        assert schema_in_place(connection, script)
        ensure_inventory_schema(connection)
    map_areas.ensure_table(repository)
    map_area_columns.ensure_table(repository)
    stamp = workspace_data_stamp(repository.db_path)
    # Once its tables exist, making sure of a schema reads only: the workspace is as it was (the server makes sure of
    # those of the Map Areas every half minute while idle).
    with repository.connection() as connection:
        ensure_inventory_schema(connection)
        assert connection.execute('SELECT COUNT(*) FROM inventory_cells').fetchone()[0] == 0
    map_areas.ensure_table(repository)
    map_area_columns.ensure_table(repository)
    assert workspace_data_stamp(repository.db_path) == stamp
