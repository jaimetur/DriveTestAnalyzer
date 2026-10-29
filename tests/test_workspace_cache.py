from __future__ import annotations

from pathlib import Path

from src.modules import bundle_report_templates, inventory_insights, ppt_design_cache, scoring_cache, workspace_cache


def _write(path: Path, content: bytes = b'x') -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


class _Repository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path


def test_every_module_keeps_its_cache_in_the_cache_folder_of_the_workspace(tmp_path: Path) -> None:
    database = _write(tmp_path / 'UK' / 'UK.db', b'')
    repository = _Repository(database)
    cache = tmp_path / 'UK' / '.cache'

    scoring_cache.write(repository, 'trends', 'k' * 64, {'value': 1})
    assert (cache / 'scoring' / 'trends' / f"{'k' * 64}.json.gz").is_file()
    assert scoring_cache.read(repository, 'trends', 'k' * 64) == {'value': 1}
    assert inventory_insights._cells_cache_folder(repository) == cache / 'network-insights'
    assert ppt_design_cache.root_of(database) == cache / 'ppt-designer'
    assert bundle_report_templates.section_cache_root(repository) == cache / 'bundle-reports'
    assert sorted(item.name for item in (tmp_path / 'UK').iterdir()) == ['.cache', 'UK.db']


def test_the_cache_folders_of_earlier_versions_move_to_the_cache_folder(tmp_path: Path) -> None:
    root = tmp_path / 'UK'
    _write(root / '.scoring-cache' / 'trends' / 'a.json.gz')
    _write(root / '.network-insights-cache' / 'snapshot-base-1.json')
    _write(root / '.ppt-designer-cache' / 'charts' / 'ab' / 'ab.json.gz')
    _write(root / '.ppt-designer-cache.removing-0123456789ab' / 'charts' / 'cd' / 'cd.json.gz')
    _write(root / 'output' / 'reports' / 'bundle-reports' / 'cache' / 'section-1' / 'section.json')
    report = _write(root / 'output' / 'reports' / 'bundle-reports' / '20261029_120000 - 1a2b3c4d' / 'report.pptx')
    # A module that already has its folder keeps it: the folder of the earlier version goes.
    _write(root / '.cache' / 'network-insights' / 'snapshot-base-2.json')
    store = _write(root / '.cdr-store' / 'data' / '1' / 'part-0.parquet')
    upload = _write(root / '.upload-sessions' / ('f' * 32) / 'manifest.json')

    found = workspace_cache.move_legacy_folders(root)

    assert sorted(found) == ['.network-insights-cache', '.ppt-designer-cache',
                             '.ppt-designer-cache.removing-0123456789ab', '.scoring-cache',
                             'output/reports/bundle-reports/cache']
    cache = root / '.cache'
    assert (cache / 'scoring' / 'trends' / 'a.json.gz').is_file()
    assert [item.name for item in (cache / 'network-insights').iterdir()] == ['snapshot-base-2.json']
    assert (cache / 'ppt-designer' / 'charts' / 'ab' / 'ab.json.gz').is_file()
    assert ppt_design_cache.trash_folders(root) == [cache / 'ppt-designer.removing-0123456789ab']
    assert (cache / 'bundle-reports' / 'section-1' / 'section.json').is_file()
    # Only caches move: the generated reports, the columnar copies of the CDRs and the uploads stay where they are.
    assert report.is_file() and store.is_file() and upload.is_file()
    assert sorted(item.name for item in root.iterdir()) == ['.cache', '.cdr-store', '.upload-sessions', 'output']
    assert workspace_cache.move_legacy_folders(root) == []
