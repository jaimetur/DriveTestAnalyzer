"""Final CDRs that look local: the suggestion to make their campaign a Flex campaign.

A Flex campaign is a local campaign (one city, several cities of one zone, a region): its Campaign values, or their
label in Campaign Maps, have the word Flex (see ``cdr_auto_selection.is_flex_campaign``). Ad-hoc campaigns do not always
say so, so a CDR that is not Flex yet is suggested as one when

* its file name has the name of an area of the workspace (a City, Cluster or Region value of the CDRs, such as London),
  unless it is a Final CDR whose tests cover most of the area of the other Final CDRs; or
* it is a Final CDR whose tests cover a small part of the area of the other Final CDRs of its type and NR Mode that are
  not Flex (``LOCAL_COVERAGE_SHARE`` of the cells of ``CELL_DEGREES`` they test in), whatever its name.

Weekly and Daily CDRs hold the calls measured so far, not the whole area yet, so only their file name suggests them.
A suggestion is accepted with **Mark as Flex** or dismissed with **Not local**. Any CDR that is not Flex can be marked
too (``mark_cdr_as_flex``: a Campaign Maps exception that labels the Campaign values of the CDR with Flex, or, for a CDR
whose rows have no Campaign values, a Flex campaign of its own), and the upload review chooses it for each CDR before
it is processed (``set_import_choices``, applied once it is ready by ``apply_import_choices``). The Campaign values and
Campaign Maps labels written by hand keep working as before.

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

from src.modules.cdr.cdr_campaign import _DATE, infer_campaign, normalize_campaign
from src.modules.cdr.cdr_stage import DEFAULT_CDR_STAGE, _revision, combined_inclusion
from src.modules.cdr.column_names import (
    DEFAULT_CAMPAIGN_LABEL_MODES, campaign_market, campaign_parts, campaign_quarter_and_name, current_campaign_map,
)

FACTS_STATE_KEY = 'cdr_local_facts'
DISMISSED_STATE_KEY = 'cdr_flex_suggestions_dismissed'
# The Flex choice of the upload review for each CDR not processed yet: ``flex`` or ``not_flex``.
IMPORT_CHOICES_STATE_KEY = 'cdr_flex_import_choices'
IMPORT_CHOICES = frozenset({'flex', 'not_flex'})
# A suggestion dismissed with this revision stays hidden whatever the CDR becomes (Not Flex chosen in the upload review).
ALWAYS = '*'
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


def dismiss(repository: Any, dataset: Any, always: bool = False) -> None:
    values = dismissed(repository)
    values[str(int(dataset['id']))] = ALWAYS if always else _revision(dataset)
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


def _period_of_name(file_name: object) -> tuple[str, str] | None:
    """The year and quarter of a CDR from its file name: its quarter, else its first measurement date
    (``20261112 Daily Data CDR UK London 20261024-20261111`` is 2026 Q4)."""
    year, quarter, _mode = campaign_parts(infer_campaign(file_name))
    if year and quarter:
        return year, quarter
    stem = Path(str(file_name or '')).stem
    dates = [(match.start(), match.group(1), int(match.group(2))) for match in _DATE.finditer(stem)]
    measured = [(year, month) for start, year, month in dates if start > 0] or [(year, month) for _start, year, month in dates]
    return (measured[0][0], f'Q{(measured[0][1] - 1) // 3 + 1}') if measured else None


def flex_label(campaigns: Iterable[object], area: str, file_name: object = '', dataset_campaign: object = '',
               config: dict | None = None) -> str:
    """The Campaign Maps label of a local campaign: ``26-Q4-London-Flex`` (its year, quarter, area and Flex), with the
    NR Mode of its Campaign values when the Campaign Maps format shows it (``26-Q4-SA-London-Flex``).

    The year and quarter come from the Campaign values, else from the campaign of the CDR in Workspace, else from its
    file name (``UK_London_SA_2026`` in ``… UK London 20261024-20261111.xlsx`` is 2026 Q4)."""
    config = config or current_campaign_map()
    area_part = re.sub(r'[^A-Za-z0-9]+', '-', str(area or '').strip()).strip('-') or 'Local'
    values = [str(value).strip() for value in campaigns if str(value).strip()]
    period, name = None, ''
    for value in values:
        parts = campaign_quarter_and_name(value, config)
        if parts:
            period, name = parts[:2], parts[2]
            break
    if period is None:
        year, quarter, _mode = campaign_parts(dataset_campaign)
        period = (year, quarter) if year and quarter else _period_of_name(file_name)
    mode = next((found for value in values if (found := campaign_parts(value)[2])), None)
    if period:
        year, quarter = period
        shown = config.get('modes_in_label', DEFAULT_CAMPAIGN_LABEL_MODES)
        name_part = re.sub(r'[^A-Za-z0-9]+', '-', name).strip('-')
        middle = '-'.join(part for part in (mode if mode in shown else '', name_part, area_part) if part and part.casefold() != 'flex')
        return f'{year[-2:]}-{quarter}-{middle}-Flex'[:80]
    first = values[0] if values else ''
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
    """The CDRs that look local, with why, the area, the label proposed and the other CDRs of their campaigns.

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
    config = current_campaign_map()
    suggestions: dict[int, dict[str, Any]] = {}
    for dataset in datasets:
        dataset_id = int(dataset['id'])
        if flex[dataset_id] or skipped.get(str(dataset_id)) in {_revision(dataset), ALWAYS}:
            continue
        named = _name_area(str(dataset['file_name']), areas)
        if stage[dataset_id] != 'final':
            # A Weekly or Daily CDR holds the calls measured so far: only an area in its name says it is local.
            if named:
                suggestions[dataset_id] = _suggestion(repository, dataset, datasets, campaigns, 'name', named, None, config)
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
        if share is not None and share <= LOCAL_COVERAGE_SHARE:
            reason = 'coverage'
        elif named and (share is None or share < NATIONAL_COVERAGE_SHARE):
            reason = 'name'
        else:
            continue
        suggestions[dataset_id] = _suggestion(repository, dataset, datasets, campaigns, reason,
                                              named or _dominant_area(facts[dataset_id]), share, config)
    return suggestions


