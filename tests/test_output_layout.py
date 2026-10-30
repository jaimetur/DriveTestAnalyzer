from __future__ import annotations

import sqlite3
from pathlib import Path

from src.modules.output_layout import migrate_output_layout


def _workspace(tmp_path: Path) -> tuple[Path, Path]:
    output_dir = tmp_path / 'output'
    database_path = tmp_path / 'workspace.db'
    with sqlite3.connect(database_path) as connection:
        connection.execute('CREATE TABLE design_ppt_jobs (id INTEGER PRIMARY KEY, output_path TEXT)')
        connection.execute('CREATE TABLE report_task_runs (id INTEGER PRIMARY KEY, output_dir TEXT)')
    return output_dir, database_path


def _write(path: Path, content: bytes = b'x') -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def test_former_output_layout_moves_into_module_folders(tmp_path: Path) -> None:
    output_dir, database_path = _workspace(tmp_path)
    design = _write(output_dir / 'dashboards' / '20260915_120000 - Design' / 'design.pptx')
    run_dir = output_dir / 'reporting' / '20261006_062102 - All Modules - run 2'
    _write(run_dir / 'artifact.pptx')
    _write(output_dir / 'charts' / '20260907-120000' / 'chart-1.png')
    report = _write(output_dir / 'reports' / '20260929-050129_NetCheck_CDR_NSA_operator-comparison' / 'report.pptx')
    _write(output_dir / 'reports' / '20261006_042512_summary_network_insights.pptx')
    _write(output_dir / 'reports' / 'NetCheck_UK_CDR_Voice_report_6160225e5b.docx')
    _write(output_dir / 'reports' / '20261006_042512_summary_dataset_analysis.pptx')
    _write(output_dir / 'reports' / 'imported.pptx')
    with sqlite3.connect(database_path) as connection:
        connection.execute('INSERT INTO design_ppt_jobs (output_path) VALUES (?)', (str(design),))
        connection.execute('INSERT INTO report_task_runs (output_dir) VALUES (?)', (str(run_dir),))

    assert migrate_output_layout(output_dir, database_path) is True

    reports = output_dir / 'reports'
    assert sorted(path.name for path in output_dir.iterdir()) == ['reports']
    assert sorted(path.name for path in reports.iterdir()) == [
        'cdr-analysis', 'network-insights', 'ppt-designs', 'reporting-jobs', 'reports-charts-old', 'reports-old']
    assert (reports / 'reports-charts-old' / '20260907-120000' / 'chart-1.png').is_file()
    assert (reports / 'network-insights' / '20261006_042512_summary_network_insights.pptx').is_file()
    assert sorted(path.name for path in (reports / 'cdr-analysis').iterdir()) == [
        '20261006_042512_summary_dataset_analysis.pptx', 'NetCheck_UK_CDR_Voice_report_6160225e5b.docx']
    assert (reports / 'reports-old' / 'imported.pptx').is_file()
    # The reports of PPT Reporting (old), a module the tool no longer has, keep their former folder.
    assert (reports / 'reports-old' / report.parent.name / 'report.pptx').is_file()
    with sqlite3.connect(database_path) as connection:
        stored = [connection.execute(f'SELECT {column} FROM {table}').fetchone()[0] for table, column in (
            ('design_ppt_jobs', 'output_path'), ('report_task_runs', 'output_dir'))]
    assert stored == [
        str(reports / 'ppt-designs' / '20260915_120000 - Design' / 'design.pptx'),
        str(reports / 'reporting-jobs' / '20261006_062102 - All Modules - run 2'),
    ]
    assert all(Path(path).exists() for path in stored)
    assert migrate_output_layout(output_dir, database_path) is False


def test_migration_merges_folders_without_overwriting_current_files(tmp_path: Path) -> None:
    output_dir, database_path = _workspace(tmp_path)
    current = _write(output_dir / 'reports' / 'ppt-designs' / 'job' / 'design.pptx', b'current')
    _write(output_dir / 'dashboards' / 'job' / 'design.pptx', b'former')
    _write(output_dir / 'dashboards' / 'other' / 'design.pptx', b'other')

    migrate_output_layout(output_dir, database_path)

    assert current.read_bytes() == b'current'
    assert (output_dir / 'reports' / 'ppt-designs' / 'other' / 'design.pptx').read_bytes() == b'other'
    assert (output_dir / 'dashboards' / 'job' / 'design.pptx').read_bytes() == b'former'


def test_the_ppt_jobs_of_ppt_dashboards_move_to_ppt_designer_with_their_charts(tmp_path: Path) -> None:
    output_dir, database_path = _workspace(tmp_path)
    deck = _write(output_dir / 'reports' / 'dashboards' / '20261020_101010 - Weekly' / 'deck.pptx')
    _write(output_dir / 'reports' / 'dashboards' / '20261020_101010 - Weekly' / 'dashboard-charts' / 'manifest.json', b'{}')
    with sqlite3.connect(database_path) as connection:
        connection.execute('INSERT INTO design_ppt_jobs (output_path) VALUES (?)', (str(deck),))

    assert migrate_output_layout(output_dir, database_path) is True

    job = output_dir / 'reports' / 'ppt-designs' / '20261020_101010 - Weekly'
    assert (job / 'deck.pptx').is_file() and (job / 'design-charts' / 'manifest.json').read_bytes() == b'{}'
    assert not (output_dir / 'reports' / 'dashboards').exists() and not (job / 'dashboard-charts').exists()
    with sqlite3.connect(database_path) as connection:
        assert connection.execute('SELECT output_path FROM design_ppt_jobs').fetchone()[0] == str(job / 'deck.pptx')


def test_the_ppt_jobs_kept_under_reports_designs_move_to_ppt_designs(tmp_path: Path) -> None:
    output_dir, database_path = _workspace(tmp_path)
    deck = _write(output_dir / 'reports' / 'designs' / '20261029_080000 - Weekly' / 'deck.pptx')
    with sqlite3.connect(database_path) as connection:
        connection.execute('INSERT INTO design_ppt_jobs (output_path) VALUES (?)', (str(deck),))

    assert migrate_output_layout(output_dir, database_path) is True

    moved = output_dir / 'reports' / 'ppt-designs' / '20261029_080000 - Weekly' / 'deck.pptx'
    assert moved.is_file() and not (output_dir / 'reports' / 'designs').exists()
    with sqlite3.connect(database_path) as connection:
        assert connection.execute('SELECT output_path FROM design_ppt_jobs').fetchone()[0] == str(moved)
