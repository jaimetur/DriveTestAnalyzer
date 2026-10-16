"""The CDRs of a module, chosen automatically from its NR Mode and Campaign filter.

PPT Dashboards, Scoring & GAP Analysis, CDR Analysis, Network Insights, Non-Qualified Calls
and their Reporting artifacts do not ask for CDRs: they use the CDRs that the combined CDR
tables include (see ``cdr_stage.combined_inclusion``: the Final CDR of a campaign before its
Weekly and Daily CDRs, the newest cumulative CDR before the previous ones, or the In
Combined? choice of the Workspace) of their NR Mode and whose campaigns are among the chosen
ones; every campaign when the Campaign filter is not restricted.

The Campaign filter of a saved definition (a Dashboard, a Reporting Job entry) also accepts
two choices made again each time they are used, so they follow the campaigns that arrive
later: **Latest campaign** and **Latest 2 campaigns**.
"""

from __future__ import annotations

import json
from typing import Any, Iterable

from src.modules.cdr_stage import _facts as cdr_stage_facts, combined_inclusion
from src.modules.column_names import campaign_sort_key, compact_campaign_value
from src.modules.nr_mode import dataset_nr_mode, normalize_nr_mode

CDR_KINDS = ('data', 'voice', 'speech')
CDR_KIND_LABELS = {'data': 'Data', 'voice': 'Voice', 'speech': 'Speech'}
LATEST_CAMPAIGN = '@latest-campaign'
LATEST_TWO_CAMPAIGNS = '@latest-2-campaigns'
ALL_CAMPAIGNS = '@all-campaigns'
# How many of the newest campaigns each choice stands for (None: every campaign of the NR Mode at that moment, so
# the campaigns that arrive later are included too, unlike a list of every campaign checked now).
CAMPAIGN_PRESETS = {LATEST_CAMPAIGN: 1, LATEST_TWO_CAMPAIGNS: 2, ALL_CAMPAIGNS: None}
CAMPAIGN_PRESET_LABELS = {LATEST_CAMPAIGN: 'Latest campaign', LATEST_TWO_CAMPAIGNS: 'Latest 2 campaigns',
                          ALL_CAMPAIGNS: 'All available campaigns'}


def _row(dataset: Any, key: str, default: Any = None) -> Any:
    try:
        value = dataset[key]
    except (KeyError, IndexError):
        return default
    return default if value is None else value


def is_campaign_preset(value: object) -> bool:
    return str(value or '').strip() in CAMPAIGN_PRESETS


def campaign_presets(values: Iterable[object] | None) -> list[str]:
    """The automatic choices among some Campaign filter values."""
    return [str(value).strip() for value in values or [] if is_campaign_preset(value)]


def campaign_identity(value: object) -> str:
    """One campaign whatever its spelling (UK_Q2_2026 and 2026-Q2 are the same campaign)."""
    return str(compact_campaign_value(value) or '').strip().casefold()


def candidate_cdrs(repository: Any, nr_mode: object = None, kinds: Iterable[str] = CDR_KINDS) -> list[dict[str, Any]]:
    """The ready CDRs of the NR Mode (or of every mode) that the combined CDR tables include, newest first."""
    wanted_kinds = {str(kind).casefold() for kind in kinds}
    mode = normalize_nr_mode(nr_mode)
    inclusion = combined_inclusion(repository)
    rows: list[dict[str, Any]] = []
    for dataset in repository.list_datasets():
        kind = str(_row(dataset, 'dataset_kind', '')).casefold()
        if str(_row(dataset, 'status', '')) != 'ready' or kind not in wanted_kinds:
            continue
        dataset_id = int(dataset['id'])
        if not (inclusion.get(dataset_id) or {}).get('included'):
            continue
        dataset_mode = dataset_nr_mode(kind, _row(dataset, 'nr_mode'), _row(dataset, 'file_name', ''))
        if mode and dataset_mode != mode:
            continue
        rows.append({
            'id': dataset_id, 'kind': kind, 'nr_mode': dataset_mode, 'file_name': str(_row(dataset, 'file_name', '')),
            'stage': (inclusion.get(dataset_id) or {}).get('stage') or 'final',
            'uploaded_at': str(_row(dataset, 'uploaded_at', '')), 'updated_at': str(_row(dataset, 'updated_at', '')),
            'dataset_campaign': str(_row(dataset, 'campaign', '') or ''),
        })
    return rows


