"""Cell Configuration packages: Google Earth KMZ/KML files whose Placemarks describe the cells of a network.

Each cell Placemark carries its attributes in its description as ``Key: Value`` lines (Network, Host
Network, Vendor, Site ID, eNodeB/gNodeB ID, Cell ID, ECI/NCI, Band, PCI, coordinates, azimuth…). The reader
accepts one ``.kml`` or ``.kmz`` file, or a ``.zip`` package of them (also in folders or nested ``.zip``
files), and returns one row per cell. Placemarks without a cell identity, such as the site-vendor points of
the same packages, are skipped: their sites are already described by their cells.
"""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path
from typing import Callable, IO, Iterator
import xml.etree.ElementTree as ET

import pandas as pd

from src.modules.column_names import column_identity

KML_NAMESPACE = '{http://www.opengis.net/kml/2.2}'
CELL_CONFIGURATION_SUFFIXES = frozenset({'.kml', '.kmz'})
# Description keys that identify a cell rather than a site.
CELL_IDENTITY_KEYS = frozenset({
    'eci', 'nci', 'gcid', 'cgi', 'ecgi', 'ncgi', 'cellidentity', 'cellname', 'cellid', 'localcellid',
})
TECHNOLOGY_COLUMN = 'Technology'
SOURCE_FILE_COLUMN = 'Source_File'
FOLDER_COLUMN = 'Folder'
_TAGS = re.compile(r'<[^>]+>')
_BREAKS = re.compile(r'<br\s*/?>', re.I)
_NR_NAME = re.compile(r'(?<![a-z0-9])(nr|5g)(?![a-z0-9])', re.I)
_LTE_NAME = re.compile(r'(?<![a-z0-9])(lte|4g)(?![a-z0-9])', re.I)


def is_cell_configuration_package(path: Path) -> bool:
    """Whether a ``.kml``/``.kmz`` file, or a ``.zip`` holding one, is a Cell Configuration package."""
    suffix = path.suffix.lower()
    if suffix in CELL_CONFIGURATION_SUFFIXES:
        return True
    if suffix != '.zip' or not zipfile.is_zipfile(path):
        return False
    with zipfile.ZipFile(path) as archive:
        return any(Path(name).suffix.lower() in {*CELL_CONFIGURATION_SUFFIXES, '.zip'} for name in archive.namelist()
                   if not name.endswith('/'))


def _kml_documents(
    name: str, opener: Callable[[], IO[bytes]], depth: int = 0, label: str | None = None,
) -> Iterator[tuple[str, Callable[[], IO[bytes]]]]:
    """Every KML document of a file: itself, the ``.kml`` of a ``.kmz`` or those of a ``.zip`` package.

    ``name`` gives the file type; each document is labelled with ``label`` (its own name by default).
    """
    label = label or name
    suffix = Path(name).suffix.lower()
    if suffix == '.kml':
        yield label, opener
        return
    if suffix not in {'.kmz', '.zip'} or depth > 3:
        return
    if depth == 0 and Path(name).is_file():
        archive = zipfile.ZipFile(name)
    else:
        # A package inside a package is read into memory: ZIP members cannot be seeked in place.
        with opener() as stream:
            archive = zipfile.ZipFile(io.BytesIO(stream.read()))
    for member in sorted(archive.infolist(), key=lambda item: item.filename):
        member_name = member.filename
        if member_name.endswith('/') or Path(member_name).name.startswith(('.', '__MACOSX')) or '__MACOSX/' in member_name:
            continue
        member_suffix = Path(member_name).suffix.lower()
        if member_suffix not in {'.kml', '.kmz', '.zip'}:
            continue
        # A KMZ document is named after its package (doc.kml inside Outcome1_LTE_….kmz).
        member_label = label if suffix == '.kmz' and member_suffix == '.kml' else member_name
        yield from _kml_documents(member_name, lambda member=member: archive.open(member), depth + 1, member_label)


