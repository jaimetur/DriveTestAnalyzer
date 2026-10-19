"""Cascading filter values of the CDRs a module can use.

The filters of PPT Dashboards, Scoring & GAP Analysis and Network Insights list the values of
every CDR of the chosen NR Mode (not only of the CDRs a selection already uses), and each filter
lists only the values that the other filters leave: choosing Vodafone as Operator leaves in
Vendor only the Vendors of Vodafone, and choosing a Campaign leaves its Operators, Regions and
Cities. Operators and Vendors are listed with the labels of the Operator and Vendor Maps.

Each CDR keeps the distinct combinations of its Campaign, Operator, Operator_Vendor, Vendor,
Region, Cluster, City and test environment in the **CDR Filter Facets** table, read once from its
rows after it is processed (or, for the CDRs processed before, in the background the first time
they are needed) and again only when it changes. Filling a list never reads the CDR rows: a CDR whose
combinations are not ready yet offers the values of its CDR catalogue meanwhile.
"""

from __future__ import annotations

import json
from collections import OrderedDict
from threading import Lock, Thread
from time import monotonic
from typing import Any, Iterable

from src.modules.cdr_auto_selection import campaign_identity, sort_campaigns
from src.modules.cdr_environments import environment_class
from src.modules.column_names import column_identity
from src.modules.mapping_order import dimension_order_key
from src.modules.value_maps import ValueMapper
from src.modules.value_patterns import ValueSet, is_pattern

FACETS_TABLE = 'cdr_filter_facets'
FACETS_VERSION = 2
# The fields kept per CDR, and the columns each one is read from (as the CDR catalogues).
FACET_FIELDS = ('Campaign', 'Operator', 'Operator_Vendor', 'Vendor', 'Region', 'Cluster', 'City', 'Environment')
FACET_COLUMN_ALIASES = {
    'Campaign': ('campaign',),
    'Operator': ('operator', 'operator_a', 'home_operator', 'home_operator_a'),
    'Operator_Vendor': ('Operator_Vendor',),
    'Vendor': ('Vendor',),
    'Region': ('region', 'g_level_2', 'g level 2'),
    'Cluster': ('Cluster',),
    'City': ('city', 'g_level_4', 'g level 4'),
    # The most detailed level first (Big Cities, Roads...): its value is listed as Cities, Towns or Roads and railways.
    'Environment': ('g_level_3', 'g level 3', 'g_level_2', 'g level 2'),
}
# The filters built from them: Vendor_Operator is Operator_Vendor the other way round.
FILTER_FIELDS = ('Campaign', 'Operator', 'Operator_Vendor', 'Vendor_Operator', 'Vendor', 'Region', 'Cluster', 'City')
# Filters only the modules that offer them ask for (Network Insights): other modules neither list nor apply them.
OPTIONAL_FILTER_FIELDS = ('Environment',)
MAPPED_KINDS = {'Operator': 'operator', 'Operator_Vendor': 'operator_vendor', 'Vendor_Operator': 'vendor_operator', 'Vendor': 'vendor'}
# The CDR catalogue lists of each filter, offered while the combinations of a CDR are not ready.
CATALOGUE_KEYS = {'Campaign': 'campaigns', 'Operator': 'operators', 'Operator_Vendor': 'vendors',
                  'Vendor': 'vendors_only', 'Region': 'regions', 'Cluster': 'clusters', 'City': 'cities'}
_FIELD_BY_IDENTITY = {column_identity(field): field for field in FILTER_FIELDS}
_FIELD_BY_IDENTITY.update({'operators': 'Operator', 'vendors': 'Vendor', 'vendoronly': 'Vendor', 'vendorv3': 'Vendor',
                           'opvendor': 'Operator_Vendor', 'operatorvendors': 'Operator_Vendor',
                           'vendoroperators': 'Vendor_Operator', 'campaigns': 'Campaign', 'regions': 'Region',
                           'clusters': 'Cluster', 'cities': 'City'})
_MEMORY: OrderedDict[tuple[str, int, str], tuple[tuple[str, ...], ...]] = OrderedDict()
_MEMORY_LIMIT = 256
_MEMORY_LOCK = Lock()
# The databases whose missing combinations are being read in the background.
_FILLING: set[str] = set()


def filter_field(name: object) -> str | None:
    """The facet filter a field name stands for (``vendors`` → Vendor), or ``None``."""
    return _FIELD_BY_IDENTITY.get(column_identity(name))


