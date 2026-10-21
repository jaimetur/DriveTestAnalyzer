"""The presentations of the Help, with live figures.

tools/presentations draws them (build.js) with the figures of the workspaces chosen in Super Admin. When those
figures, or the generator, change, the server generates them again in the background into APP_DATA_DIR/presentations,
and the Help shows them from there; until then, and where Node or the packages of the generator are missing, it shows
the last ones generated (at first, those kept in static/presentations).
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
import threading
import time
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GENERATOR = PROJECT_ROOT / 'tools' / 'presentations'
STATIC_PRESENTATIONS = PROJECT_ROOT / 'src' / 'web_interface' / 'static' / 'presentations'
# The workspaces whose figures the presentations show (Super Admin).
FIGURES_STATE_KEY = 'presentation_figure_workspaces'
MANIFEST = 'presentations.json'
# 1920 × 1080 pixels for a 13.33 × 7.5 inch slide, and 600 × 338 for its thumbnail (sharp on the cards of
# high-density screens).
SLIDE_DPI = 144
THUMB_DPI = 45
GENERATION_TIMEOUT_SECONDS = 600
CDR_KINDS = ('data', 'voice', 'speech')
# The CDRs whose rows the presentations count as calls (a Speech CDR measures calls of the Voice one).
CALL_KINDS = ('data', 'voice')
MAPPING_KINDS = ('mapping_vodafone', 'mapping_three', 'vendors')
GEOGRAPHICAL_KINDS = ('regions', 'clusters')
# Where Node usually is when the application does not run from a shell (a launcher of macOS, for example).
NODE_CANDIDATES = ('/opt/homebrew/bin/node', '/usr/local/bin/node', '/usr/bin/node', '/usr/bin/nodejs')


# -- figures ---------------------------------------------------------------------------------------------------------

def workspace_figures(database_path: Path | str) -> dict[str, Any]:
    """The figures of one workspace, read without changing its database: its ready datasets by type, the calls of its
    Data and Voice CDRs, the campaigns of its CDRs and its Non-Qualified calls with their follow-up."""
    figures: dict[str, Any] = dict.fromkeys((
        'cdr_rows', 'cdr_calls', 'cdrs', 'inventory_rows', 'mapping_rows', 'geographical_datasets', 'nq_calls', 'nq_calls_total',
        'nq_followed', 'nq_rca', 'nq_comments'), 0)
    campaigns: set[str] = set()
    try:
        with closing(sqlite3.connect(f'file:{Path(database_path)}?mode=ro', uri=True, timeout=5)) as connection:
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            if 'dataset_profiles' in tables:
                for kind, count, rows in connection.execute(
                        "SELECT dataset_kind, COUNT(*), COALESCE(SUM(row_count), 0) FROM dataset_profiles WHERE status = 'ready' "
                        'GROUP BY dataset_kind'):
                    if kind in CDR_KINDS:
                        figures['cdrs'] += count
                        figures['cdr_rows'] += rows
                        if kind in CALL_KINDS:
                            figures['cdr_calls'] += rows
                    elif kind == 'network_inventory':
                        figures['inventory_rows'] += rows
                    elif kind in MAPPING_KINDS:
                        figures['mapping_rows'] += rows
                    elif kind in GEOGRAPHICAL_KINDS:
                        figures['geographical_datasets'] += count
                if 'cdr_catalogues' in tables:
                    for (value,) in connection.execute(
                            'SELECT catalogue.campaigns_json FROM cdr_catalogues catalogue JOIN dataset_profiles profile '
                            "ON profile.dataset_id = catalogue.dataset_id WHERE profile.status = 'ready' "
                            f"AND profile.dataset_kind IN ({', '.join('?' for _ in CDR_KINDS)})", CDR_KINDS):
                        try:
                            campaigns.update(str(item) for item in json.loads(value or '[]') if item)
                        except (TypeError, ValueError):
                            continue
            for key, query in (
                    ('nq_calls', 'SELECT COUNT(*) FROM nq_calls'),
                    ('nq_calls_total', 'SELECT COUNT(*) FROM nq_call_population WHERE is_latest'),
                    ('nq_followed', 'SELECT COUNT(*) FROM nq_call_tracking'),
                    ('nq_rca', 'SELECT COUNT(*) FROM nq_rca_results'),
                    ('nq_comments', "SELECT COUNT(*) FROM nq_call_comments WHERE COALESCE(deleted_at, '') = ''")):
                table = query.split(' FROM ', 1)[1].split()[0]
                if table in tables:
                    figures[key] = int(connection.execute(query).fetchone()[0] or 0)
    except sqlite3.Error:
        pass
    figures['campaigns'] = sorted(campaigns)
    return figures


def ready_workspaces(core: Any) -> list[Any]:
    return [workspace for workspace in core.workspace_registry.list()
            if getattr(workspace, 'status', 'ready') in {'ready', '', None} and Path(workspace.database_path).is_file()]


def chosen_workspace_ids(repository: Any) -> list[str]:
    try:
        value = json.loads(repository.get_application_state(FIGURES_STATE_KEY) or '[]')
    except (TypeError, ValueError):
        return []
    return [str(item) for item in value if item] if isinstance(value, list) else []


def figure_workspaces(core: Any) -> list[Any]:
    """The workspaces chosen in Super Admin, or, while none is, the one with the most CDR rows."""
    workspaces = ready_workspaces(core)
    chosen = set(chosen_workspace_ids(core.repository))
    selected = [workspace for workspace in workspaces if workspace.id in chosen]
    if selected or not workspaces:
        return selected
    return [max(workspaces, key=lambda workspace: workspace_figures(workspace.database_path)['cdr_rows'])]


def product_figures() -> dict[str, int]:
    """The figures of the tool itself: its Help chapters, releases and automated tests (those of the presentations kept
    in the repository where the tests are not, as in a Docker image)."""
    help_root = PROJECT_ROOT / 'help'
    changelog = PROJECT_ROOT / 'CHANGELOG.md'
    tests_root = PROJECT_ROOT / 'tests'
    if tests_root.is_dir():
        tests = sum(1 for path in tests_root.glob('test_*.py') for line in path.read_text(encoding='utf-8', errors='replace').splitlines()
                    if line.lstrip().startswith(('def test_', 'async def test_')))
    else:
        tests = int(_read_manifest(STATIC_PRESENTATIONS).get('figures', {}).get('tests') or 0)
    return {
        'help_chapters': len(list(help_root.glob('*.md'))) if help_root.is_dir() else 0,
        'releases': changelog.read_text(encoding='utf-8', errors='replace').count('\n## Release:') if changelog.is_file() else 0,
        'tests': tests,
    }


def presentation_figures(core: Any) -> dict[str, Any]:
    """Every figure the presentations show: those of the chosen workspaces added up, the users and their roles, the
    workspaces of the server and the tool itself."""
    selected = figure_workspaces(core)
    totals: dict[str, Any] = {}
    campaigns: set[str] = set()
    for workspace in selected:
        figures = workspace_figures(workspace.database_path)
        campaigns.update(f'{workspace.id}:{campaign}' for campaign in figures.pop('campaigns'))
        for key, value in figures.items():
            totals[key] = totals.get(key, 0) + value
    users = [row for row in core.repository.list_users() if row['active']]
    roles: dict[str, int] = {}
    for row in users:
        roles[str(row['role'])] = roles.get(str(row['role']), 0) + 1
    return {
        'workspaces': [workspace.name for workspace in selected], 'month': datetime.now().strftime('%B %Y'),
        **{key: totals.get(key, 0) for key in ('cdr_rows', 'cdr_calls', 'cdrs', 'inventory_rows', 'mapping_rows', 'nq_calls', 'nq_calls_total',
                                               'nq_followed', 'nq_rca', 'nq_comments')},
        'campaigns': len(campaigns), 'users': len(users), 'roles': roles,
        'workspace_list': [{'name': workspace.name, 'campaigns': len(workspace_figures(workspace.database_path)['campaigns'])}
                           for workspace in ready_workspaces(core)],
        **product_figures(),
    }


def generator_signature() -> str:
    """What the presentations look like: a change of the generator draws them again."""
    digest = hashlib.sha256()
    for name in ('build.js', 'art.js', 'package.json'):
        path = GENERATOR / name
        digest.update(path.read_bytes() if path.is_file() else b'')
    return digest.hexdigest()


def figures_key(figures: dict[str, Any]) -> str:
    return hashlib.sha256((json.dumps(figures, sort_keys=True) + generator_signature()).encode()).hexdigest()[:20]


# -- generation ------------------------------------------------------------------------------------------------------

def _read_manifest(folder: Path | None) -> dict[str, Any]:
    if folder is None:
        return {}
    try:
        return json.loads((folder / MANIFEST).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def render_slides(folder: Path, manifest: dict[str, Any]) -> None:
    """Every slide of the presentations of ``folder`` as ``<id>/slide-NN.png`` (the viewer) and ``<id>/thumb-NN.png``
    (its list and the cards of the Help), converted by LibreOffice as the previews of the Bundle Report Templates."""
    from src.modules.pptx_to_docx import document_pdf, pdf_page_images

    for presentation in manifest['presentations']:
        pdf = document_pdf((folder / presentation['file']).read_bytes(), 'pptx', whole=True)
        if pdf is None:
            raise RuntimeError('LibreOffice and PyMuPDF are needed to render the slides.')
        slides = pdf_page_images(pdf, SLIDE_DPI)
        expected = sum(len(section['slides']) for section in presentation['sections'])
        if len(slides) != expected:
            raise RuntimeError(f"{presentation['file']} has {len(slides)} slides; presentations.json lists {expected}.")
        target = folder / presentation['id']
        target.mkdir(exist_ok=True)
        for stale in target.glob('*.png'):
            stale.unlink()
        for number, (slide, thumb) in enumerate(zip(slides, pdf_page_images(pdf, THUMB_DPI)), 1):
            (target / f'slide-{number:02d}.png').write_bytes(slide)
            (target / f'thumb-{number:02d}.png').write_bytes(thumb)


def node_executable() -> str | None:
    return shutil.which('node') or shutil.which('nodejs') or next((path for path in NODE_CANDIDATES if Path(path).is_file()), None)


class PresentationGenerator:
    """Generates the presentations into ``<data dir>/presentations/current``, one generation at a time, and tells which
    version the Help shows."""

    def __init__(self, data_dir: Any, log: Any) -> None:
        # (Both read when used: the data directory and the App Events of the application as they are then.)
        self.data_dir = data_dir
        self.log = log
        self.lock = threading.Lock()
        self.running = False
        self.failed_key = ''
        self.error = ''

    @property
    def root(self) -> Path:
        return Path(self.data_dir()) / 'presentations'

    def current(self) -> Path | None:
        folder = self.root / 'current'
        return folder if (folder / MANIFEST).is_file() else None

    def manifest(self) -> dict[str, Any]:
        """The presentations shown: the last generated, else those of the repository."""
        return _read_manifest(self.current()) or _read_manifest(STATIC_PRESENTATIONS)

    def file(self, relative: str) -> Path | None:
        for root in (self.current(), STATIC_PRESENTATIONS):
            if root is None:
                continue
            target = (root / relative).resolve()
            if root.resolve() in target.parents and target.is_file():
                return target
        return None

    @staticmethod
    def unavailable() -> str:
        """Why the presentations cannot be generated here, or an empty text."""
        if node_executable() is None:
            return 'Node.js is not installed on this server.'
        if not (GENERATOR / 'node_modules' / 'pptxgenjs').is_dir():
            return 'The packages of the generator are not installed (npm install in tools/presentations).'
        return ''

    def ensure(self, figures: dict[str, Any], requested_by: str = 'system') -> bool:
        """Generate the presentations again in the background when their figures or generator changed (once per change
        when it fails); True when a generation runs."""
        key = figures_key(figures)
        with self.lock:
            if self.running:
                return True
            if key in {self.manifest().get('key'), self.failed_key} or self.unavailable():
                return False
            self.running = True
        threading.Thread(target=self._generate, args=(figures, key, requested_by), name='presentations', daemon=True).start()
        return True

    def _generate(self, figures: dict[str, Any], key: str, requested_by: str) -> None:
        started = time.monotonic()
        self.root.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix='.building-', dir=self.root))
        try:
            (work / 'figures.json').write_text(json.dumps(figures), encoding='utf-8')
            output = work / 'presentations'
            subprocess.run([node_executable(), str(GENERATOR / 'build.js'), str(output)], cwd=GENERATOR, check=True,
                           capture_output=True, timeout=GENERATION_TIMEOUT_SECONDS,
                           env={**os.environ, 'PRESENTATION_FIGURES': str(work / 'figures.json')})
            manifest = _read_manifest(output)
            render_slides(output, manifest)
            manifest.update(key=key, figures=figures, generated_at=datetime.now().astimezone().isoformat(timespec='seconds'))
            (output / MANIFEST).write_text(json.dumps(manifest, indent=2), encoding='utf-8')
            # The new presentations replace the shown ones at once.
            current = self.root / 'current'
            previous = self.root / f'.previous-{int(time.time())}'
            if current.exists():
                current.rename(previous)
            output.rename(current)
            shutil.rmtree(previous, ignore_errors=True)
            self.failed_key, self.error = '', ''
            self.log('system', 'generate_presentations', json.dumps({
                'workspaces': figures['workspaces'], 'presentations': [item['id'] for item in manifest['presentations']],
                'seconds': round(time.monotonic() - started, 1), 'requested_by': requested_by,
            }, ensure_ascii=False))
        except Exception as exc:  # noqa: BLE001 - the Help keeps the last presentations and App Events tells why.
            detail = getattr(exc, 'stderr', b'') or b''
            self.failed_key = key
            self.error = (detail.decode('utf-8', errors='replace')[-600:] if isinstance(detail, bytes) else str(detail)) or str(exc)
            self.log('system', 'generate_presentations_failed', json.dumps({
                'workspaces': figures['workspaces'], 'error': self.error, 'requested_by': requested_by,
            }, ensure_ascii=False))
        finally:
            shutil.rmtree(work, ignore_errors=True)
            with self.lock:
                self.running = False

    def status(self) -> dict[str, Any]:
        manifest = self.manifest()
        return {'generated_at': manifest.get('generated_at', ''), 'workspaces': (manifest.get('figures') or {}).get('workspaces', []),
                'running': self.running, 'error': self.error, 'unavailable': self.unavailable()}


_GENERATOR: PresentationGenerator | None = None


def presentation_settings(core: Any) -> dict[str, Any]:
    """What the Presentations panel of Super Admin shows: every workspace, those chosen, and the presentations."""
    chosen = set(chosen_workspace_ids(core.repository))
    return {
        'workspaces': [{'id': workspace.id, 'name': workspace.name, 'chosen': workspace.id in chosen} for workspace in ready_workspaces(core)],
        'status': _GENERATOR.status() if _GENERATOR else {},
    }


def install_presentation_routes(core: Any) -> None:
    from fastapi import Depends, Form, HTTPException
    from fastapi.responses import FileResponse, RedirectResponse

    global _GENERATOR
    _GENERATOR = generator = PresentationGenerator(lambda: core.settings.data_dir, lambda *event: core.repository.try_add_log(*event))
    app = core.app

    @app.get('/api/presentations')
    def presentations(user=Depends(core.optional_user)) -> dict[str, Any]:
        # Opening them brings them up to date (a signed-in user's visit), meanwhile showing the last ones.
        if user is not None:
            generator.ensure(presentation_figures(core), user.username)
        manifest = generator.manifest()
        return {**manifest, 'base': '/presentations/files', 'updating': generator.running}

    @app.get('/presentations/files/{relative:path}')
    def presentation_file(relative: str):
        path = generator.file(relative)
        if path is None:
            raise HTTPException(status_code=404, detail='Presentation file not found.')
        return FileResponse(path, headers={'Cache-Control': 'no-cache'})

    @app.post('/super-admin/presentations')
    def save_presentation_workspaces(workspace_ids: list[str] = Form([]), user=Depends(core.super_admin_user)):
        workspaces = {workspace.id: workspace.name for workspace in ready_workspaces(core)}
        chosen = [workspace_id for workspace_id in dict.fromkeys(workspace_ids) if workspace_id in workspaces]
        before = [workspaces.get(workspace_id, workspace_id) for workspace_id in chosen_workspace_ids(core.repository)]
        core.repository.set_application_state(FIGURES_STATE_KEY, json.dumps(chosen))
        core.repository.try_add_log(user.username, 'save_presentation_figures', json.dumps({
            'workspaces': [workspaces[workspace_id] for workspace_id in chosen], 'before': before,
        }, ensure_ascii=False))
        generator.ensure(presentation_figures(core), user.username)
        return RedirectResponse('/super-admin#presentations', status_code=303)
