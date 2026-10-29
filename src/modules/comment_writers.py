"""LLM writers of the generated comments of PPT Designer: Kiro CLI (the default LLM) and Claude, set up in Super Admin.

The rules of ``design_comments`` always read the charts first. An LLM writer receives the same facts and the rules
comments as a draft, rewrites them in a more natural way and returns JSON; every figure it writes must be one of the
facts (``validate_comments``), otherwise the rules comment is kept. Kiro CLI runs headless with no tools; each writer
takes the API key of the server or that of the user who generates (Reporting Jobs: their owner), as Super Admin
chooses. The keys live in a file of the configuration folder of this server (never in its database, exports, transfers
or backups) and are never sent back to the browser. Kiro CLI is the screened package a super-admin uploads (Ericsson
forbids the versions downloaded from AWS): it is unpacked in the configuration folder, so it survives every image update.
"""
from __future__ import annotations

import io
import json
import os
import platform
import re
import shutil
import subprocess
import tarfile
import tempfile
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse

SETTINGS_STATE_KEY = 'ai_comment_writers_v1'
CREDENTIALS_FILE = 'ai-credentials.json'
# A Kiro CLI already installed on the machine (a local run, a team server with ``module add kiro_cli``).
KIRO_CLI_ENVIRONMENT = 'DRIVETEST_ANALYZER_KIRO_CLI'
# The screened Kiro CLI packages (one folder per version) in the Ericsson Artifactory, and the Kiro CLI release notes.
KIRO_CLI_DOWNLOAD_URL = 'https://arm.seli.gic.ericsson.se/artifactory/proj-AmazonQ-Kiro-generic-local/kiro-cli/'
KIRO_CLI_RELEASE_NOTES_URL = 'https://kiro.dev/changelog/cli/'
ENGINE_RULES = 'rules'
ENGINE_KIRO_CLI = 'kiro_cli'
ENGINE_KIRO_BRIEF = 'kiro_brief'
ENGINE_CLAUDE = 'claude'
PROVIDERS = (ENGINE_KIRO_CLI, ENGINE_KIRO_BRIEF, ENGINE_CLAUDE)
# The writers the server runs itself (the Kiro Brief is exported to Kiro IDE and imported back).
SERVER_ENGINES = (ENGINE_KIRO_CLI, ENGINE_CLAUDE)
ENGINE_LABELS = {ENGINE_RULES: 'Rules', ENGINE_KIRO_CLI: 'Kiro CLI', ENGINE_KIRO_BRIEF: 'Kiro Brief', ENGINE_CLAUDE: 'Claude'}
CLAUDE_MODELS = (('claude-opus-5-5', 'Claude Opus 5.5'), ('claude-sonnet-5-5', 'Claude Sonnet 5.5'), ('claude-haiku-5-5', 'Claude Haiku 5.5'))
CLAUDE_EFFORTS = ('low', 'medium', 'high')
DEFAULT_SETTINGS: dict[str, Any] = {
    'enabled': [], 'default': ENGINE_KIRO_CLI, 'claude_model': CLAUDE_MODELS[0][0], 'claude_effort': 'medium',
    'kiro_model': '', 'timeout_seconds': 120, 'kiro_cli': {}, 'kiro_key_source': 'user', 'claude_key_source': 'server',
}
MAX_COMMENT_LENGTH = 500
KIRO_STATUS_SECONDS = 300
ANSI_SEQUENCE = re.compile(r'\x1b\[[0-9;?]*[A-Za-z]')
NUMBER = re.compile(r'[−-]?\d[\d,]*(?:\.\d+)?')
CAMPAIGN = re.compile(r'\b\d{4}-Q[1-4](?:-[A-Za-z]+)?\b')

STYLE_GUIDE = '''You write the analysis comments of one slide of a drive-test benchmark PowerPoint for radio engineers.

You receive the facts read from the charts of the slide (exact medians, means, shares, tails, correlations,
classes and failure counts per operator and campaign) and the comments a rules engine wrote from them. Rewrite them as the best comments
for the slide:
- English, radio-technical, one sentence per comment, at most 220 characters; no headings, no bullets, no emojis.
- Lead with the Focus operators when the facts name them; otherwise lead with the leader and the largest change.
- Use only figures that appear in the facts or in the rules comments, written the same way (units, decimals, the
  minus sign −, campaign names such as 2026-Q2). Never compute, round differently or invent a figure.
- Never name a series, operator, vendor or class listed as hidden.
- Prefer connecting facts (a change and where to act, such as the weak tail) to repeating them; say "on par" or
  "stable" where the rules do.
- Write at most the number of comments the brief allows.
Reply with JSON only: {"comments": ["…", "…"]}.'''
COMMENTS_SCHEMA = {
    'type': 'object',
    'properties': {'comments': {'type': 'array', 'items': {'type': 'string'}}},
    'required': ['comments'],
    'additionalProperties': False,
}


class WriterError(RuntimeError):
    """An LLM writer could not write the comments; the rules comments are used instead."""


# -- settings ---------------------------------------------------------------------------------------------------------

def load_settings(repository: Any) -> dict[str, Any]:
    """The AI writer settings of Super Admin over their defaults."""
    try:
        stored = json.loads(repository.get_application_state(SETTINGS_STATE_KEY) or '{}')
    except (TypeError, ValueError):
        stored = {}
    settings = {**DEFAULT_SETTINGS, **(stored if isinstance(stored, dict) else {})}
    settings['enabled'] = [provider for provider in settings.get('enabled') or [] if provider in PROVIDERS]
    if settings.get('default') not in (*SERVER_ENGINES, ENGINE_RULES):
        settings['default'] = ENGINE_KIRO_CLI
    return settings


