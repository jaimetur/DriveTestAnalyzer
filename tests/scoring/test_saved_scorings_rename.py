"""The Saved Filters of earlier versions became Saved Scorings (v0.12.7): workspaces, packages and App Events of before
keep working."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from src.modules.core.app_event_details import app_event_origin, describe_app_event
from src.modules.core.repository import Repository
from src.modules.scoring import saved_scorings
from tests.scoring.test_saved_scorings_reuse import _three_cdrs, _workspace

import src.DriveTestAnalyzer as app_module


def test_a_workspace_with_saved_filters_keeps_them_as_saved_scorings(tmp_path: Path) -> None:
    repository = _workspace(tmp_path, 'w')
    ids = _three_cdrs(repository, tmp_path / 'w')
    saved, _ = saved_scorings.save_saved_scoring(repository, ids, ['Operator'], 'NSA')
    # As a workspace of an earlier version: the table, and its indexes, under their earlier names.
    with sqlite3.connect(repository.db_path) as connection:
        connection.execute('ALTER TABLE saved_scorings RENAME TO saved_filters')
        for suffix in ('order', 'finished'):
            connection.execute(f'DROP INDEX IF EXISTS idx_saved_scorings_{suffix}')
        connection.execute('CREATE INDEX idx_saved_filters_order ON saved_filters(pinned DESC, last_used_at DESC)')
    reopened = Repository(repository.db_path, global_db_path=tmp_path / 'global.db')
    reopened.initialize()
    with sqlite3.connect(repository.db_path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        indexes = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}
    assert 'saved_scorings' in tables and 'saved_filters' not in tables
    assert {'idx_saved_scorings_order', 'idx_saved_scorings_finished'} <= indexes and 'idx_saved_filters_order' not in indexes
    assert [item['id'] for item in saved_scorings.list_saved_scorings(reopened)] == [saved['id']]


def test_saved_filters_exported_by_earlier_versions_are_imported(tmp_path: Path) -> None:
    source = _workspace(tmp_path, 'source')
    ids = _three_cdrs(source, tmp_path / 'source')
    saved, _ = saved_scorings.save_saved_scoring(source, ids, ['Operator'], 'NSA')
    saved_scorings.update_saved_scoring(source, saved['id'], name='Weekly view', pinned=True)
    document = saved_scorings.saved_scorings_document(source)
    earlier = {**{key: value for key, value in document.items() if key != 'saved_scorings'},
               'format': 'drivetest-analyzer-saved-filters', 'saved_filters': document['saved_scorings']}
    target = _workspace(tmp_path, 'target')
    _three_cdrs(target, tmp_path / 'target')
    assert saved_scorings.import_saved_scorings(target, earlier) == 1
    assert [item['name'] for item in saved_scorings.list_saved_scorings(target)] == ['Weekly view']
    # Packages and backups of before name the element Favourites Filters.
    assert app_module.current_archive_name('scoring-favourites-filters') == 'scoring-favourite-scorings'
    assert app_module.current_archive_name('scoring_favourites_filters') == 'scoring_favourite_scorings'
    assert 'scoring-favourites-filters/scoring-favourites-filters.json' in app_module.FAVOURITE_SCORINGS_ARCHIVE_NAMES


def test_app_events_recorded_with_saved_filters_read_as_saved_scorings() -> None:
    details = {'saved_filter_id': 9, 'name': 'Q3 London', 'starred': True}
    assert describe_app_event('open_saved_filter', details) == describe_app_event(
        'open_saved_scoring', {'saved_scoring_id': 9, 'name': 'Q3 London', 'starred': True})
    assert 'saved scoring ID 9 (favourite)' in describe_app_event('open_saved_filter', details)
    assert app_event_origin('open_saved_filter', details) == app_event_origin('open_saved_scoring', details)