def _suggestion(repository: Any, dataset: Any, datasets: list[Any], campaigns: dict[int, list[str]], reason: str,
                area: str, share: float | None, config: dict) -> dict[str, Any]:
    dataset_id = int(dataset['id'])
    values = campaigns.get(dataset_id) or []
    identities = {str(value).strip().casefold() for value in values}
    sharing = [str(other['file_name']) for other in datasets
               if int(other['id']) != dataset_id and identities & {str(value).strip().casefold() for value in campaigns.get(int(other['id'])) or []}]
    return {
        'reason': reason, 'area': area, 'coverage_share': None if share is None else round(share, 3),
        'campaigns': list(values), 'shared_with': sharing,
        'label': flex_label(values, area, dataset['file_name'], _row(dataset, 'campaign', ''), config),
    }


def name_areas(repository: Any) -> list[str]:
    """The area names of the workspace (City, Cluster and Region values of its Final CDRs) that a file name can have."""
    try:
        cached = json.loads(repository.get_workspace_state(FACTS_STATE_KEY) or '{}')
    except (TypeError, ValueError):
        cached = {}
    entries = {int(key): value for key, value in (cached if isinstance(cached, dict) else {}).items()
               if isinstance(value, dict) and str(key).isdigit()}
    return sorted(set(_known_areas(entries).values()), key=str.casefold)


def proposed_label(repository: Any, dataset: Any) -> tuple[str, list[str]]:
    """The Flex label proposed for a CDR (its suggestion's, else one built from the area in its file name) and its
    Campaign values."""
    from src.modules.cdr.cdr_auto_selection import cdr_campaigns

    dataset_id = int(dataset['id'])
    suggestion = flex_suggestions(repository, read_missing=False).get(dataset_id) or {}
    campaigns = cdr_campaigns(repository, [dataset_id]).get(dataset_id) or []
    if suggestion.get('label'):
        return suggestion['label'], campaigns
    area = _name_area(str(dataset['file_name']), {_words(name): name for name in name_areas(repository)})
    return flex_label(campaigns, area, dataset['file_name'], _row(dataset, 'campaign', '')), campaigns


