from __future__ import annotations

from pathlib import Path
import os
import shutil
import sqlite3
import time

# The tests already run in parallel, one process per CPU: the numerical libraries of each process keep to one thread
# (set before they are imported), or the processes of a run would contend for the CPUs with dozens of threads.
for _variable in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS'):
    os.environ.setdefault(_variable, '1')

import pytest
from fastapi.testclient import TestClient

import src.DriveTestAnalyzer as app_module
from src.config import settings
from src.modules import presentations
from src.modules.workspace_countries import set_workspace_country


BACKGROUND_UPLOAD_PATHS = (
    '/datasets-analysis/upload', '/datasets-analysis/retry/', '/workspace/reprocess-datasets',
    '/workspace/map-', '/workspace/clear-',
)


def wait_for_background_dataset_work(timeout: float = 30.0) -> None:
    """Wait until uploaded sources and their combined CDR rebuilds finish.

    Dataset sources are parsed by isolated workers after the upload response
    is returned, so tests that inspect processed rows must wait for them.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with app_module.ACTIVE_DATASET_PROCESSING_LOCK:
            datasets_busy = bool(app_module.ACTIVE_DATASET_PROCESSING)
        with app_module.AUTO_CALCULATED_FIELD_JOBS_LOCK:
            jobs_busy = any(
                job.get('status') in {'queued', 'processing'}
                for job in app_module.AUTO_CALCULATED_FIELD_JOBS.values()
            )
        if not datasets_busy and not jobs_busy:
            return
        time.sleep(0.02)


@pytest.fixture(autouse=True)
def restore_environment():
    """A test leaves the environment and the time zone of the process as it found them: the runtime settings of the
    application (Super Admin) write TZ and other variables into os.environ, and the next tests of the process would read
    their local times in that time zone."""
    saved = dict(os.environ)
    yield
    if os.environ != saved:
        os.environ.clear()
        os.environ.update(saved)
    if hasattr(time, 'tzset'):
        time.tzset()


def _prepare_client_folders(root: Path, monkeypatch: pytest.MonkeyPatch, *, create: bool) -> Path:
    """Point the application at the folders of a test under ``root`` (creating them for a new workspace); returns the
    folder of the slide templates."""
    config_dir = root / "config"
    data_dir = root / "data"
    input_dir = data_dir / "input"
    output_dir = data_dir / "output"
    export_dir = data_dir / "exports"
    slides_templates_dir = data_dir / "slides-templates"
    powerpoint_templates_dir = data_dir / "powerpoint-templates"

    if create:
        for directory in (config_dir, input_dir, output_dir, export_dir, slides_templates_dir, powerpoint_templates_dir):
            directory.mkdir(parents=True, exist_ok=True)
        shutil.copy2(app_module.PROJECT_ROOT / "assets" / "powerpoint-templates" / "Template_VodafoneThree.pptx", powerpoint_templates_dir / "Template_VodafoneThree.pptx")
        nsa_target = slides_templates_dir / "default" / "nsa" / "NSA Slide Template.csv"
        nsa_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(Path(__file__).parent / "fixtures" / "NSA Slide Template.csv", nsa_target)
        sa_target = slides_templates_dir / "default" / "sa" / "SA Slide Template.csv"
        sa_target.parent.mkdir(parents=True, exist_ok=True)
        sa_target.write_text(
            "Slide,Slide tittle,Slide Subtittle,Layout,Chart Tittle,CDR source,KPI,Chart type,Filters,Rows Split,Columns Split,Legend,Legend Position\n"
            "1,SA test template,,Title Page,,,,Title Slide,,,,,Top\n",
            encoding="utf-8",
        )

    object.__setattr__(settings, "database_path", config_dir / "application.db")
    object.__setattr__(settings, "config_dir", config_dir)
    object.__setattr__(settings, "input_dir", input_dir)
    object.__setattr__(settings, "output_dir", output_dir)
    object.__setattr__(settings, "export_dir", export_dir)
    object.__setattr__(settings, "slides_templates_dir", slides_templates_dir)
    object.__setattr__(settings, "powerpoint_templates_dir", powerpoint_templates_dir)
    app_module.repository.db_path = settings.database_path
    app_module.repository.set_global_database(settings.database_path)
    # Backups resolve their folder from the application data directory, which
    # otherwise still points to the developer's real storage-paths.conf folder.
    object.__setattr__(settings, "data_dir", data_dir)
    monkeypatch.setattr(app_module, "application_data_dir", data_dir)
    app_module.SESSIONS.clear()
    # The tests that need the presentations of the Help generate them (or a fake of them) themselves.
    monkeypatch.setattr(presentations, "GENERATE_AT_STARTUP", False)
    # Bundled Network Insights content is seeded explicitly by the tests that need it.
    return slides_templates_dir


@pytest.fixture(scope="session")
def client_workspace_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The folders of the new workspace every ``client`` test starts with, made once per test process.

    Opening the application on a new workspace creates its databases and seeds its starter content, which takes
    seconds; each test copies these folders instead and opens the application on them, as it reopens a workspace.
    """
    root = tmp_path_factory.mktemp("client-workspace")
    with pytest.MonkeyPatch.context() as monkeypatch:
        slides_templates_dir = _prepare_client_folders(root, monkeypatch, create=True)
        with TestClient(app_module.app):
            # On a busy machine the workspace is still being prepared (its starter content seeded) after the grace period
            # of the startup: it must be complete before the favourites are removed.
            assert app_module.STARTUP_READY.wait(timeout=300), 'The workspace of the tests was not ready.'
            # Tests that need a library explicitly import it; new workspaces stay empty.
            if slides_templates_dir.is_dir():
                shutil.copytree(slides_templates_dir, app_module.active_workspace.slides_templates_dir, dirs_exist_ok=True)
            app_module.register_workspace_template_files(app_module.active_workspace)
            # The test CDRs are NetCheck UK CDRs: the workspace is one of the United Kingdom, with its operators.
            set_workspace_country(app_module.repository, 'GBR')
            # The starter favourites (favourite Bundle Report Templates and Favourites Filters) are seeded explicitly by
            # the tests that need them; the others start without favourites.
            remove_starter_favourites(app_module.repository)
        wait_for_background_dataset_work()
    for database in root.rglob("*.db"):
        with sqlite3.connect(database) as connection:
            # Each test records its own start of the application, as a new workspace does.
            if connection.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'audit_logs'").fetchone():
                connection.execute("DELETE FROM audit_logs WHERE action = 'application_started'")
                connection.commit()
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    return root


