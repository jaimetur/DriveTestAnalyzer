from __future__ import annotations

from threading import Event, Thread

from src.modules.repository import Repository


def test_workspace_writes_wait_for_the_active_transaction_while_reads_continue(tmp_path) -> None:
    repository = Repository(tmp_path / 'workspace.db')
    repository.initialize()
    repository.set_workspace_state('coordination-test', 'initial')

    writer_started = Event()
    release_writer = Event()
    errors: list[Exception] = []

    def first_writer() -> None:
        try:
            with repository.connection() as connection:
                connection.execute(
                    'UPDATE workspace_state SET value = ? WHERE key = ?',
                    ('first', 'coordination-test'),
                )
                writer_started.set()
                assert release_writer.wait(5)
        except Exception as exc:  # pragma: no cover - asserted below
            errors.append(exc)

    first = Thread(target=first_writer)
    first.start()
    assert writer_started.wait(5)

    # WAL readers must remain available while the coordinated writer is open.
    assert repository.get_workspace_state('coordination-test') == 'initial'

    second_finished = Event()

    def second_writer() -> None:
        try:
            repository.set_workspace_state('coordination-test', 'second')
            second_finished.set()
        except Exception as exc:  # pragma: no cover - asserted below
            errors.append(exc)

    second = Thread(target=second_writer)
    second.start()
    assert not second_finished.wait(0.1)
    release_writer.set()
    first.join(5)
    second.join(5)

    assert not first.is_alive()
    assert not second.is_alive()
    assert errors == []
    assert repository.get_workspace_state('coordination-test') == 'second'


def test_explicit_commit_releases_writer_without_closing_connection(tmp_path) -> None:
    repository = Repository(tmp_path / 'workspace.db')
    repository.initialize()

    with repository.connection() as connection:
        connection.execute(
            'INSERT INTO workspace_state (key, value) VALUES (?, ?)',
            ('commit-release', 'first'),
        )
        connection.commit()

        finished = Event()
        worker = Thread(target=lambda: (
            repository.set_workspace_state('commit-release', 'second'), finished.set()
        ))
        worker.start()
        assert finished.wait(2)
        worker.join(2)

    assert repository.get_workspace_state('commit-release') == 'second'


def test_shared_connection_lends_one_connection_to_the_reads_of_its_block(tmp_path, monkeypatch) -> None:
    import sqlite3

    repository = Repository(tmp_path / 'workspace.db')
    repository.initialize()
    repository.set_workspace_state('shared-test', 'value')
    opened: list[str] = []
    connect = sqlite3.connect

    def counting_connect(database, *args, **kwargs):
        opened.append(str(database))
        return connect(database, *args, **kwargs)

    monkeypatch.setattr(sqlite3, 'connect', counting_connect)
    in_thread: list[int] = []
    with repository.shared_connection():
        with repository.shared_connection():
            # Another Repository of the same workspace shares it too.
            other = Repository(tmp_path / 'workspace.db')
            assert [repository.get_workspace_state('shared-test') for _ in range(5)] == ['value'] * 5
            assert other.get_workspace_state('shared-test') == 'value'
            with repository.connection() as first, other.connection() as second:
                assert first is second
        # Another thread opens its own connection.
        thread = Thread(target=lambda: in_thread.append(len(repository.get_workspace_state('shared-test') or '')))
        thread.start()
        thread.join(5)
    assert in_thread == [5]
    assert opened.count(str(tmp_path / 'workspace.db')) == 2
    # After the block every read opens its own connection again.
    repository.get_workspace_state('shared-test')
    assert opened.count(str(tmp_path / 'workspace.db')) == 3