def _revision(dataset: Any) -> str:
    def value(key: str) -> str:
        try:
            return str(dataset[key] or '')
        except (KeyError, IndexError):
            return ''
    return '|'.join([str(FACETS_VERSION), value('updated_at'), value('processed_at'), value('row_count')])


def _ready_cdrs(repository: Any, dataset_ids: Iterable[int]) -> dict[int, Any]:
    wanted = {int(value) for value in dataset_ids}
    return {int(row['id']): row for row in repository.list_datasets()
            if int(row['id']) in wanted and str(row['status'] or '') == 'ready'}


def stored_facets(repository: Any, dataset_ids: Iterable[int]) -> tuple[dict[int, tuple[tuple[str, ...], ...]], list[int]]:
    """The combinations already read for each CDR, and the CDRs whose combinations are missing or out of date.

    Never reads the CDR rows.
    """
    datasets = _ready_cdrs(repository, dataset_ids)
    database = str(repository.db_path)
    found: dict[int, tuple[tuple[str, ...], ...]] = {}
    pending: list[int] = []
    for dataset_id, dataset in datasets.items():
        key = (database, dataset_id, _revision(dataset))
        with _MEMORY_LOCK:
            cached = _MEMORY.get(key)
            if cached is not None:
                _MEMORY.move_to_end(key)
                found[dataset_id] = cached
                continue
        pending.append(dataset_id)
    missing: list[int] = []
    if pending:
        with repository.connection() as connection:
            rows = {int(row['dataset_id']): row for row in connection.execute(
                f"SELECT dataset_id, revision, fields_json, rows_json FROM {FACETS_TABLE} "
                f"WHERE dataset_id IN ({','.join('?' for _ in pending)})", pending).fetchall()}
        for dataset_id in pending:
            revision = _revision(datasets[dataset_id])
            row = rows.get(dataset_id)
            combinations = None
            if row is not None and row['revision'] == revision:
                try:
                    if json.loads(row['fields_json'] or '[]') == list(FACET_FIELDS):
                        combinations = tuple(tuple(str(value) for value in item) for item in json.loads(row['rows_json'] or '[]'))
                except (TypeError, ValueError):
                    combinations = None
            if combinations is None:
                missing.append(dataset_id)
                continue
            _remember(database, dataset_id, revision, combinations)
            found[dataset_id] = combinations
    return found, missing


def _remember(database: str, dataset_id: int, revision: str, combinations: tuple[tuple[str, ...], ...]) -> None:
    with _MEMORY_LOCK:
        _MEMORY[(database, dataset_id, revision)] = combinations
        while len(_MEMORY) > _MEMORY_LIMIT:
            _MEMORY.popitem(last=False)


def read_facets(repository: Any, dataset_id: int) -> None:
    """Read the combinations of one CDR from its rows and keep them (one scan of its table)."""
    datasets = _ready_cdrs(repository, [dataset_id])
    if dataset_id not in datasets or not repository.dataset_rows_table_exists(dataset_id):
        return
    revision = _revision(datasets[dataset_id])
    repository.ensure_vendor_column(dataset_id)
    columns = set(repository.list_dataset_row_columns(dataset_id))
    expressions = []
    for field in FACET_FIELDS:
        # The first non-blank value of its columns (City, else G_Level_4), as every filter reads it.
        resolved = list(dict.fromkeys(column for alias in FACET_COLUMN_ALIASES[field]
                                      if (column := repository._resolve_dataset_row_column_name(columns, alias))))
        values = [f"NULLIF(TRIM(CAST({repository._quote_identifier(column)} AS TEXT)), '')" for column in resolved]
        expressions.append(f"COALESCE({', '.join(values)}, '')" if values else "''")
    table = repository._quote_identifier(repository.dataset_rows_table_name(dataset_id))
    selected = ', '.join(f'{expression} AS f{index}' for index, expression in enumerate(expressions))
    grouped = ', '.join(str(index + 1) for index in range(len(expressions)))
    with repository.connection() as connection:
        rows = connection.execute(f'SELECT {selected} FROM {table} GROUP BY {grouped}').fetchall()
    combinations = tuple(tuple(str(row[index] or '') for index in range(len(FACET_FIELDS))) for row in rows)
    # The revision may have changed while the rows were read (the CDR was mapped again): keep the one read.
    latest = _ready_cdrs(repository, [dataset_id]).get(dataset_id)
    if latest is None or _revision(latest) != revision:
        return
    with repository.connection() as connection:
        connection.execute(
            f"INSERT INTO {FACETS_TABLE} (dataset_id, revision, fields_json, rows_json, updated_at) "
            "VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP) ON CONFLICT(dataset_id) DO UPDATE SET "
            "revision = excluded.revision, fields_json = excluded.fields_json, rows_json = excluded.rows_json, "
            "updated_at = excluded.updated_at",
            (dataset_id, revision, json.dumps(list(FACET_FIELDS)),
             json.dumps([list(item) for item in combinations], ensure_ascii=False, separators=(',', ':'))),
        )
    _remember(str(repository.db_path), dataset_id, revision, combinations)