def cdr_campaigns(repository: Any, dataset_ids: Iterable[int]) -> dict[int, list[str]]:
    """The Campaign values of the rows of each CDR, from its catalogue (a CDR without them has no campaign).

    They are the values the Campaign filters compare with the rows, never the Campaign column of Workspace.
    """
    ids = list(dict.fromkeys(int(value) for value in dataset_ids))
    campaigns: dict[int, list[str]] = {dataset_id: [] for dataset_id in ids}
    if not ids:
        return campaigns
    with repository.connection() as connection:
        has_catalogues = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'cdr_catalogues'").fetchone() is not None
        rows = connection.execute(
            f"SELECT dataset_id, campaigns_json FROM cdr_catalogues WHERE dataset_id IN ({','.join('?' for _ in ids)})", ids,
        ).fetchall() if has_catalogues else []
    for row in rows:
        try:
            values = json.loads(row['campaigns_json'] or '[]')
        except (TypeError, ValueError):
            values = []
        campaigns[int(row['dataset_id'])] = [str(value).strip() for value in values if str(value).strip()] if isinstance(values, list) else []
    missing = [dataset_id for dataset_id in ids if not campaigns[dataset_id]]
    if missing:
        # The campaigns the combined tables read once per CDR revision (never a scan of the rows here).
        datasets = [dataset for dataset in repository.list_datasets() if int(dataset['id']) in set(missing)
                    and str(_row(dataset, 'status', '')) == 'ready']
        try:
            facts = cdr_stage_facts(repository, datasets)
        except Exception:  # noqa: BLE001 - the CDR's own Campaign is used instead.
            facts = {}
        for dataset in datasets:
            dataset_id = int(dataset['id'])
            campaigns[dataset_id] = [str(value).strip() for value in (facts.get(dataset_id) or {}).get('campaigns') or []
                                     if str(value).strip()]
    return campaigns


def sort_campaigns(values: Iterable[object]) -> list[str]:
    """Distinct campaigns in chronological order (oldest first)."""
    unique = list(dict.fromkeys(str(value).strip() for value in values if str(value or '').strip()))
    return sorted(unique, key=lambda value: (campaign_sort_key(value), value.casefold()))


def campaign_values(repository: Any, nr_mode: object = None, kinds: Iterable[str] = CDR_KINDS) -> list[str]:
    """Every Campaign of the CDRs a module of the NR Mode can use, oldest first."""
    rows = candidate_cdrs(repository, nr_mode, kinds)
    index = cdr_campaigns(repository, [row['id'] for row in rows])
    return sort_campaigns(value for values in index.values() for value in values)


def campaign_groups(campaigns: Iterable[object]) -> list[list[str]]:
    """The campaigns newest first, each with every spelling of it (UK_Q2_2026 and 2026-Q2)."""
    groups: dict[str, list[str]] = {}
    for value in reversed(sort_campaigns(campaigns)):
        groups.setdefault(campaign_identity(value), []).append(value)
    return list(groups.values())


def latest_campaigns(campaigns: Iterable[object], count: int | None) -> list[str]:
    """The values of the newest ``count`` campaigns, or of every campaign with None (each with every spelling of it)."""
    groups = campaign_groups(campaigns)
    chosen = {value for group in (groups if count is None else groups[:max(0, int(count))]) for value in group}
    return [value for value in sort_campaigns(campaigns) if value in chosen]


def expand_campaign_filter(values: Iterable[object] | None, campaigns: Iterable[object]) -> list[str]:
    """A Campaign filter with its automatic choices replaced by the campaigns they stand for now."""
    selected = [str(value).strip() for value in values or [] if str(value or '').strip()]
    presets = campaign_presets(selected)
    if not presets:
        return selected
    counts = [CAMPAIGN_PRESETS[preset] for preset in presets]
    count = None if None in counts else max(counts)
    explicit = [value for value in selected if not is_campaign_preset(value)]
    return list(dict.fromkeys([*explicit, *latest_campaigns(campaigns, count)]))


def resolve_campaign_filter(repository: Any, nr_mode: object, values: Iterable[object] | None,
                            kinds: Iterable[str] = CDR_KINDS) -> list[str]:
    """The campaigns a Campaign filter chooses now in the NR Mode ([] for every campaign).

    Latest campaign and Latest 2 campaigns choose every campaign when the CDRs have none.
    """
    selected = [str(value).strip() for value in values or [] if str(value or '').strip()]
    if not campaign_presets(selected):
        return selected
    return expand_campaign_filter(selected, campaign_values(repository, nr_mode, kinds))