def save_settings(repository: Any, values: dict[str, Any]) -> dict[str, Any]:
    """Validate and save the AI writer settings (the keys are saved apart, see ``set_server_key``)."""
    settings = load_settings(repository)
    enabled = [provider for provider in PROVIDERS if provider in set(values.get('enabled') or [])]
    default = str(values.get('default') or ENGINE_KIRO_CLI)
    if default not in (*SERVER_ENGINES, ENGINE_RULES):
        raise ValueError('Choose Rules, Kiro CLI or Claude as the default writer.')
    model = str(values.get('claude_model') or CLAUDE_MODELS[0][0])
    if model not in {item for item, _label in CLAUDE_MODELS}:
        raise ValueError('Choose one of the Claude models offered.')
    effort = str(values.get('claude_effort') or 'medium')
    if effort not in CLAUDE_EFFORTS:
        raise ValueError('Choose low, medium or high effort for Claude.')
    try:
        timeout = int(values.get('timeout_seconds') or DEFAULT_SETTINGS['timeout_seconds'])
    except (TypeError, ValueError) as exc:
        raise ValueError('The timeout must be a number of seconds.') from exc
    if not 15 <= timeout <= 900:
        raise ValueError('The timeout must be between 15 and 900 seconds.')
    sources = {}
    for name in ('kiro', 'claude'):
        source = str(values.get(f'{name}_key_source') or DEFAULT_SETTINGS[f'{name}_key_source'])
        if source not in KEY_SOURCES:
            raise ValueError('Choose the key of the server or the key of each user.')
        sources[f'{name}_key_source'] = source
    settings.update({
        **sources,
        'enabled': enabled, 'default': default, 'claude_model': model, 'claude_effort': effort,
        'kiro_model': re.sub(r'[^\w.:/-]', '', str(values.get('kiro_model') or '').strip())[:80], 'timeout_seconds': timeout,
    })
    repository.set_application_state(SETTINGS_STATE_KEY, json.dumps(settings, sort_keys=True))
    return settings


def available_engines(repository: Any) -> dict[str, Any]:
    """The writers a user can choose when generating comments: Rules and the server writers Super Admin enabled, with
    the default one, and whether the Kiro Brief is enabled."""
    settings = load_settings(repository)
    engines = [ENGINE_RULES, *[engine for engine in SERVER_ENGINES if engine in settings['enabled']]]
    default = settings['default'] if settings['default'] in engines else ENGINE_RULES
    return {
        'engines': [{'id': engine, 'label': ENGINE_LABELS[engine]} for engine in engines], 'default': default,
        'kiro_brief': ENGINE_KIRO_BRIEF in settings['enabled'],
    }


def resolve_engine(repository: Any, requested: str | None) -> str:
    """The writer of a request: the one asked for when it is enabled, the default for an empty request, else Rules."""
    choices = available_engines(repository)
    ids = {item['id'] for item in choices['engines']}
    requested = str(requested or '').strip()
    if not requested:
        return choices['default']
    return requested if requested in ids else ENGINE_RULES


# -- credentials ------------------------------------------------------------------------------------------------------

def _credentials_path(config_dir: Path) -> Path:
    return Path(config_dir) / CREDENTIALS_FILE


def _read_credentials(config_dir: Path) -> dict[str, Any]:
    try:
        data = json.loads(_credentials_path(config_dir).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_credentials(config_dir: Path, data: dict[str, Any]) -> None:
    """Write the keys of this server, readable only by its own user."""
    path = _credentials_path(config_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, sort_keys=True), encoding='utf-8')
    os.chmod(temporary, 0o600)
    temporary.replace(path)


# Where each LLM writer takes its API key from, as Super Admin chooses: the one key of the server, or each user's own key
# (saved in the user menu, API keys; Reporting Jobs use that of their owner).
KEY_SOURCES = ('server', 'user')
KEY_NAMES = {ENGINE_KIRO_CLI: 'kiro', ENGINE_CLAUDE: 'claude'}


def server_key(config_dir: Path, engine: str) -> str:
    return str(_read_credentials(config_dir).get(f'{KEY_NAMES[engine]}_api_key') or '')


def set_server_key(config_dir: Path, engine: str, key: str) -> None:
    """Save (or with an empty key remove) the API key of the server for a writer."""
    data = _read_credentials(config_dir)
    if key:
        data[f'{KEY_NAMES[engine]}_api_key'] = key.strip()
    else:
        data.pop(f'{KEY_NAMES[engine]}_api_key', None)
    _write_credentials(config_dir, data)


def user_key(config_dir: Path, engine: str, username: str) -> str:
    return str((_read_credentials(config_dir).get(f'{KEY_NAMES[engine]}_api_keys') or {}).get(str(username).casefold()) or '')


def set_user_key(config_dir: Path, engine: str, username: str, key: str) -> None:
    """Save (or with an empty key remove) the personal API key of a user for a writer."""
    data = _read_credentials(config_dir)
    keys = dict(data.get(f'{KEY_NAMES[engine]}_api_keys') or {})
    if key:
        keys[str(username).casefold()] = key.strip()
    else:
        keys.pop(str(username).casefold(), None)
    data[f'{KEY_NAMES[engine]}_api_keys'] = keys
    _write_credentials(config_dir, data)