def _description_values(text: str | None) -> dict[str, str]:
    if not text:
        return {}
    values: dict[str, str] = {}
    for line in _TAGS.sub('', _BREAKS.sub('\n', text)).splitlines():
        key, separator, value = line.partition(':')
        key = key.strip()
        if separator and key:
            values[key] = value.strip()
    return values


def _technology(document: str, folders: list[str], values: dict[str, str]) -> str:
    """LTE or NR from the cell's keys, else from its document or folder names."""
    identities = {column_identity(key) for key, value in values.items() if value}
    if identities & {'gnodebid', 'gnodeb', 'nci', 'arfcn', 'nrpci', 'ssbfrequency'}:
        return 'NR'
    if identities & {'enodebid', 'enodeb', 'eci', 'earfcn'}:
        return 'LTE'
    for text in (*reversed(folders), Path(document).stem):
        if _NR_NAME.search(text.replace('_', ' ')):
            return 'NR'
        if _LTE_NAME.search(text.replace('_', ' ')):
            return 'LTE'
    band = values.get('Band', '')
    return 'NR' if band.upper().startswith('NR') else 'LTE' if band.upper().startswith('LTE') else ''


def read_cell_configuration(path: Path, progress_callback: Callable[[int], None] | None = None) -> pd.DataFrame:
    """One row per cell Placemark of a KML/KMZ file or of a ZIP package of them.

    Keys spelled differently in LTE and NR documents (``Cell_name`` and ``Cell Name``, ``Site_ID`` and
    ``Site ID``) share one column, named after the first spelling read.
    """
    documents = list(_kml_documents(str(path), lambda: path.open('rb')))
    if not documents:
        raise ValueError('The package contains no KML or KMZ file.')
    names: dict[str, str] = {TECHNOLOGY_COLUMN.casefold(): TECHNOLOGY_COLUMN,
                             column_identity(SOURCE_FILE_COLUMN): SOURCE_FILE_COLUMN,
                             column_identity(FOLDER_COLUMN): FOLDER_COLUMN}
    columns: dict[str, list[str | None]] = {TECHNOLOGY_COLUMN: [], SOURCE_FILE_COLUMN: [], FOLDER_COLUMN: []}
    shared: dict[str, str] = {}
    rows = 0
    for position, (document, opener) in enumerate(documents, start=1):
        source = Path(document).name
        with opener() as stream:
            stack: list[str] = []
            folders: list[str | None] = []
            for event, element in ET.iterparse(stream, events=('start', 'end')):
                tag = element.tag.replace(KML_NAMESPACE, '')
                if event == 'start':
                    stack.append(tag)
                    if tag == 'Folder':
                        folders.append(None)
                    continue
                stack.pop()
                parent = stack[-1] if stack else ''
                if tag == 'name' and parent == 'Folder' and folders and folders[-1] is None:
                    folders[-1] = (element.text or '').strip()
                elif tag == 'Folder':
                    folders.pop()
                    element.clear()
                elif tag == 'Placemark':
                    description = element.find(f'{KML_NAMESPACE}description')
                    values = _description_values(description.text if description is not None else '')
                    element.clear()
                    if not ({column_identity(key) for key, value in values.items() if value} & CELL_IDENTITY_KEYS):
                        continue
                    path_names = [name or '' for name in folders]
                    row = {TECHNOLOGY_COLUMN: _technology(source, path_names, values), SOURCE_FILE_COLUMN: source,
                           FOLDER_COLUMN: ' / '.join(name for name in path_names if name)}
                    for key, value in values.items():
                        identity = column_identity(key) or key.casefold()
                        column = names.setdefault(identity, key)
                        if column not in columns:
                            columns[column] = [None] * rows
                        row[column] = value or None
                    for column, values_list in columns.items():
                        value = row.get(column)
                        # Repeated labels (Network, Vendor, Band…) share one string object.
                        values_list.append(shared.setdefault(value, value) if value is not None else None)
                    rows += 1
        if progress_callback:
            progress_callback(min(50, 5 + int(45 * position / len(documents))))
    if not rows:
        raise ValueError('The package has no cell Placemark: each cell needs a Cell Name, Cell ID, ECI or NCI in its description.')
    return pd.DataFrame(columns)