def fill_missing_facets(repository: Any, dataset_ids: Iterable[int] | None = None, max_seconds: float | None = None) -> int:
    """Read the combinations of the ready CDRs (of ``dataset_ids``, or every one) that do not have them.

    Returns how many were missing; with ``max_seconds`` it stops after that time and the rest wait for the next call.
    """
    if dataset_ids is None:
        dataset_ids = [int(row['id']) for row in repository.list_datasets()
                       if str(row['status'] or '') == 'ready' and str(row['dataset_kind'] or '').casefold() in {'data', 'voice', 'speech'}]
    _found, missing = stored_facets(repository, dataset_ids)
    started = monotonic()
    for dataset_id in missing:
        if max_seconds is not None and monotonic() - started > max_seconds:
            break
        try:
            read_facets(repository, dataset_id)
        except Exception:  # noqa: BLE001 - a CDR that cannot be read offers its catalogue values.
            continue
    return len(missing)


def request_missing_facets(repository: Any, dataset_ids: Iterable[int]) -> None:
    """Read in a background thread the combinations of the CDRs that do not have them yet."""
    ids = [int(value) for value in dataset_ids]
    database = str(repository.db_path)
    with _MEMORY_LOCK:
        if not ids or database in _FILLING:
            return
        _FILLING.add(database)

    def fill() -> None:
        try:
            fill_missing_facets(type(repository)(repository.db_path, repository.global_db_path), ids)
        except Exception:  # noqa: BLE001 - optional cache work.
            pass
        finally:
            with _MEMORY_LOCK:
                _FILLING.discard(database)

    Thread(target=fill, name='cdr-filter-facets', daemon=True).start()


def normalize_selections(selections: dict[str, Iterable[object]] | None) -> dict[str, set[str]]:
    """The chosen values of each facet filter (any spelling of its name), as comparison keys; empty filters left out."""
    normalized: dict[str, set[str]] = {}
    for name, values in (selections or {}).items():
        field = filter_field(name)
        if field is None:
            continue
        items = [values] if isinstance(values, str) else list(values or [])
        keys = set()
        for value in items:
            text = str(value or '').strip()
            if text:
                keys |= _keys(field, text)
        if keys:
            normalized.setdefault(field, set()).update(keys)
    return normalized


def _chosen(candidates: set[str], keys: set[str]) -> bool:
    """Whether a value (by its keys) is taken by the chosen keys of its filter, among which patterns (VF*, -Lebara; see
    value_patterns)."""
    if not any(is_pattern(key) for key in keys):
        return bool(candidates & keys)
    return ValueSet(keys).accepts(candidates)


def _keys(field: str, value: str, raw: str = '') -> set[str]:
    if field == 'Campaign':
        return {campaign_identity(value), value.casefold()} - {''}
    return {value.casefold(), raw.casefold()} - {''}


class _Mapping:
    """The Maps labels of the values of each field, each value mapped once per request."""

    def __init__(self, mapper: ValueMapper) -> None:
        self.mapper = mapper
        self.cache: dict[tuple[str, str], str] = {}

    def __call__(self, field: str, raw: str) -> str:
        key = (field, raw)
        if key not in self.cache:
            if not raw:
                value = ''
            elif field == 'Vendor_Operator':
                value = self.mapper.map('vendor_operator', self.mapper.vendor_operators([self('Operator_Vendor', raw)])[0])
            elif field in MAPPED_KINDS:
                value = str(self.mapper.map(MAPPED_KINDS[field], raw))
            elif field == 'Environment':
                value = environment_class(raw)
            else:
                value = raw
            self.cache[key] = value
        return self.cache[key]


def _order(field: str, values: Iterable[str], mapper: ValueMapper) -> list[str]:
    items = list(values)
    if field == 'Campaign':
        return sort_campaigns(items)
    if field in MAPPED_KINDS:
        return sorted(items, key=lambda value: dimension_order_key(MAPPED_KINDS[field], value, mapper.operator_groups, mapper.vendor_groups))
    return sorted(items, key=str.casefold)