def key_source(settings: dict[str, Any], engine: str) -> str:
    return settings.get(f'{KEY_NAMES[engine]}_key_source') or DEFAULT_SETTINGS[f'{KEY_NAMES[engine]}_key_source']


def writer_key(settings: dict[str, Any], config_dir: Path, engine: str, username: str) -> tuple[str, str]:
    """The API key a writer uses for a user, and where it comes from (the server or the user)."""
    source = key_source(settings, engine)
    key = server_key(config_dir, engine) if source == 'server' else user_key(config_dir, engine, username)
    return key, source


def user_key_engines(repository: Any) -> list[str]:
    """The enabled writers whose key each user saves in the user menu."""
    settings = load_settings(repository)
    return [engine for engine in SERVER_ENGINES if engine in settings['enabled'] and key_source(settings, engine) == 'user']


# -- Kiro CLI installation ----------------------------------------------------------------------------------------------

def kiro_cli_root(config_dir: Path) -> Path:
    return Path(config_dir) / 'tools' / 'kiro-cli'


def kiro_home(config_dir: Path) -> Path:
    """The home of Kiro CLI on this server (its settings and logs), in the configuration folder."""
    return Path(config_dir) / 'tools' / 'kiro-home'


MACH_O_MAGICS = {b'\xcf\xfa\xed\xfe', b'\xce\xfa\xed\xfe', b'\xca\xfe\xba\xbe', b'\xfe\xed\xfa\xcf'}


def binary_architecture(path: Path) -> str:
    """The system and processor an executable is built for, from its header (Linux x86_64, macOS, script…)."""
    try:
        header = Path(path).read_bytes()[:20]
    except OSError:
        return 'unknown'
    if header[:4] == b'\x7fELF' and len(header) >= 20:
        machine = int.from_bytes(header[18:20], 'little' if header[5] == 1 else 'big')
        return 'Linux ' + {0x3E: 'x86_64', 0xB7: 'aarch64', 0x03: 'x86'}.get(machine, f'ELF machine {machine}')
    if header[:4] in MACH_O_MAGICS:
        return 'macOS'
    if header[:2] == b'#!':
        return 'script'
    return 'not an executable'


def server_platform() -> str:
    """The system and processor of this server, as a package names them (Linux x86_64, macOS arm64)."""
    return f"{ {'Darwin': 'macOS'}.get(platform.system(), platform.system()) } {platform.machine()}".strip()


def _is_executable_file(path: Path) -> bool:
    """A program a package may hold: a Linux (ELF) or macOS (Mach-O) binary, or a script."""
    try:
        with open(path, 'rb') as handle:
            header = handle.read(4)
    except OSError:
        return False
    return header == b'\x7fELF' or header in MACH_O_MAGICS or header[:2] == b'#!'


def _ar_members(content: bytes) -> dict[str, bytes]:
    """The members of a Debian package (an ar archive)."""
    if not content.startswith(b'!<arch>\n'):
        raise ValueError('This .deb file is not a Debian package.')
    members, position = {}, 8
    while position + 60 <= len(content):
        header = content[position:position + 60]
        name = header[:16].decode('ascii', 'replace').strip().rstrip('/')
        size = int(header[48:58].decode('ascii').strip() or 0)
        members[name] = content[position + 60:position + 60 + size]
        position += 60 + size + (size % 2)
    return members


def _extract_dmg(content: bytes, target: Path) -> None:
    """Copy the kiro-cli programs of a macOS disk image (Kiro CLI.dmg, with Kiro CLI.app inside), mounted read-only."""
    if platform.system() != 'Darwin':
        raise ValueError('Kiro CLI.dmg is the package for macOS: on this Linux server upload the kiro-cli.deb of the '
                         'Windows_WSL folder of Artifactory.')
    image, mount = target.parent / 'package.dmg', target.parent / 'mount'
    image.write_bytes(content)
    mount.mkdir()
    attached = subprocess.run(['hdiutil', 'attach', '-readonly', '-nobrowse', '-noautoopen', '-mountpoint', str(mount),
                               str(image)], input='Y\n', capture_output=True, text=True, timeout=180, check=False)
    if attached.returncode != 0:
        raise ValueError(f'The disk image could not be opened: {(attached.stderr or attached.stdout).strip()[-300:]}')
    try:
        for path in mount.rglob('kiro-cli*'):
            if path.is_file() and not path.is_symlink() and _is_executable_file(path):
                destination = target / path.relative_to(mount)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, destination)
    finally:
        subprocess.run(['hdiutil', 'detach', str(mount), '-force'], capture_output=True, timeout=60, check=False)


def _extract(filename: str, content: bytes, target: Path) -> None:
    """Unpack a package as Artifactory gives it: a .deb, a .dmg (on macOS), a .zip, a tar archive, or the executable
    itself."""
    name = filename.casefold()
    if name.endswith('.dmg'):
        _extract_dmg(content, target)
    elif name.endswith('.deb'):
        members = _ar_members(content)
        data_name = next((member for member in members if member.startswith('data.tar')), None)
        if data_name is None:
            raise ValueError('This Debian package has no data archive.')
        if data_name.endswith('.zst'):
            raise ValueError('This package is compressed with zstd: upload the kiro-cli executable or a .zip of it.')
        with tarfile.open(fileobj=io.BytesIO(members[data_name]), mode='r:*') as archive:
            archive.extractall(target, filter='data')
    elif name.endswith('.zip'):
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            for member in archive.infolist():
                destination = (target / member.filename).resolve()
                if not str(destination).startswith(str(target.resolve())):
                    raise ValueError('The archive has a path outside its folder.')
            archive.extractall(target)
            for member in archive.infolist():
                mode = member.external_attr >> 16
                if mode and not member.is_dir():
                    os.chmod(target / member.filename, mode & 0o777)
    elif re.search(r'\.(tar|tar\.gz|tgz|tar\.xz|tar\.bz2)$', name):
        with tarfile.open(fileobj=io.BytesIO(content), mode='r:*') as archive:
            archive.extractall(target, filter='data')
    else:
        (target / 'kiro-cli').write_bytes(content)


