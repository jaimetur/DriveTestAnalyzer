"""The cache folder of a workspace: ``.cache`` beside its database, with one folder per module for what it works out
to use again (``scoring``, ``network-insights``, ``ppt-designer`` and ``bundle-reports``).

What it holds is worked out again when it is missing: it is left out of backups, exports and transfers, moved with its
workspace when it is renamed and deleted with it. The cache folders of earlier versions (``.scoring-cache``,
``.network-insights-cache`` and ``.ppt-designer-cache`` beside the database, and
``output/reports/bundle-reports/cache``) move to it when the workspace opens.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

CACHE_FOLDER = '.cache'
SCORING = 'scoring'
NETWORK_INSIGHTS = 'network-insights'
PPT_DESIGNER = 'ppt-designer'
BUNDLE_REPORTS = 'bundle-reports'
# The cache folders of earlier versions, relative to the workspace folder, and the module folder that replaces each one.
LEGACY_FOLDERS = (
    ('.scoring-cache', SCORING),
    ('.network-insights-cache', NETWORK_INSIGHTS),
    ('.ppt-designer-cache', PPT_DESIGNER),
    ('output/reports/bundle-reports/cache', BUNDLE_REPORTS),
)
# A cache folder set aside to be deleted in the background is named after its module with this suffix and an id.
REMOVING_SUFFIX = '.removing-'


def cache_root(workspace_folder: str | Path) -> Path:
    """The cache folder of a workspace, given the workspace folder."""
    return Path(workspace_folder) / CACHE_FOLDER


def module_folder(workspace_folder: str | Path, module: str) -> Path:
    """The cache folder of a module in a workspace, given the workspace folder."""
    return cache_root(workspace_folder) / module


def of_database(database_path: Any, module: str) -> Path:
    """The cache folder of a module in a workspace, given the workspace database."""
    return module_folder(Path(str(database_path)).resolve().parent, module)


def move_legacy_folders(workspace_folder: str | Path) -> list[str]:
    """Move the cache folders of earlier versions (and those set aside to be deleted) to the cache folder of the
    workspace; one whose module already has its folder there, or that cannot be moved, is deleted. Returns the folders
    of earlier versions found, relative to the workspace folder."""
    workspace_folder = Path(workspace_folder)
    root = cache_root(workspace_folder)
    found = []
    for legacy, module in LEGACY_FOLDERS:
        source = workspace_folder / legacy
        moves = [(source, root / module)] if source.is_dir() else []
        try:
            moves += [(trash, root / f'{module}{trash.name[len(source.name):]}')
                      for trash in sorted(source.parent.glob(f'{source.name}{REMOVING_SUFFIX}*')) if trash.is_dir()]
        except OSError:
            pass
        for folder, target in moves:
            try:
                if target.exists():
                    raise FileExistsError(target)
                root.mkdir(parents=True, exist_ok=True)
                os.replace(folder, target)
            except OSError:
                shutil.rmtree(folder, ignore_errors=True)
            found.append(folder.relative_to(workspace_folder).as_posix())
    return found
