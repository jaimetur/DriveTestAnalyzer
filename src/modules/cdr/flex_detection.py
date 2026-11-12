"""Final CDRs that look local: the suggestion to make their campaign a Flex campaign.

A Flex campaign is a local campaign (one city, several cities of one zone, a region): its Campaign values, or their
label in Campaign Maps, have the word Flex (see ``cdr_auto_selection.is_flex_campaign``). Ad-hoc campaigns do not always
say so, so a Final CDR that is not Flex yet is suggested as one when

* its file name has the name of an area of the workspace (a City, Cluster or Region value of the CDRs, such as London),
  unless its tests cover most of the area of the other Final CDRs; or
* its tests cover a small part of the area of the other Final CDRs of its type and NR Mode that are not Flex
  (``LOCAL_COVERAGE_SHARE`` of the cells of ``CELL_DEGREES`` they test in), whatever its name.

Weekly and Daily CDRs are never suggested: they hold the calls measured so far, not the whole country yet, so their
stage decides. A suggestion is accepted with **Mark as Flex** (a Campaign Maps exception that labels the Campaign values
of the CDR with Flex: ``mark_as_flex``) or dismissed with **Not local**; the Campaign values and Campaign Maps labels
written by hand keep working as before.

What each CDR covers (its cells and its most frequent areas) is read once per revision of the CDR and kept in the
workspace state.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from src.modules.cdr.cdr_stage import DEFAULT_CDR_STAGE, _revision, combined_inclusion, infer_cdr_stage
from src.modules.cdr.column_names import campaign_market, campaign_quarter_and_name

FACTS_STATE_KEY = 'cdr_local_facts'
DISMISSED_STATE_KEY = 'cdr_flex_suggestions_dismissed'
FACTS_VERSION = 1
CDR_KINDS = frozenset({'data', 'voice', 'speech'})
# The grid of the area covered: cells of a quarter of a degree (about 28 km by 17 km in the UK).
CELL_DEGREES = 0.25
# A CDR whose tests are in at most this share of the cells of the other Final CDRs looks local...
LOCAL_COVERAGE_SHARE = 0.35
# ...and one in at least this share covers the country, whatever its name says.
NATIONAL_COVERAGE_SHARE = 0.6
# The other Final CDRs need this many cells for a comparison.
MIN_REFERENCE_CELLS = 12
# An area that holds this share of the located tests of a CDR names it.
DOMINANT_AREA_SHARE = 0.6
AREA_FIELDS = ('City', 'Cluster', 'Region')
_TOP_AREAS = 40
_GENERIC_AREAS = frozenset({'unknown', 'other', 'others', 'none', 'null', 'nan', 'n/a', 'na', 'all', 'total', 'national',
                            'nationwide', 'country', 'city', 'cities', 'road', 'roads', 'connecting roads', 'rural', 'urban'})


def _words(text: object) -> str:
    """Lower-case words separated by single spaces (``SouthWest_Bristol`` → ``south west bristol``)."""
    spaced = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', str(text or ''))
    return ' '.join(re.sub(r'[^a-z0-9]+', ' ', spaced.casefold()).split())


def _row(dataset: Any, key: str, default: Any = None) -> Any:
    try:
        value = dataset[key]
    except (KeyError, IndexError):
        return default
    return default if value is None else value


def _resolve(columns: Iterable[str], candidates: Iterable[str]) -> str | None:
    by_identity = {_words(column).replace(' ', ''): column for column in columns}
    return next((by_identity[key] for candidate in candidates if (key := _words(candidate).replace(' ', '')) in by_identity), None)


def _read_columns(repository: Any, dataset: Any, columns: list[str]) -> pd.DataFrame:
    """Some columns of a CDR: from its columnar copy, else from its table."""
    dataset_id, kind = int(dataset['id']), str(dataset['dataset_kind']).casefold()
    try:
        from src.modules.cdr import cdr_store

        frame = cdr_store.query_cdr(repository.db_path, kind, dataset_id, [(column, column) for column in columns])
        if frame is not None:
            return frame
    except Exception:  # noqa: BLE001 - the table is read instead.
        pass
    quoted = ', '.join(repository._quote_identifier(column) for column in columns)
    with repository.connection() as connection:
        return pd.read_sql_query(f'SELECT {quoted} FROM {repository._quote_identifier(f"dataset_rows_{dataset_id}")}', connection)


def _cdr_facts(repository: Any, dataset: Any, profile: Any) -> dict[str, Any]:
    """The cells a CDR tests in and its most frequent areas."""
    kind = str(dataset['dataset_kind']).casefold()
    columns = repository.list_dataset_row_columns(int(dataset['id']))
    pairs = [(_resolve(columns, [lat]), _resolve(columns, [lon])) for lat, lon in (profile.coordinate_sources.get(kind) or ())]
    pairs = [(lat, lon) for lat, lon in pairs if lat and lon]
    areas = {field: _resolve(columns, profile.area_fields.get(field) or (field,)) for field in AREA_FIELDS}
    wanted = list(dict.fromkeys([*(column for pair in pairs for column in pair), *(column for column in areas.values() if column)]))
    facts: dict[str, Any] = {'version': FACTS_VERSION, 'revision': _revision(dataset), 'cells': [], 'located': 0, 'areas': {}}
    if not wanted:
        return facts
    frame = _read_columns(repository, dataset, wanted)
    cells: set[tuple[int, int]] = set()
    located = pd.Series(False, index=frame.index)
    for lat_column, lon_column in pairs:
        lat = pd.to_numeric(frame[lat_column], errors='coerce')
        lon = pd.to_numeric(frame[lon_column], errors='coerce')
        valid = lat.between(-90, 90) & lon.between(-180, 180) & ~((lat == 0) & (lon == 0))
        located |= valid
        grid = pd.DataFrame({'lat': (lat[valid] / CELL_DEGREES).apply(math.floor),
                             'lon': (lon[valid] / CELL_DEGREES).apply(math.floor)}).drop_duplicates()
        cells.update(zip(grid['lat'].astype(int), grid['lon'].astype(int)))
    facts['cells'] = sorted([int(lat), int(lon)] for lat, lon in cells)
    facts['located'] = int(located.sum())
    for field, column in areas.items():
        if not column:
            continue
        values = frame[column].dropna().astype(str).str.strip()
        values = values[values.ne('')]
        counts = values.value_counts()
        facts['areas'][field] = {'rows': int(len(values)), 'top': {str(name): int(count) for name, count in counts.head(_TOP_AREAS).items()}}
    return facts


def local_facts(repository: Any, datasets: list[Any], read_missing: bool = True) -> dict[int, dict[str, Any]]:
    """What each ready CDR covers, read once per revision (only those already read with ``read_missing`` False)."""
    try:
        cached = json.loads(repository.get_workspace_state(FACTS_STATE_KEY) or '{}')
    except (TypeError, ValueError):
        cached = {}
    cached = cached if isinstance(cached, dict) else {}
    profile = None
    facts: dict[int, dict[str, Any]] = {}
    changed = False
    for dataset in datasets:
        dataset_id = int(dataset['id'])
        entry = cached.get(str(dataset_id))
        if isinstance(entry, dict) and entry.get('revision') == _revision(dataset) and entry.get('version') == FACTS_VERSION:
            facts[dataset_id] = entry
            continue
        if not read_missing:
            continue
        if profile is None:
            from src.modules.cdr.cdr_field_profiles import workspace_field_profile

            profile = workspace_field_profile(repository)
        try:
            entry = _cdr_facts(repository, dataset, profile)
        except Exception:  # noqa: BLE001 - a CDR that cannot be read is not suggested.
            entry = {'version': FACTS_VERSION, 'revision': _revision(dataset), 'cells': [], 'located': 0, 'areas': {}}
        facts[dataset_id] = cached[str(dataset_id)] = entry
        changed = True
    known = {str(int(dataset['id'])) for dataset in repository.list_datasets()}
    if changed or set(cached) - known:
        repository.set_workspace_state(FACTS_STATE_KEY, json.dumps({key: value for key, value in cached.items() if key in known}))
    return facts


def dismissed(repository: Any) -> dict[str, str]:
    """The CDRs whose suggestion was dismissed, with the revision they had."""
    try:
        values = json.loads(repository.get_workspace_state(DISMISSED_STATE_KEY) or '{}')
    except (TypeError, ValueError):
        return {}
    return values if isinstance(values, dict) else {}


def dismiss(repository: Any, dataset: Any) -> None:
    values = dismissed(repository)
    values[str(int(dataset['id']))] = _revision(dataset)
    repository.set_workspace_state(DISMISSED_STATE_KEY, json.dumps(values))


def _known_areas(facts: dict[int, dict[str, Any]]) -> dict[str, str]:
    """The area names of the workspace CDRs, by their words (``south west`` → ``South West``)."""
    names: dict[str, str] = {}
    for entry in facts.values():
        for field in AREA_FIELDS:
            for name in ((entry.get('areas') or {}).get(field) or {}).get('top') or {}:
                words = _words(name)
                if len(words.replace(' ', '')) >= 3 and words not in _GENERIC_AREAS and not campaign_market(name) == name.strip():
                    names.setdefault(words, str(name).strip())
    return names


def _name_area(file_name: str, areas: dict[str, str]) -> str:
    """The longest area name of the workspace in a file name, as a whole word."""
    words = f" {_words(Path(file_name).stem)} "
    found = [name for key, name in areas.items() if f' {key} ' in words]
    return max(found, key=len) if found else ''


def _dominant_area(entry: dict[str, Any]) -> str:
    for field in ('City', 'Cluster'):
        area = (entry.get('areas') or {}).get(field) or {}
        top = area.get('top') or {}
        if top and area.get('rows'):
            name, count = max(top.items(), key=lambda item: item[1])
            if count / area['rows'] >= DOMINANT_AREA_SHARE and _words(name) not in _GENERIC_AREAS:
                return str(name)
    return ''


def flex_label(campaigns: Iterable[object], area: str) -> str:
    """The Campaign Maps label of a local campaign: ``26-Q4-London-Flex`` (its year, quarter, area and Flex)."""
    area_part = re.sub(r'[^A-Za-z0-9]+', '-', str(area or '').strip()).strip('-') or 'Local'
    for value in campaigns:
        parts = campaign_quarter_and_name(value)
        if parts:
            year, quarter, name = parts
            name_part = re.sub(r'[^A-Za-z0-9]+', '-', name).strip('-')
            middle = '-'.join(part for part in (name_part, area_part) if part and part.casefold() != 'flex')
            return f'{year[-2:]}-{quarter}-{middle}-Flex'[:80]
    first = next((str(value).strip() for value in campaigns if str(value).strip()), '')
    return f'{first}-{area_part}-Flex'[:80] if first else f'{area_part}-Flex'


def final_cdrs_to_read(repository: Any) -> list[Any]:
    """The ready Final CDRs whose coverage has not been read in their revision yet."""
    try:
        cached = json.loads(repository.get_workspace_state(FACTS_STATE_KEY) or '{}')
    except (TypeError, ValueError):
        cached = {}
    cached = cached if isinstance(cached, dict) else {}
    inclusion = combined_inclusion(repository)
    return [dataset for dataset in repository.list_datasets()
            if str(_row(dataset, 'status', '')) == 'ready' and str(_row(dataset, 'dataset_kind', '')).casefold() in CDR_KINDS
            and ((inclusion.get(int(dataset['id'])) or {}).get('stage') or DEFAULT_CDR_STAGE) == 'final'
            and not (isinstance(entry := cached.get(str(int(dataset['id']))), dict) and entry.get('revision') == _revision(dataset)
                     and entry.get('version') == FACTS_VERSION)]


def flex_suggestions(repository: Any, read_missing: bool = True) -> dict[int, dict[str, Any]]:
    """The Final CDRs that look local, with why, the area, the label proposed and the other CDRs of their campaigns.

    With ``read_missing`` False nothing is suggested until every Final CDR has been read (a comparison with only some of
    them would find CDRs of the whole country local)."""
    from src.modules.cdr.cdr_auto_selection import cdr_campaigns, is_flex_cdr

    datasets = [dataset for dataset in repository.list_datasets()
                if str(_row(dataset, 'status', '')) == 'ready' and str(_row(dataset, 'dataset_kind', '')).casefold() in CDR_KINDS]
    if not datasets:
        return {}
    inclusion = combined_inclusion(repository)
    campaigns = cdr_campaigns(repository, [int(dataset['id']) for dataset in datasets])
    flex = {int(dataset['id']): is_flex_cdr(campaigns.get(int(dataset['id'])) or [], _row(dataset, 'campaign', ''))
            for dataset in datasets}
    stage = {int(dataset['id']): (inclusion.get(int(dataset['id'])) or {}).get('stage') or DEFAULT_CDR_STAGE for dataset in datasets}
    finals = [dataset for dataset in datasets if stage[int(dataset['id'])] == 'final']
    facts = local_facts(repository, finals, read_missing)
    if len(facts) < len(finals):
        return {}
    areas = _known_areas(facts)
    skipped = dismissed(repository)
    suggestions: dict[int, dict[str, Any]] = {}
    for dataset in finals:
        dataset_id = int(dataset['id'])
        if flex[dataset_id] or skipped.get(str(dataset_id)) == _revision(dataset):
            continue
        # A name that says Weekly or Daily is a CDR of the calls measured so far, never a local one.
        if infer_cdr_stage(dataset['file_name']) != 'final':
            continue
        kind, mode = str(dataset['dataset_kind']).casefold(), str(_row(dataset, 'nr_mode', '') or '').upper()
        reference: set[tuple[int, int]] = set()
        for other in finals:
            other_id = int(other['id'])
            if (other_id != dataset_id and not flex[other_id] and str(other['dataset_kind']).casefold() == kind
                    and (not mode or not str(_row(other, 'nr_mode', '') or '') or str(_row(other, 'nr_mode', '')).upper() == mode)):
                reference.update(tuple(cell) for cell in facts[other_id].get('cells') or [])
        cells = {tuple(cell) for cell in facts[dataset_id].get('cells') or []}
        share = len(cells & reference) / len(reference) if len(reference) >= MIN_REFERENCE_CELLS and cells else None
        named = _name_area(str(dataset['file_name']), areas)
        if share is not None and share <= LOCAL_COVERAGE_SHARE:
            reason = 'coverage'
        elif named and (share is None or share < NATIONAL_COVERAGE_SHARE):
            reason = 'name'
        else:
            continue
        values = campaigns.get(dataset_id) or []
        area = named or _dominant_area(facts[dataset_id])
        identities = {str(value).strip().casefold() for value in values}
        sharing = [str(other['file_name']) for other in datasets
                   if int(other['id']) != dataset_id and identities & {str(value).strip().casefold() for value in campaigns.get(int(other['id'])) or []}]
        suggestions[dataset_id] = {
            'reason': reason, 'area': area, 'coverage_share': None if share is None else round(share, 3),
            'campaigns': list(values), 'label': flex_label(values, area), 'shared_with': sharing,
        }
    return suggestions


def describe(suggestion: dict[str, Any]) -> str:
    """What the card of the CDR says about its suggestion."""
    area = f" ({suggestion['area']})" if suggestion.get('area') else ''
    if suggestion['reason'] == 'coverage':
        why = f"its tests cover {round(100 * (suggestion.get('coverage_share') or 0))}% of the area of the other Final CDRs"
    else:
        why = f"its file name has the area{area}"
        area = ''
    text = f'Looks local{area}: {why}.'
    if suggestion.get('shared_with'):
        count = len(suggestion['shared_with'])
        text += f" Its campaign is also in {count} other CDR{'' if count == 1 else 's'}, which would be Flex too."
    return text


def mark_as_flex(repository: Any, campaigns: Iterable[object], label: str, username: str = '') -> dict[str, Any]:
    """Label the Campaign values of a CDR with a Flex label in Campaign Maps (adding Flex to an exception they have)."""
    from src.modules.mapping.campaign_maps import load_campaign_map, save_campaign_map

    values = list(dict.fromkeys(str(value).strip() for value in campaigns if str(value).strip()))
    if not values:
        raise ValueError('This CDR has no Campaign values to label as Flex.')
    label = re.sub(r'\s+', ' ', str(label or '')).strip()[:80]
    if not re.search(r'(?<![a-z])flex(?![a-z])', label, re.IGNORECASE):
        raise ValueError('The label of a Flex campaign needs the word Flex, such as 26-Q4-London-Flex.')
    config = load_campaign_map(repository)
    exceptions = [dict(item, sources=list(item.get('sources') or [])) for item in config.get('exceptions') or []]
    keys = {value.casefold() for value in values}
    own = [item for item in exceptions if keys & {str(source).casefold() for source in item['sources']}]
    if own:
        # The values already have a label of their own: the first one takes the Flex label and every value.
        target = own[0]
        for item in own[1:]:
            item['sources'] = [source for source in item['sources'] if str(source).casefold() not in keys]
        target['sources'] = list(dict.fromkeys([*target['sources'], *values]))
        if label.casefold() != str(target['label']).casefold() and any(
                str(item['label']).casefold() == label.casefold() for item in exceptions if item is not target):
            raise ValueError(f'The campaign label "{label}" is already used by another exception.')
        target['label'] = label
        exceptions = [item for item in exceptions if item['sources']]
    else:
        same = next((item for item in exceptions if str(item['label']).casefold() == label.casefold()), None)
        if same is not None:
            same['sources'] = list(dict.fromkeys([*same['sources'], *values]))
        else:
            exceptions.append({'label': label, 'sources': values})
    return save_campaign_map(repository, {**config, 'exceptions': exceptions}, username)