def _run_version(path: Path, home: Path) -> str:
    environment = {**os.environ, 'HOME': str(home), 'PATH': f'{path.parent}{os.pathsep}{os.environ.get("PATH", "")}'}
    completed = subprocess.run([str(path), '--version'], capture_output=True, text=True, timeout=20, env=environment, check=False)
    output = ANSI_SEQUENCE.sub('', (completed.stdout or completed.stderr or '')).strip()
    if completed.returncode != 0 or not output:
        raise ValueError(f'kiro-cli --version failed: {output[-300:] or f"exit code {completed.returncode}"}')
    return output.splitlines()[0][:80]


def install_kiro_cli(config_dir: Path, filename: str, content: bytes) -> dict[str, Any]:
    """Install the uploaded Kiro CLI package in the configuration folder and check that it runs on this server."""
    if not content:
        raise ValueError('Choose the Kiro CLI package downloaded from Artifactory.')
    root = kiro_cli_root(config_dir)
    root.mkdir(parents=True, exist_ok=True)
    home = kiro_home(config_dir)
    home.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=root) as scratch:
        unpacked = Path(scratch) / 'unpacked'
        unpacked.mkdir()
        _extract(filename, content, unpacked)
        # The programs of the package (kiro-cli and its kiro-cli-* helpers), those of a bin folder (MacOS in an app)
        # first: a .deb also holds shell completions, icons and menu entries named kiro-cli.
        candidates = sorted((path for path in unpacked.rglob('*') if path.is_file() and path.name.startswith('kiro-cli')
                             and _is_executable_file(path)),
                            key=lambda path: (path.parent.name not in {'bin', 'MacOS'}, len(path.parts)))
        executables: dict[str, Path] = {}
        for path in candidates:
            executables.setdefault(path.name, path)
        if 'kiro-cli' not in executables:
            raise ValueError('The package has no kiro-cli executable.')
        staged = Path(scratch) / 'bin'
        staged.mkdir()
        for name, path in executables.items():
            shutil.copy2(path, staged / name)
            os.chmod(staged / name, 0o755)
        architecture, server = binary_architecture(staged / 'kiro-cli'), server_platform()
        if architecture.startswith('Linux') and server.startswith('macOS'):
            raise ValueError(f'This Kiro CLI is a {architecture} package: it runs on the Linux server of the app (Docker), '
                             f'not on this {server} computer. On a Mac, set {KIRO_CLI_ENVIRONMENT} to a kiro-cli '
                             'installed on it.')
        try:
            version = _run_version(staged / 'kiro-cli', home)
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            detail = exc.strerror if isinstance(exc, OSError) and exc.strerror else str(exc)
            raise ValueError(f'This Kiro CLI does not run on this server ({architecture} package, {server} server): '
                             f'{detail}') from exc
        slug = re.sub(r'[^\w.-]+', '-', version).strip('-') or 'kiro-cli'
        destination = root / slug
        if destination.exists():
            shutil.rmtree(destination)
        shutil.move(str(staged), destination)
    return {
        'path': str(destination / 'kiro-cli'), 'version': version, 'architecture': architecture,
        'installed_at': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'file': filename,
    }


def save_kiro_cli(repository: Any, installed: dict[str, Any], username: str) -> dict[str, Any]:
    settings = load_settings(repository)
    settings['kiro_cli'] = {**installed, 'installed_by': username}
    repository.set_application_state(SETTINGS_STATE_KEY, json.dumps(settings, sort_keys=True))
    _STATUS_CACHE.clear()
    return settings


_STATUS_CACHE: dict[tuple[str, float], tuple[float, dict[str, Any]]] = {}


def kiro_cli_path(repository: Any) -> Path | None:
    override = os.environ.get(KIRO_CLI_ENVIRONMENT, '').strip()
    if override:
        return Path(override)
    path = str((load_settings(repository).get('kiro_cli') or {}).get('path') or '')
    return Path(path) if path else None


def kiro_cli_status(repository: Any, config_dir: Path) -> dict[str, Any]:
    """Whether Kiro CLI is installed and runs on this server (checked again every few minutes, so an image update that
    breaks it shows in Super Admin)."""
    path = kiro_cli_path(repository)
    status: dict[str, Any] = {'installed': False, 'server_architecture': server_platform(),
                              'from_environment': bool(os.environ.get(KIRO_CLI_ENVIRONMENT, '').strip())}
    if path is None:
        return status
    try:
        modified = path.stat().st_mtime
    except OSError:
        return {**status, 'path': str(path), 'error': 'The installed kiro-cli is missing: upload the package again.'}
    cached = _STATUS_CACHE.get((str(path), modified))
    if cached and time.monotonic() - cached[0] < KIRO_STATUS_SECONDS:
        return cached[1]
    status.update({'installed': True, 'path': str(path), 'architecture': binary_architecture(path)})
    try:
        status['version'] = _run_version(path, kiro_home(config_dir))
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        status['error'] = f'Kiro CLI no longer runs on this server: {exc}'
    _STATUS_CACHE[(str(path), modified)] = (time.monotonic(), status)
    return status