def cascading_options(repository: Any, dataset_ids: Iterable[int], selections: dict[str, Iterable[object]] | None = None,
                      fields: Iterable[str] = FILTER_FIELDS, mapper: ValueMapper | None = None) -> dict[str, list[str]]:
    """The values each filter offers among the CDRs, given the values chosen in the other filters.

    A filter's own choice does not narrow its list. Operators and Vendors carry their Maps labels and
    follow the order of the Maps; Campaigns are in chronological order; the rest alphabetically.
    """
    ids = list(dict.fromkeys(int(value) for value in dataset_ids))
    mapper = mapper or ValueMapper.from_repository(repository)
    mapping = _Mapping(mapper)
    wanted = [field for field in fields if field in FILTER_FIELDS or field in OPTIONAL_FILTER_FIELDS]
    chosen = normalize_selections(selections)
    for field in OPTIONAL_FILTER_FIELDS:
        values = (selections or {}).get(field)
        keys = {str(value).strip().casefold() for value in ([values] if isinstance(values, str) else values or [])
                if str(value).strip()}
        if field in wanted and keys:
            chosen[field] = keys
    mapped_fields = (*FILTER_FIELDS, *(field for field in OPTIONAL_FILTER_FIELDS if field in wanted))
    values: dict[str, dict[str, str]] = {field: {} for field in wanted}

    def offer(field: str, value: str) -> None:
        if value and field in values:
            values[field].setdefault(value if field == 'Campaign' else value.casefold(), value)

    facets, missing = stored_facets(repository, ids)
    combinations = {combination for items in facets.values() for combination in items}
    for combination in combinations:
        raw = dict(zip(FACET_FIELDS, combination))
        raw['Vendor_Operator'] = raw['Operator_Vendor']
        mapped = {field: mapping(field, raw[field]) for field in mapped_fields}
        failing = [field for field, keys in chosen.items()
                   if not _chosen(_keys(field, mapped[field], raw[field] if field != 'Vendor_Operator' else ''), keys)]
        if len(failing) > 1:
            continue
        for field in wanted:
            if not failing or failing[0] == field:
                offer(field, mapped[field])
    if missing:
        # Until their combinations are read, these CDRs offer their catalogue values when they have
        # some value of every other chosen filter.
        request_missing_facets(repository, missing)
        catalogues = repository.cdr_catalogues_by_dataset(missing)
        for catalogue in catalogues.values():
            lists = {field: [str(value) for value in catalogue.get(key) or []] for field, key in CATALOGUE_KEYS.items()}
            lists['Vendor_Operator'] = lists['Operator_Vendor']
            mapped_lists = {field: [mapping(field, value) for value in items] for field, items in lists.items()}
            # A catalogue does not list environments: it may hold any of them.
            failing = [field for field, keys in chosen.items() if field in mapped_lists
                       and not any(_chosen(_keys(field, mapped, raw), keys) for mapped, raw in zip(mapped_lists[field], lists[field]))]
            if len(failing) > 1:
                continue
            for field in wanted:
                if not failing or failing[0] == field:
                    for value in mapped_lists.get(field, []):
                        offer(field, value)
    return {field: _order(field, values[field].values(), mapper) for field in wanted}


def matching_dataset_ids(repository: Any, dataset_ids: Iterable[int], selections: dict[str, Iterable[object]] | None,
                         mapper: ValueMapper | None = None) -> list[int]:
    """The CDRs with rows that every chosen filter value leaves (all of them without a choice, or not read yet)."""
    ids = list(dict.fromkeys(int(value) for value in dataset_ids))
    chosen = normalize_selections(selections)
    if not chosen:
        return ids
    mapping = _Mapping(mapper or ValueMapper.from_repository(repository))
    facets, _missing = stored_facets(repository, ids)
    kept = []
    for dataset_id in ids:
        if dataset_id not in facets:
            kept.append(dataset_id)
            continue
        for combination in facets[dataset_id]:
            raw = dict(zip(FACET_FIELDS, combination))
            raw['Vendor_Operator'] = raw['Operator_Vendor']
            if all(_chosen(_keys(field, mapping(field, raw[field]), raw[field] if field != 'Vendor_Operator' else ''), keys)
                   for field, keys in chosen.items()):
                kept.append(dataset_id)
                break
    return kept
