from __future__ import annotations

import sqlite3

from src.modules.core import kept_reads
from src.modules.core.kept_reads import kept
from src.modules.core.repository import Repository, schema_in_place, workspace_data_stamp
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


def test_a_write_of_another_process_is_told_by_the_database_files(tmp_path) -> None:
    repository = workspace(tmp_path)
    repository.set_workspace_state('kept-test', 'first')
    read = lambda: repository.get_workspace_state('kept-test')
    assert kept(repository, 'test', None, read) == 'first'
    # A connection the repository does not coordinate, as another process would open.
    with sqlite3.connect(repository.db_path) as connection:
        connection.execute("UPDATE workspace_state SET value = 'second' WHERE key = 'kept-test'")
    assert kept(repository, 'test', None, read) == 'second'


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
    stamp = workspace_data_stamp(repository.db_path)
    # Once its tables exist, making sure of the inventory schema reads only: the workspace is as it was.
    with repository.connection() as connection:
        ensure_inventory_schema(connection)
        assert connection.execute('SELECT COUNT(*) FROM inventory_cells').fetchone()[0] == 0
    assert workspace_data_stamp(repository.db_path) == stamp