# -- writing ----------------------------------------------------------------------------------------------------------

def _prompt(brief: dict[str, Any]) -> str:
    return json.dumps({key: brief[key] for key in ('limit', 'focus_operators', 'hidden', 'charts', 'rules_comments') if key in brief},
                      ensure_ascii=False)


def _comments_from(document: Any) -> list[str]:
    comments = document.get('comments') if isinstance(document, dict) else None
    if not isinstance(comments, list):
        raise WriterError('The reply has no list of comments.')
    return [re.sub(r'\s+', ' ', str(item)).strip() for item in comments if str(item).strip()]


def _json_reply(text: str) -> Any:
    """The last JSON object of a reply that holds the comments (Kiro CLI may print other text around it)."""
    decoder = json.JSONDecoder()
    clean = ANSI_SEQUENCE.sub('', text or '')
    found = None
    for match in re.finditer(r'\{', clean):
        try:
            document, _end = decoder.raw_decode(clean[match.start():])
        except ValueError:
            continue
        if isinstance(document, dict) and 'comments' in document:
            found = document
    if found is None:
        raise WriterError('The reply has no JSON with the comments.')
    return found


def write_with_kiro_cli(brief: dict[str, Any], settings: dict[str, Any], cli: Path | None, api_key: str,
                        config_dir: Path, source: str = 'user') -> tuple[list[str], dict[str, Any]]:
    """Kiro CLI headless (``kiro-cli chat --no-interactive``) with the API key of the user or of the server and no tools
    trusted, run in an empty folder so it has nothing to read."""
    if cli is None:
        raise WriterError('Kiro CLI is not installed on this server.')
    if not api_key:
        raise WriterError('Add your Kiro API key in the user menu (API keys) to write comments with Kiro.' if source == 'user'
                          else 'Kiro has no API key of the server: Super Admin saves it in AI Comment Writers.')
    home = kiro_home(config_dir)
    home.mkdir(parents=True, exist_ok=True)
    command = [str(cli), 'chat', '--no-interactive']
    if settings.get('kiro_model'):
        command += ['--model', str(settings['kiro_model'])]
    command.append(f'{STYLE_GUIDE}\n\nBrief of the slide (JSON):\n{_prompt(brief)}')
    environment = {**os.environ, 'KIRO_API_KEY': api_key, 'HOME': str(home),
                   'PATH': f'{cli.parent}{os.pathsep}{os.environ.get("PATH", "")}', 'NO_COLOR': '1'}
    with tempfile.TemporaryDirectory() as empty:
        try:
            completed = subprocess.run(command, capture_output=True, text=True, cwd=empty, env=environment,
                                       timeout=int(settings.get('timeout_seconds') or 120), check=False)
        except subprocess.TimeoutExpired as exc:
            raise WriterError(f'Kiro CLI did not answer within {settings.get("timeout_seconds")} seconds.') from exc
        except OSError as exc:
            raise WriterError(f'Kiro CLI could not start: {exc}') from exc
    if completed.returncode != 0:
        detail = ANSI_SEQUENCE.sub('', completed.stderr or completed.stdout or '').strip()[-300:]
        raise WriterError(f'Kiro CLI failed (exit code {completed.returncode}): {detail}')
    return _comments_from(_json_reply(completed.stdout)), {'model': str(settings.get('kiro_model') or '')}


def write_with_claude(brief: dict[str, Any], settings: dict[str, Any], api_key: str,
                      source: str = 'server') -> tuple[list[str], dict[str, Any]]:
    """Claude with structured output; a refusal routes to Anthropic's default fallback model on the server. Without a
    key of the server it uses the credentials of the server's environment (ANTHROPIC_API_KEY)."""
    if source == 'user' and not api_key:
        raise WriterError('Add your Claude API key in the user menu (API keys) to write comments with Claude.')
    try:
        import anthropic
    except ImportError as exc:
        raise WriterError('The anthropic package is not installed on this server.') from exc
    client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
    try:
        response = client.beta.messages.create(
            model=settings.get('claude_model') or CLAUDE_MODELS[0][0],
            max_tokens=16000,
            betas=['server-side-fallback-2026-07-01'],
            fallbacks='default',
            system=[{'type': 'text', 'text': STYLE_GUIDE, 'cache_control': {'type': 'ephemeral'}}],
            output_config={'effort': settings.get('claude_effort') or 'medium',
                           'format': {'type': 'json_schema', 'schema': COMMENTS_SCHEMA}},
            messages=[{'role': 'user', 'content': f'Brief of the slide (JSON):\n{_prompt(brief)}'}],
        )
    except anthropic.AuthenticationError as exc:
        raise WriterError('Your Claude API key was rejected.' if source == 'user' else 'The Claude API key of the server was rejected.') from exc
    except anthropic.RateLimitError as exc:
        raise WriterError('Claude is rate limited right now: try again in a minute.') from exc
    except anthropic.APIStatusError as exc:
        raise WriterError(f'Claude failed ({exc.status_code}): {exc.message}') from exc
    except anthropic.APIConnectionError as exc:
        raise WriterError('This server cannot reach the Claude API.') from exc
    if response.stop_reason == 'refusal':
        raise WriterError('Claude declined to write these comments.')
    text = next((block.text for block in response.content if block.type == 'text'), '')
    try:
        document = json.loads(text)
    except ValueError as exc:
        raise WriterError('Claude did not reply with JSON.') from exc
    usage = getattr(response, 'usage', None)
    return _comments_from(document), {
        'model': str(getattr(response, 'model', '') or settings.get('claude_model') or ''),
        'input_tokens': int(getattr(usage, 'input_tokens', 0) or 0), 'output_tokens': int(getattr(usage, 'output_tokens', 0) or 0),
    }