def resolve_cdrs(repository: Any, nr_mode: object, campaigns: Iterable[object] | None = None,
                 kinds: Iterable[str] = CDR_KINDS) -> dict[str, list[int]]:
    """The CDRs of each type a module uses for an NR Mode and Campaign filter, newest first.

    The combined CDR tables include them (the Final CDR of a campaign before its Weekly and Daily
    CDRs, or the In Combined? choice); a Campaign filter keeps the CDRs with any of its campaigns.
    """
    kinds = tuple(kinds)
    rows = candidate_cdrs(repository, nr_mode, kinds)
    wanted = {campaign_identity(value) for value in resolve_campaign_filter(repository, nr_mode, campaigns, kinds)}
    wanted.discard('')
    index = cdr_campaigns(repository, [row['id'] for row in rows]) if wanted else {}
    chosen: dict[str, list[int]] = {kind: [] for kind in kinds}
    for row in sorted(rows, key=lambda item: (item['uploaded_at'], item['id']), reverse=True):
        if wanted and not ({campaign_identity(value) for value in index.get(row['id'], [])} & wanted):
            continue
        chosen.setdefault(row['kind'], []).append(row['id'])
    return chosen


def describe_cdrs(repository: Any, chosen: dict[str, Iterable[int]]) -> dict[str, list[dict[str, Any]]]:
    """The CDRs of each type as the modules list them: id, file name, stage and campaigns (as the Campaign Maps show them)."""
    ids = [int(value) for values in chosen.values() for value in values or []]
    inclusion = combined_inclusion(repository) if ids else {}
    datasets = {int(dataset['id']): dataset for dataset in repository.list_datasets() if int(dataset['id']) in set(ids)}
    campaigns = cdr_campaigns(repository, ids)
    described: dict[str, list[dict[str, Any]]] = {}
    for kind, values in chosen.items():
        rows = []
        for value in values or []:
            dataset_id = int(value)
            dataset = datasets.get(dataset_id)
            stage = (inclusion.get(dataset_id) or {}).get('stage') or (str(_row(dataset, 'cdr_stage', '') or '') if dataset is not None else '')
            name = str(_row(dataset, 'file_name', '') or '') if dataset is not None else ''
            labels = sort_campaigns(compact_campaign_value(campaign) or campaign for campaign in campaigns.get(dataset_id) or [])
            rows.append({'id': dataset_id, 'name': name or f'CDR {dataset_id}', 'stage': stage or 'final', 'campaigns': labels})
        described[kind] = rows
    return described


def resolve_cdr_ids(repository: Any, nr_mode: object, campaigns: Iterable[object] | None = None,
                    kinds: Iterable[str] = CDR_KINDS) -> list[int]:
    """The CDRs of ``resolve_cdrs`` as one list, Data, Voice then Speech."""
    return [dataset_id for ids in resolve_cdrs(repository, nr_mode, campaigns, kinds).values() for dataset_id in ids]


def complete_campaign_cdrs(repository: Any, nr_mode: object, campaigns: Iterable[object] | None = None) -> tuple[list[int], list[str]]:
    """The CDRs of the campaigns with Data, Voice and Speech CDRs, and the campaigns left out for lacking a type.

    Scoring needs every campaign it scores in the three types: without a Campaign filter, the
    campaigns missing a type are left out instead of failing the calculation.
    """
    chosen = resolve_cdrs(repository, nr_mode, campaigns)
    ids = [dataset_id for values in chosen.values() for dataset_id in values]
    index = cdr_campaigns(repository, ids)
    kinds_by_campaign: dict[str, set[str]] = {}
    labels: dict[str, str] = {}
    kind_of = {dataset_id: kind for kind, values in chosen.items() for dataset_id in values}
    for dataset_id in ids:
        for value in index.get(dataset_id) or ['']:
            identity = campaign_identity(value)
            kinds_by_campaign.setdefault(identity, set()).add(kind_of[dataset_id])
            labels.setdefault(identity, compact_campaign_value(value) or value or 'No campaign')
    complete = {identity for identity, kinds in kinds_by_campaign.items() if set(CDR_KINDS) <= kinds}
    incomplete = [labels[identity] for identity in kinds_by_campaign if identity not in complete]
    kept = [dataset_id for dataset_id in ids
            if {campaign_identity(value) for value in index.get(dataset_id) or ['']} <= complete]
    return kept, sort_campaigns(incomplete)
