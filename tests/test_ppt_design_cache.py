import gzip
import json
import os
import sqlite3
import time
import zlib
from contextlib import closing
from pathlib import Path

from src.modules import ppt_design_cache


def workspace_database(tmp_path: Path) -> Path:
    database = tmp_path / 'UK' / 'UK.db'
    database.parent.mkdir(parents=True)
    database.touch()
    return database


def test_a_value_is_written_whole_and_read_back_and_an_unreadable_file_is_deleted(tmp_path):
    database = workspace_database(tmp_path)
    path = ppt_design_cache.chart_path(database, 'ab' * 32)
    assert ppt_design_cache.read(path) is None and not ppt_design_cache.exists(path)

    assert ppt_design_cache.write(path, {'series': [1, 2, 3]})
    assert path.parent == database.parent / '.ppt-designer-cache' / 'charts' / 'ab'
    assert ppt_design_cache.read(path) == {'series': [1, 2, 3]} and ppt_design_cache.exists(path)
    # Written under a temporary name and renamed: nothing else is left in the folder.
    assert [item.name for item in path.parent.iterdir()] == [path.name]

    # A file cut short (a crash, a full disk) is deleted and read as missing.
    path.write_bytes(path.read_bytes()[:-6])
    assert ppt_design_cache.read(path) is None and not path.exists()
    path.write_bytes(b'')
    assert ppt_design_cache.read(path) is None and not path.exists()
    with gzip.open(path, 'wb') as handle:
        handle.write(b'[1, 2]')
    assert ppt_design_cache.read(path) is None and not path.exists()


def test_the_least_recently_used_go_beyond_the_size_kept_and_the_unused_and_temporary_files_go(tmp_path, monkeypatch):
    database = workspace_database(tmp_path)
    paths = [ppt_design_cache.chart_path(database, f'{index:02d}' * 32) for index in range(6)]
    for age, path in enumerate(paths):
        assert ppt_design_cache.write(path, {'values': os.urandom(3000).hex()})
        os.utime(path, (time.time() - 3600 * (10 - age),) * 2)
    size = paths[0].stat().st_size
    root = ppt_design_cache.root_of(database)
    ppt_design_cache._indexes.pop(str(root), None)
    # The oldest is read again: it becomes the most recently used.
    assert ppt_design_cache.read(paths[0]) is not None

    monkeypatch.setenv('DRIVETEST_ANALYZER_PPT_CHART_CACHE_MB', str(size * 6.5 / 1024 ** 2))
    newest = ppt_design_cache.chart_path(database, 'ff' * 32)
    assert ppt_design_cache.write(newest, {'values': os.urandom(3000).hex()})
    # Over the size kept: the least recently used go, down to nine tenths of it.
    kept = [path for path in (*paths, newest) if path.exists()]
    assert paths[0] in kept and newest in kept and paths[1] not in kept
    files, total = ppt_design_cache.usage(database)
    assert files == len(kept) and total == sum(path.stat().st_size for path in kept) <= size * 6.5 * 0.9

    # Read again later: what nothing used for UNUSED_DAYS days goes, and the temporary files of writes cut short.
    stale = time.time() - (ppt_design_cache.UNUSED_DAYS + 1) * 86400
    os.utime(kept[0], (stale, stale))
    temporary = newest.with_name(f'.{newest.name}.1.2.tmp')
    temporary.write_bytes(b'cut')
    os.utime(temporary, (time.time() - 2 * 3600,) * 2)
    recent_temporary = newest.with_name(f'.{newest.name}.3.4.tmp')
    recent_temporary.write_bytes(b'being written')
    ppt_design_cache._indexes.pop(str(root), None)
    assert ppt_design_cache.usage(database)[0] == len(kept) - 1
    assert not kept[0].exists() and not temporary.exists() and recent_temporary.exists()


def test_clear_sets_the_folder_aside_at_once(tmp_path):
    database = workspace_database(tmp_path)
    path = ppt_design_cache.preparation_path(database, 'design-a', ppt_design_cache.preparation_key(9, 'design-a', 'f'))
    assert ppt_design_cache.write(path, {'design_id': 'design-a'})
    assert ppt_design_cache.has_preparation(database, 'design-a')
    assert not ppt_design_cache.has_preparation(database, 'design-b')

    trash = ppt_design_cache.clear(database)
    assert trash is not None and trash.exists() and ppt_design_cache.trash_folders(database.parent) == [trash]
    assert not ppt_design_cache.root_of(database).exists()
    assert not ppt_design_cache.has_preparation(database, 'design-a')
    assert ppt_design_cache.usage(database) == (0, 0)
    assert ppt_design_cache.clear(database) is None


def test_what_earlier_versions_kept_in_the_database_moves_to_the_folder(tmp_path):
    database = workspace_database(tmp_path)
    model, manifest = {'series': [4]}, {'version': 9, 'design_id': 'design-a', 'fingerprint': 'f1', 'payload': {}}
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute('CREATE TABLE design_chart_models (cache_key TEXT PRIMARY KEY, model BLOB, size INTEGER)')
        connection.execute('CREATE TABLE design_preview_manifests (cache_key TEXT PRIMARY KEY, design_id TEXT, '
                           'manifest BLOB, size INTEGER)')
        connection.execute('INSERT INTO design_chart_models VALUES (?, ?, 1)', ('cd' * 32, zlib.compress(json.dumps(model).encode())))
        connection.execute('INSERT INTO design_chart_models VALUES (?, ?, 1)', ('ef' * 32, b'not compressed'))
        for key, value in (('old-1', manifest), ('old-2', {**manifest, 'version': 8})):
            connection.execute('INSERT INTO design_preview_manifests VALUES (?, ?, ?, 1)',
                               (key, 'design-a', zlib.compress(json.dumps(value).encode())))

    def name(value):
        return ppt_design_cache.preparation_key(9, value['design_id'], value['fingerprint']) if value['version'] == 9 else None

    moved = ppt_design_cache.move_database_rows(database, name)
    assert (moved['charts'], moved['preparations']) == (1, 1) and moved['bytes'] > 0
    assert ppt_design_cache.read(ppt_design_cache.chart_path(database, 'cd' * 32)) == model
    assert ppt_design_cache.read(ppt_design_cache.preparation_path(database, 'design-a', name(manifest))) == manifest
    with closing(sqlite3.connect(database)) as connection:
        assert not connection.execute(
            "SELECT name FROM sqlite_master WHERE name IN ('design_chart_models', 'design_preview_manifests')").fetchall()
    # Nothing left to move.
    assert ppt_design_cache.move_database_rows(database, name) == {'charts': 0, 'preparations': 0, 'bytes': 0}