def _numbers(text: str) -> list[float]:
    values = []
    for token in NUMBER.findall(text):
        try:
            values.append(round(abs(float(token.replace('−', '-').replace(',', ''))), 2))
        except ValueError:
            continue
    return values


def allowed_numbers(brief: dict[str, Any]) -> set[float]:
    """Every figure a comment may write: those of the facts (as they read and rounded as comments round them), of the
    rules comments and of the class edges."""
    allowed: set[float] = set()

    def add(value: Any, percent: bool = False) -> None:
        try:
            number = abs(float(value)) * (100 if percent else 1)
        except (TypeError, ValueError):
            return
        allowed.update({round(number, 2), round(number, 1), float(round(number))})

    for text in brief.get('rules_comments') or []:
        allowed.update(_numbers(CAMPAIGN.sub(' ', text)))
    for chart in brief.get('charts') or []:
        for edge in chart.get('bucket_edges') or []:
            add(edge)
        share = chart.get('family') in {'share', 'map'}
        for record in chart.get('records') or []:
            add(record.get('value'), percent=share)
            add(record.get('samples'))
            allowed.update(_numbers(str(record.get('shown') or '')))
            for key, value in (record.get('extra') or {}).items():
                if key == 'bucket_shares':
                    for item in value or []:
                        add(item, percent=True)
                elif isinstance(value, (int, float)):
                    add(value)
    return allowed


def validate_comments(texts: list[str], brief: dict[str, Any]) -> tuple[list[str], list[str]]:
    """The comments of an LLM that keep to the facts: every figure among the facts, no hidden item named, within the
    length and number a slide allows. Returns them and the problems of those left out."""
    allowed = allowed_numbers(brief)
    names = sorted({str(name) for chart in brief.get('charts') or [] for name in (chart.get('title'), chart.get('kpi'), chart.get('metric'))
                    if name} | {str(name) for chart in brief.get('charts') or [] for record in chart.get('records') or []
                                for name in (record.get('labels') or {}).values()}, key=len, reverse=True)
    hidden = [str(item) for item in brief.get('hidden') or [] if len(str(item)) > 1]
    kept, problems = [], []
    for text in texts[:int(brief.get('limit') or 4)]:
        if len(text) > MAX_COMMENT_LENGTH:
            problems.append(f'Too long: {text[:60]}…')
            continue
        named = next((item for item in hidden if re.search(rf'(?<!\w){re.escape(item)}(?!\w)', text)), None)
        if named:
            problems.append(f'Names the hidden {named}: {text[:60]}…')
            continue
        stripped = CAMPAIGN.sub(' ', text)
        stripped = re.sub(r'\bP\d{2}\b', ' ', stripped)
        for name in names:
            stripped = stripped.replace(name, ' ')
        unknown = [value for value in _numbers(stripped) if value not in allowed]
        if unknown:
            problems.append(f'Figures not in the facts ({", ".join(f"{value:g}" for value in unknown[:3])}): {text[:60]}…')
            continue
        kept.append(text)
    return kept, problems


def write_comments(engine: str, brief: dict[str, Any], *, repository: Any, config_dir: Path, username: str) -> dict[str, Any]:
    """The comments an LLM writer gives for one slide, checked against its facts; the rules comments when the writer
    fails or none of its comments keeps to the facts."""
    started = time.monotonic()
    rules = list(brief.get('rules_comments') or [])
    result: dict[str, Any] = {'engine': engine, 'model': '', 'texts': rules, 'warning': '', 'problems': []}
    if engine not in SERVER_ENGINES or not rules:
        result['engine'] = ENGINE_RULES
        return result
    settings = load_settings(repository)
    try:
        api_key, source = writer_key(settings, config_dir, engine, username)
        if engine == ENGINE_KIRO_CLI:
            texts, details = write_with_kiro_cli(brief, settings, kiro_cli_path(repository), api_key, config_dir, source)
        else:
            texts, details = write_with_claude(brief, settings, api_key, source)
    except WriterError as exc:
        reason = str(exc) if str(exc).startswith(ENGINE_LABELS[engine]) else f'{ENGINE_LABELS[engine]}: {exc}'
        result.update({'engine': ENGINE_RULES, 'warning': f'{reason} The rules comments are shown.'})
        result['duration_ms'] = round((time.monotonic() - started) * 1000)
        return result
    kept, problems = validate_comments(texts, brief)
    result.update(details)
    result['problems'] = problems
    if not kept:
        result.update({'engine': ENGINE_RULES, 'texts': rules,
                       'warning': f'{ENGINE_LABELS[engine]} wrote figures that are not in the charts: the rules comments are shown.'})
    else:
        result['texts'] = kept
        if problems:
            result['warning'] = f'{len(problems)} comment(s) of {ENGINE_LABELS[engine]} left out: their figures are not in the charts.'
    result['duration_ms'] = round((time.monotonic() - started) * 1000)
    return result


# -- Super Admin and account ----------------------------------------------------------------------------------------------