def mark_cdr_as_flex(repository: Any, dataset: Any, label: str, campaigns: list[str], username: str = '') -> dict[str, Any]:
    """Make a CDR Flex: its Campaign values take the Flex label in Campaign Maps (``mark_as_flex``); a CDR whose rows
    have no Campaign values takes the Flex campaign itself (``2026-Q4-London-Flex`` for ``26-Q4-London-Flex``)."""
    if campaigns:
        config = mark_as_flex(repository, campaigns, label, username)
        return {'label': label, 'campaign': '', 'exceptions': [item['label'] for item in config.get('exceptions') or []]}
    label = re.sub(r'\s+', ' ', str(label or '')).strip()
    if not re.search(r'(?<![a-z])flex(?![a-z])', label, re.IGNORECASE):
        raise ValueError('The label of a Flex campaign needs the word Flex, such as 26-Q4-London-Flex.')
    short = re.match(r'^(\d{2})(\s*[-_ ]\s*q\s*[1-4].*)$', label, re.IGNORECASE)
    try:
        campaign = normalize_campaign(f'20{short.group(1)}{short.group(2)}' if short else label)
    except ValueError as exc:
        raise ValueError('This CDR has no Campaign values: write its Flex campaign with its year and quarter, '
                         'such as 26-Q4-London-Flex.') from exc
    if not re.search(r'(?<![a-z])flex(?![a-z])', campaign, re.IGNORECASE):
        campaign = f'{campaign[:35]}-Flex'
    repository.update_dataset_profile(int(dataset['id']), campaign=campaign)
    return {'label': label, 'campaign': campaign, 'exceptions': []}


def import_choices(repository: Any) -> dict[str, str]:
    """The Flex choices of the upload review waiting for their CDR to be processed."""
    try:
        values = json.loads(repository.get_workspace_state(IMPORT_CHOICES_STATE_KEY) or '{}')
    except (TypeError, ValueError):
        return {}
    return {str(key): str(value) for key, value in values.items() if value in IMPORT_CHOICES} if isinstance(values, dict) else {}


def set_import_choices(repository: Any, choices: dict[int, str]) -> None:
    """Keep the Flex choice of the upload review of each CDR (``flex`` or ``not_flex``) until it is processed."""
    values = import_choices(repository)
    values.update({str(int(dataset_id)): choice for dataset_id, choice in choices.items() if choice in IMPORT_CHOICES})
    repository.set_workspace_state(IMPORT_CHOICES_STATE_KEY, json.dumps(values))


def apply_import_choices(repository: Any, username: str = '') -> list[dict[str, Any]]:
    """Apply the Flex choices of the upload review of the CDRs processed since: ``flex`` marks the CDR as Flex (unless
    it already is), ``not_flex`` hides its suggestion for good. The choices of CDRs still waiting stay; those of failed,
    stopped or deleted CDRs are dropped. Returns what was applied."""
    from src.modules.cdr.cdr_auto_selection import cdr_campaigns, is_flex_cdr

    pending = import_choices(repository)
    if not pending:
        return []
    by_id = {str(int(dataset['id'])): dataset for dataset in repository.list_datasets()}
    applied: list[dict[str, Any]] = []
    remaining: dict[str, str] = {}
    for key, choice in pending.items():
        dataset = by_id.get(key)
        status = str(_row(dataset, 'status', '')) if dataset is not None else ''
        if dataset is not None and status in {'queued', 'processing', 'pending', ''}:
            remaining[key] = choice
            continue
        if dataset is None or status != 'ready' or str(_row(dataset, 'dataset_kind', '')).casefold() not in CDR_KINDS:
            continue
        entry: dict[str, Any] = {'dataset_id': int(key), 'file': str(dataset['file_name']), 'choice': choice}
        if choice == 'not_flex':
            dismiss(repository, dataset, always=True)
        else:
            label, campaigns = proposed_label(repository, dataset)
            if is_flex_cdr(cdr_campaigns(repository, [int(key)]).get(int(key)) or [], _row(dataset, 'campaign', '')):
                entry['already_flex'] = True
            else:
                try:
                    entry.update(mark_cdr_as_flex(repository, dataset, label, campaigns, username), campaigns=campaigns)
                except ValueError as exc:
                    entry['error'] = str(exc)
        applied.append(entry)
    repository.set_workspace_state(IMPORT_CHOICES_STATE_KEY, json.dumps(remaining))
    return applied


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