def _copy_client_workspace(template: Path, root: Path) -> None:
    """The workspace of a test: a copy of the template whose registry names the folders of the test."""
    shutil.copytree(template, root, dirs_exist_ok=True)
    registry = root / "data" / "workspaces" / "workspace-registry.db"
    with sqlite3.connect(registry) as connection:
        columns = [row[1] for row in connection.execute("PRAGMA table_info(workspaces)")]
        for column in columns:
            connection.execute(
                f'UPDATE workspaces SET "{column}" = REPLACE("{column}", ?, ?) WHERE CAST("{column}" AS TEXT) LIKE ?',
                (str(template), str(root), f"{template}%"),
            )


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, client_workspace_template: Path) -> TestClient:
    _copy_client_workspace(client_workspace_template, tmp_path)
    _prepare_client_folders(tmp_path, monkeypatch, create=False)

    with TestClient(app_module.app) as test_client:
        # The workspace is ready before the test starts, also on a busy machine (see client_workspace_template).
        assert app_module.STARTUP_READY.wait(timeout=300), 'The workspace of the test was not ready.'
        original_post = test_client.post

        def post_and_wait_for_uploads(url, *args, **kwargs):
            response = original_post(url, *args, **kwargs)
            if str(url).startswith(BACKGROUND_UPLOAD_PATHS):
                wait_for_background_dataset_work()
            return response

        test_client.post = post_and_wait_for_uploads
        # httpx2, which Starlette's TestClient uses once it is installed (the anthropic SDK brings it), keeps one cookie
        # per domain: a session cookie a test sets replaces the one the server gave at sign-in, as it did with httpx.
        cookies = test_client.cookies
        set_cookie = cookies.set

        def replace_cookie(name, value, domain='', path='/'):
            for cookie in [cookie for cookie in cookies.jar if cookie.name == name]:
                cookies.jar.clear(cookie.domain, cookie.path, cookie.name)
            set_cookie(name, value, domain=domain, path=path)

        cookies.set = replace_cookie
        yield test_client


def remove_starter_favourites(repository) -> None:
    from src.modules import bundle_report_templates, saved_filters

    for favourite in bundle_report_templates.list_favourites(repository):
        bundle_report_templates.delete_favourite(repository, favourite['id'])
    for saved_filter in saved_filters.list_saved_filters(repository):
        saved_filters.delete_saved_filter(repository, saved_filter['id'])


@pytest.fixture()
def ppt_reporting_old(client: TestClient) -> TestClient:
    """PPT Reporting (old) is in no Modules Profile by default; the tests of the old module add it to the default profile."""
    default = next(profile for profile in app_module.repository.list_modules_profiles() if profile['is_default'])
    app_module.repository.save_modules_profile(default['id'], default['name'], default['description'], [*default['modules'], 'ppt-reporting-old'])
    app_module.invalidate_module_access_cache()
    return client