def writer_settings_panel(core: Any) -> dict[str, Any]:
    """What the AI Comment Writers panel of Super Admin shows (never a key: only whether one is saved)."""
    settings = load_settings(core.repository)
    return {
        'settings': settings, 'labels': ENGINE_LABELS, 'claude_models': CLAUDE_MODELS, 'claude_efforts': CLAUDE_EFFORTS,
        'server_keys': {engine: bool(server_key(core.application_config_dir, engine)) for engine in SERVER_ENGINES},
        'claude_environment_key': bool(os.environ.get('ANTHROPIC_API_KEY')),
        'kiro_cli': kiro_cli_status(core.repository, core.application_config_dir),
        'kiro_cli_installed': settings.get('kiro_cli') or {},
        'kiro_cli_download_url': KIRO_CLI_DOWNLOAD_URL, 'kiro_cli_release_notes_url': KIRO_CLI_RELEASE_NOTES_URL,
    }


def install_comment_writer_routes(core: Any) -> None:
    # The FastAPI names are imported with the module: its annotations are strings (``from __future__ import annotations``)
    # that FastAPI resolves from the module globals, so a local import leaves UploadFile undefined.
    app = core.app

    @app.post('/super-admin/comment-writers')
    def save_comment_writers(
        enabled: list[str] = Form([]), default: str = Form(ENGINE_KIRO_CLI), claude_model: str = Form(CLAUDE_MODELS[0][0]),
        claude_effort: str = Form('medium'), kiro_model: str = Form(''), timeout_seconds: str = Form('120'),
        kiro_key_source: str = Form('user'), claude_key_source: str = Form('server'),
        kiro_api_key: str = Form(''), claude_api_key: str = Form(''), user=Depends(core.super_admin_user),
    ):
        before = load_settings(core.repository)
        try:
            saved = save_settings(core.repository, {
                'enabled': enabled, 'default': default, 'claude_model': claude_model, 'claude_effort': claude_effort,
                'kiro_model': kiro_model, 'timeout_seconds': timeout_seconds,
                'kiro_key_source': kiro_key_source, 'claude_key_source': claude_key_source,
            })
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        changes = {}
        for engine, key in ((ENGINE_KIRO_CLI, kiro_api_key), (ENGINE_CLAUDE, claude_api_key)):
            if key.strip():
                set_server_key(core.application_config_dir, engine, key)
                changes[f'{KEY_NAMES[engine]}_server_key'] = 'replaced'
            else:
                changes[f'{KEY_NAMES[engine]}_server_key'] = 'unchanged'
        visible = ('enabled', 'default', 'kiro_key_source', 'claude_key_source', 'claude_model', 'claude_effort', 'kiro_model',
                   'timeout_seconds')
        core.repository.try_add_log(user.username, 'save_comment_writers', json.dumps({
            **{key: saved[key] for key in visible},
            'changed': [key for key in visible if before.get(key) != saved.get(key)], **changes,
        }, ensure_ascii=False))
        return RedirectResponse('/super-admin#comment-writers', status_code=303)

    @app.post('/super-admin/comment-writers/server-key/{engine}/remove')
    def remove_comment_writer_server_key(engine: str, user=Depends(core.super_admin_user)):
        """Remove the key of the server of a writer (Remove key, beside the field of the key)."""
        if engine not in SERVER_ENGINES:
            raise HTTPException(status_code=404, detail='Unknown comment writer.')
        had_key = bool(server_key(core.application_config_dir, engine))
        set_server_key(core.application_config_dir, engine, '')
        core.repository.try_add_log(user.username, 'remove_comment_writer_server_key', json.dumps({
            'writer': ENGINE_LABELS[engine], 'removed': had_key,
        }, ensure_ascii=False))
        return RedirectResponse('/super-admin#comment-writers', status_code=303)

    @app.post('/super-admin/comment-writers/kiro-cli')
    async def install_kiro_cli_package(package: UploadFile = File(...), user=Depends(core.super_admin_user)):
        content = await package.read()
        try:
            installed = install_kiro_cli(core.application_config_dir, package.filename or 'kiro-cli', content)
        except (ValueError, OSError, tarfile.TarError, zipfile.BadZipFile) as exc:
            core.repository.try_add_log(user.username, 'install_kiro_cli_failed', json.dumps({
                'file': package.filename, 'size': len(content), 'error': str(exc),
            }, ensure_ascii=False))
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        save_kiro_cli(core.repository, installed, user.username)
        core.repository.try_add_log(user.username, 'install_kiro_cli', json.dumps({
            'file': package.filename, 'size': len(content), 'version': installed['version'],
            'architecture': installed['architecture'], 'path': installed['path'],
        }, ensure_ascii=False))
        return JSONResponse({'installed': installed})

    @app.get('/account/api-keys')
    def account_api_keys(user=Depends(core.current_user)):
        """The writers whose key each user saves (as Super Admin chooses), and whether this user has saved it."""
        return JSONResponse({'providers': [
            {'id': engine, 'label': ENGINE_LABELS[engine], 'saved': bool(user_key(core.application_config_dir, engine, user.username))}
            for engine in user_key_engines(core.repository)
        ]})

    @app.post('/account/api-keys')
    def save_account_api_keys(kiro_cli: str = Form(''), claude: str = Form(''), remove: list[str] = Form([]),
                              user=Depends(core.current_user)):
        """Save or remove the personal API keys of the user: one field per writer (its id), ``remove`` the ids to remove."""
        submitted = {ENGINE_KIRO_CLI: kiro_cli, ENGINE_CLAUDE: claude}
        saved, dropped = [], []
        for engine in user_key_engines(core.repository):
            if engine in set(remove):
                set_user_key(core.application_config_dir, engine, user.username, '')
                dropped.append(engine)
            elif submitted[engine].strip():
                set_user_key(core.application_config_dir, engine, user.username, submitted[engine])
                saved.append(engine)
        if not saved and not dropped:
            raise HTTPException(status_code=400, detail='Paste an API key, or choose one to remove.')
        core.repository.try_add_log(user.username, 'save_user_api_keys', json.dumps({
            'saved': [ENGINE_LABELS[engine] for engine in saved], 'removed': [ENGINE_LABELS[engine] for engine in dropped],
        }))
        return JSONResponse({'saved': saved, 'removed': dropped})


# -- Kiro Brief -------------------------------------------------------------------------------------------------------

KIRO_BRIEF_GUIDE = STYLE_GUIDE.replace(
    'You receive the facts read from the charts of the slide', 'For each slide of facts.json you receive the facts read from its charts',
).replace(
    'Reply with JSON only: {"comments": ["…", "…"]}.',
    'Write the comments into comments.json: "slides" maps the comment_key of each slide of facts.json to its list of\n'
    'comments, at most the "limit" of that slide. Keep every other field of comments.json as it is.',
)
KIRO_BRIEF_README = '''# Kiro Brief of {name}

The facts of the charts of every slide of this PPT Designer, prepared by DriveTest Analyzer on {date}, for Kiro IDE
to write their comments.

1. Unzip this folder and open it in Kiro IDE (File → Open Folder). Kiro reads the style guide in
   `.kiro/steering/drivetest-comments.md` by itself.
2. Ask Kiro: "Write the comments of every slide of facts.json into comments.json, following brief.md."
3. Check comments.json, then in the PPT Designer choose Import Kiro comments and select comments.json and facts.json
   (or this folder zipped again). Every figure of the comments is checked against facts.json: a comment with a figure
   that is not in the facts is left out.

Never share this folder outside your organisation: it holds the figures of your drive tests.
'''


def kiro_brief_archive(brief: dict[str, Any]) -> bytes:
    """The Kiro Brief of a Design: the facts of every slide, the style guide (also as a Kiro steering file), the
    comments.json Kiro fills in and a README."""
    facts = {
        'format': 'drivetest-analyzer-comment-brief', 'version': 1,
        'design': {'id': brief['design_id'], 'name': brief['name']}, 'generated_at': brief['generated_at'],
        'selection': brief.get('selection', ''), 'slides': brief['slides'],
    }
    comments = {
        'format': 'drivetest-analyzer-comments', 'version': 1, 'design': brief['design_id'],
        'slides': {slide['comment_key']: [] for slide in brief['slides']},
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('README.md', KIRO_BRIEF_README.format(name=brief['name'], date=brief['generated_at'][:10]))
        archive.writestr('brief.md', f'# How to write the comments\n\n{KIRO_BRIEF_GUIDE}\n')
        archive.writestr('.kiro/steering/drivetest-comments.md', f'---\ninclusion: always\n---\n\n{KIRO_BRIEF_GUIDE}\n')
        archive.writestr('facts.json', json.dumps(facts, ensure_ascii=False, indent=2))
        archive.writestr('comments.json', json.dumps(comments, ensure_ascii=False, indent=2))
    return buffer.getvalue()


def read_kiro_import(uploads: list[tuple[str, bytes]]) -> tuple[dict[str, Any], dict[str, Any]]:
    """comments.json and facts.json from the files chosen to import (the two files, or the brief folder zipped)."""
    files: dict[str, bytes] = {}
    for name, content in uploads:
        if name.casefold().endswith('.zip'):
            try:
                with zipfile.ZipFile(io.BytesIO(content)) as archive:
                    for member in archive.namelist():
                        base = member.rsplit('/', 1)[-1].casefold()
                        if base in {'comments.json', 'facts.json'}:
                            files[base] = archive.read(member)
            except zipfile.BadZipFile as exc:
                raise ValueError('The zipped folder could not be read.') from exc
        else:
            files[name.rsplit('/', 1)[-1].casefold()] = content
    documents = {}
    for base in ('comments.json', 'facts.json'):
        if base not in files:
            raise ValueError(f'Choose comments.json and facts.json of the Kiro Brief ({base} is missing).')
        try:
            documents[base] = json.loads(files[base].decode('utf-8'))
        except (UnicodeDecodeError, ValueError) as exc:
            raise ValueError(f'{base} is not valid JSON.') from exc
    if documents['facts.json'].get('format') != 'drivetest-analyzer-comment-brief':
        raise ValueError('facts.json is not the facts of a Kiro Brief.')
    return documents['comments.json'], documents['facts.json']


def check_kiro_comments(comments: dict[str, Any], facts: dict[str, Any]) -> tuple[dict[str, list[str]], list[str]]:
    """The comments of every slide that keep to its facts, and the problems of those left out."""
    slides = comments.get('slides') if isinstance(comments, dict) else None
    if not isinstance(slides, dict):
        raise ValueError('comments.json has no "slides".')
    written, problems = {}, []
    for slide in facts.get('slides') or []:
        key = str(slide.get('comment_key'))
        texts = [re.sub(r'\s+', ' ', str(item)).strip() for item in slides.get(key) or [] if str(item).strip()]
        kept, left_out = validate_comments(texts, slide)
        written[key] = kept
        problems.extend(f"Slide {slide.get('number')}: {problem}" for problem in left_out)
    return written, problems
