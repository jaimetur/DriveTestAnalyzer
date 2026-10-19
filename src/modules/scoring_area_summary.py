"""National & Geographical Areas Trends: the National scoring next to the scoring of chosen cities and areas.

A scoring job can ask for an area summary, also with Region, Cluster or City filters: the summary is always scored
on the whole country (the job's other filters apply). The same job, from the CDR rows it already loaded (those of the
whole country, read apart when the job has area filters, or, when the summary has campaigns of its own, from the CDRs
of those campaigns), then calculates up to three scorings with different Split by levels:

* National: Operator, split by the summary's time split;
* the chosen cities (for example London), each scored with its own tests only;
* the breakdown: one scoring per Region, Cluster or City.

The time split of the summary aggregates every selected CDR into one value (All), splits by
Campaign, or splits by the Daily, Weekly, Monthly, Quarterly or Yearly period of the start time
of each test. Each area is scored with its own measurements: KPI values (rates, medians,
P90...) are not additive and the points come from non-linear thresholds, so they cannot be
derived from the National scoring. A calculation equal to the job's own reuses the job's result.

The Geographical views of a job split by no Region, Cluster or City are calculated the same way, from the job's own
rows and filters: one scoring per Region and one of the separate cities of its National & Geographical Areas Trends,
or of London when they have none (see ``geographical_passes``).
"""
from __future__ import annotations

from typing import Any, Callable

import pandas as pd

from src.modules.cdr_auto_selection import campaign_presets
from src.modules.column_names import campaign_sort_key, column_identity, resolve_column_name
from src.modules.scoring import START_TIME_COLUMNS, normalize_time_split

AREA_SUMMARY_BREAKDOWNS = ('Region', 'Cluster', 'City')
GEOGRAPHIC_FILTER_FIELDS = ('Region', 'Cluster', 'City')
# All aggregates every selected CDR; Campaign splits by campaign; the periods split by the tests' start time.
AREA_SUMMARY_TIME_SPLITS = ('All', 'Campaign', 'Daily', 'Weekly', 'Monthly', 'Quarterly', 'Yearly')
NATIONAL = 'National'
# The prefix of the warnings of the summary (summaries calculated before name it National & Areas Trends or National
# & Area Summary).
WARNING_PREFIXES = ('National & Geographical Areas Trends:', 'National & Areas Trends:', 'National & Area Summary:')
_CITY_COLUMNS = ('City', 'G_Level_4')
# The Geographical Areas & Scoring Trends of a job that chooses neither a Breakdown nor Separate cities (one saved when
# they could be left out): each Region and London.
DEFAULT_GEOGRAPHICAL_AREAS = {'breakdown': 'Region', 'cities': ['London']}
GEOGRAPHICAL_CITIES = tuple(DEFAULT_GEOGRAPHICAL_AREAS['cities'])
# Among the Separate cities of a request, the Main Cities of the workspace when it is calculated.
MAIN_CITIES_TOKEN = '@main-cities'
_AREA_IDENTITIES = {column_identity(field) for field in GEOGRAPHIC_FILTER_FIELDS}
# Saved per calculation: what the views of the summary read. The points-lost shares stay with the job's own result.
_PASS_RESULT_KEYS = ('scoring', 'totals', 'global_kpis', 'environment_scaling', 'aggregation_levels',
                     'aggregation_contract_version', 'campaigns', 'warnings', 'notices', 'baseline_aliases')


def normalize_trend_campaigns(values: Any) -> list[str]:
    """The campaigns of the summary: campaign names, or one automatic choice (Latest 2 campaigns…) alone."""
    names: dict[str, str] = {}
    for value in values if isinstance(values, (list, tuple, set)) else [values] if values else []:
        text = str(value or '').strip()[:200]
        if text:
            names.setdefault(text.casefold(), text)
    presets = campaign_presets(names.values())
    return presets[:1] if presets else list(names.values())


def normalize_area_summary_request(area_summary: Any, context_filters: dict[str, list[str]] | None = None) -> dict[str, Any]:
    """The Geographical Areas & Scoring Trends of a job, always included: the breakdown level and the separate cities
    of the Geographical Areas and of the National & Geographical Areas Trends, the time split of the trends and their
    campaigns (without campaigns of their own, the trends score the campaigns of the job). One without a breakdown or
    separate cities (none, or one saved when the trends could be left out) takes each Region and London.

    The summary is scored on the whole country, whatever Region, Cluster or City filters the job has
    (see ``whole_country_filters``).
    """
    area_summary = area_summary if isinstance(area_summary, dict) else {}
    # Main Cities (the flag, or its token among the cities) stand for the Main Cities of the workspace when it is calculated.
    main_cities = bool(area_summary.get('main_cities')) or any(
        str(city).strip() == MAIN_CITIES_TOKEN for city in area_summary.get('cities') or [])
    explicit = {**area_summary, 'cities': [city for city in area_summary.get('cities') or [] if str(city).strip() != MAIN_CITIES_TOKEN]}
    if main_cities:
        # (They are Separate cities: no breakdown is then a choice, not one saved without areas.)
        breakdown = geographical_areas({**explicit, 'cities': ['-']})[0]
        cities = geographical_areas({'breakdown': 'Region', 'cities': explicit['cities']})[1] if explicit['cities'] else []
    else:
        breakdown, cities = geographical_areas(explicit)
    split = str(area_summary.get('time_split') or '').strip().casefold()
    time_split = next((name for name in AREA_SUMMARY_TIME_SPLITS if name.casefold() == split), 'Campaign')
    normalized = {'breakdown': breakdown, 'cities': cities, 'time_split': time_split}
    if main_cities:
        normalized['main_cities'] = True
    campaigns = normalize_trend_campaigns(area_summary.get('campaigns'))
    # (Without campaigns of its own, the request keeps the form of the summaries saved before they had any.)
    if campaigns:
        normalized['campaigns'] = campaigns
    return normalized


def resolve_main_cities(area_summary: Any, main_cities: list[str]) -> Any:
    """The Geographical Areas & Scoring Trends of a job with its Main Cities as the Main Cities of the workspace now (after
    its other Separate cities), as they are calculated."""
    if not isinstance(area_summary, dict) or not area_summary.get('main_cities'):
        return area_summary
    cities: dict[str, str] = {}
    for city in [*(area_summary.get('cities') or []), *(main_cities or [])]:
        if str(city).strip():
            cities.setdefault(str(city).strip().casefold(), str(city).strip())
    resolved = {key: value for key, value in area_summary.items() if key != 'main_cities'}
    return {**resolved, 'cities': list(cities.values())}


def has_area_filters(context_filters: dict[str, list[str]] | None) -> bool:
    """Whether a job leaves out part of the country with Region, Cluster or City filters."""
    return any((context_filters or {}).get(field) for field in GEOGRAPHIC_FILTER_FIELDS)


def whole_country_filters(context_filters: dict[str, list[str]] | None) -> dict[str, list[str]]:
    """The filters of a job without its Region, Cluster and City filters: those of its area summary."""
    return {field: values for field, values in (context_filters or {}).items() if field not in GEOGRAPHIC_FILTER_FIELDS}


def area_summary_levels(levels: list[str], area_summary: dict[str, Any] | None) -> list[str]:
    """The columns the job reads for its area summary, besides its own levels: the breakdown, City
    and, to split by period, the start time of the tests."""
    if not area_summary:
        return []
    extra = [area_summary['breakdown']] if area_summary.get('breakdown') else []
    if area_summary.get('cities') and 'City' not in extra:
        extra.append('City')
    if normalize_time_split(area_summary.get('time_split')):
        extra.extend(START_TIME_COLUMNS)
    identities = {column_identity(level) for level in levels}
    return [level for level in extra if column_identity(level) not in identities]


def _passes(levels: list[str], area_summary: dict[str, Any], job_filtered: bool = False) -> list[dict[str, Any]]:
    time_split = area_summary.get('time_split') or 'Campaign'
    base = ['Operator'] if time_split == 'All' else ['Operator', 'Campaign']
    breakdown = area_summary.get('breakdown')
    passes = [{'kind': NATIONAL, 'field': None, 'levels': base}]
    # A City breakdown already scores the chosen cities: they are listed first among its rows.
    if area_summary.get('cities') and breakdown != 'City':
        passes.append({'kind': 'City', 'field': 'city', 'levels': [*base, 'City'], 'cities': area_summary['cities']})
    if breakdown:
        passes.append({'kind': breakdown, 'field': breakdown.lower(), 'levels': [*base, breakdown]})
    identities = {column_identity(level) for level in levels}
    # A calculation split by period is never the job's own, which splits Campaign by campaign; nor is one of a job
    # with area filters, which scores part of the country.
    for item in passes:
        item['reuses_job'] = (not job_filtered and not normalize_time_split(time_split) and 'cities' not in item
                              and {column_identity(level) for level in item['levels']} == identities)
    return passes


def _city_frames(frames: dict[str, pd.DataFrame], cities: list[str]) -> dict[str, pd.DataFrame]:
    wanted = {city.casefold() for city in cities}
    selected = {}
    for kind, frame in frames.items():
        column = next((resolved for alias in _CITY_COLUMNS
                       if (resolved := resolve_column_name(frame.columns, alias)) is not None), None)
        if column is None:
            continue
        mask = frame[column].astype('string').str.strip().str.casefold().isin(wanted).fillna(False)
        if mask.any():
            selected[kind] = frame[mask.to_numpy(dtype=bool)].reset_index(drop=True)
    return selected


def calculate_area_summary(calculate: Callable[..., dict], frames: dict[str, pd.DataFrame], levels: list[str],
                           area_summary: dict[str, Any], call_kwargs: dict[str, Any],
                           progress: Callable[[int, str], None] | None = None, *, job_filtered: bool = False) -> dict[str, Any]:
    """Score the National, chosen-city and breakdown calculations of an area summary from the loaded rows (those of
    the whole country: with ``job_filtered``, the job's own rows have area filters and are never reused)."""
    passes = []
    warnings = []
    period = normalize_time_split(area_summary.get('time_split'))
    kwargs = {**call_kwargs, 'time_split': period} if period else call_kwargs
    for index, item in enumerate(_passes(levels, area_summary, job_filtered)):
        saved = {key: item[key] for key in ('kind', 'field', 'levels', 'reuses_job') if key in item}
        if 'cities' in item:
            saved['cities'] = item['cities']
        if not item['reuses_job']:
            if progress is not None:
                progress(88 + index * 2, f"Calculating the {item['kind']} scoring of the area summary")
            source = _city_frames(frames, item['cities']) if 'cities' in item else frames
            result = calculate(source, item['levels'], **kwargs) if source else {}
            rows = result.get('scoring') if isinstance(result, dict) else None
            if not rows or (item['field'] and not any(row.get(item['field']) not in (None, '') for row in rows)):
                what = ', '.join(item['cities']) if 'cities' in item else item['kind']
                warnings.append(f'National & Geographical Areas Trends: the selected CDRs have no {what} measurements.')
                continue
            saved['result'] = {key: result[key] for key in _PASS_RESULT_KEYS if key in result}
        passes.append(saved)
    return {'breakdown': area_summary.get('breakdown'), 'cities': list(area_summary.get('cities') or []),
            'time_split': area_summary.get('time_split') or 'Campaign', 'passes': passes, 'warnings': warnings}


def calculate_area_summary_from_history(calculate: Callable[..., dict], levels: list[str], area_summary: dict[str, Any],
                                        progress: Callable[[int, str], None] | None = None, *,
                                        job_filtered: bool = False) -> dict[str, Any]:
    """The National, chosen-city and breakdown calculations of an area summary from the Scoring History.

    ``calculate(levels, time_split=..., cities=...)`` scores the job's CDRs and filters (without its area filters)
    from the history.
    """
    passes = []
    warnings = []
    period = normalize_time_split(area_summary.get('time_split'))
    for index, item in enumerate(_passes(levels, area_summary, job_filtered)):
        saved = {key: item[key] for key in ('kind', 'field', 'levels', 'reuses_job') if key in item}
        if 'cities' in item:
            saved['cities'] = item['cities']
        if not item['reuses_job']:
            if progress is not None:
                progress(88 + index * 2, f"Calculating the {item['kind']} scoring of the area summary")
            result = calculate(item['levels'], time_split=period, cities=item.get('cities'))
            rows = result.get('scoring') if isinstance(result, dict) else None
            if not rows or (item['field'] and not any(row.get(item['field']) not in (None, '') for row in rows)):
                what = ', '.join(item['cities']) if 'cities' in item else item['kind']
                warnings.append(f'National & Geographical Areas Trends: the selected CDRs have no {what} measurements.')
                continue
            saved['result'] = {key: result[key] for key in _PASS_RESULT_KEYS if key in result}
        passes.append(saved)
    return {'breakdown': area_summary.get('breakdown'), 'cities': list(area_summary.get('cities') or []),
            'time_split': area_summary.get('time_split') or 'Campaign', 'passes': passes, 'warnings': warnings}


def geographical_areas(areas: Any) -> tuple[str | None, list[str]]:
    """The Breakdown and Separate cities of the Geographical Areas & Scoring Trends of a job (Region and London without
    any)."""
    areas = areas if isinstance(areas, dict) else {}
    breakdown = next((name for name in AREA_SUMMARY_BREAKDOWNS
                      if name.casefold() == str(areas.get('breakdown') or '').strip().casefold()), None)
    chosen: dict[str, str] = {}
    for city in areas.get('cities') or []:
        if str(city).strip():
            chosen.setdefault(str(city).strip().casefold(), str(city).strip())
    cities = list(chosen.values())
    if breakdown is None and not cities:
        return DEFAULT_GEOGRAPHICAL_AREAS['breakdown'], list(DEFAULT_GEOGRAPHICAL_AREAS['cities'])
    return breakdown, cities


def geographical_passes(levels: list[str], areas: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """The calculations of the Geographical views of a job, whatever its Split by: its levels without Region, Cluster
    and City, first on their own (the scoring Nationwide), then split by the Breakdown of its Geographical Areas & Scoring
    Trends (``areas``), and by City for its Separate cities alone (not with a City breakdown, which scores them too)."""
    breakdown, cities = geographical_areas(areas)
    base = [level for level in levels if column_identity(level) not in _AREA_IDENTITIES]
    passes = [{'kind': NATIONAL, 'field': None, 'levels': list(base)}]
    if breakdown:
        passes.append({'kind': breakdown, 'field': breakdown.lower(), 'levels': [*base, breakdown]})
    if cities and breakdown != 'City':
        passes.append({'kind': 'City', 'field': 'city', 'levels': [*base, 'City'], 'cities': cities})
    return passes


def geographical_levels(levels: list[str], areas: dict[str, Any] | None = None) -> list[str]:
    """The columns the job reads for its Geographical views, besides its own levels."""
    identities = {column_identity(level) for level in levels}
    extra = [item['levels'][-1] for item in geographical_passes(levels, areas) if item['field']]
    return [level for level in dict.fromkeys(extra) if column_identity(level) not in identities]


def _summary_result(item: dict[str, Any], summary: dict[str, Any] | None) -> dict[str, Any] | None:
    """The result of the calculation of an area summary equal to a Geographical one (the same split, cities and filters,
    without a split by period), which is then not calculated again."""
    if not isinstance(summary, dict) or normalize_time_split(summary.get('time_split')):
        return None
    identities = {column_identity(level) for level in item['levels']}
    cities = [city.casefold() for city in item.get('cities') or []]
    for saved in summary.get('passes') or []:
        if (isinstance(saved, dict) and saved.get('kind') == item['kind'] and isinstance(saved.get('result'), dict)
                and [city.casefold() for city in saved.get('cities') or []] == cities
                and {column_identity(level) for level in saved.get('levels') or []} == identities):
            return saved['result']
    return None


def _summary_reuses_job(item: dict[str, Any], summary: dict[str, Any] | None) -> bool:
    """Whether the area summary has the same calculation as ``item`` and took it from the job's own."""
    if not isinstance(summary, dict) or normalize_time_split(summary.get('time_split')) or 'cities' in item:
        return False
    identities = {column_identity(level) for level in item['levels']}
    return any(isinstance(saved, dict) and saved.get('kind') == item['kind'] and saved.get('reuses_job')
               and {column_identity(level) for level in saved.get('levels') or []} == identities
               for saved in summary.get('passes') or [])


def _geographical(score: Callable[[dict[str, Any]], dict | None], levels: list[str],
                  progress: Callable[[int, str], None] | None, summary: dict[str, Any] | None = None,
                  areas: dict[str, Any] | None = None, reuse_job: bool = False) -> dict[str, Any] | None:
    passes = []
    identities = {column_identity(level) for level in levels}
    for item in geographical_passes(levels, areas):
        if reuse_job and 'cities' not in item and {column_identity(level) for level in item['levels']} == identities:
            # The job's own calculation (of the whole country, split by the same levels): its result is read from it.
            passes.append({**item, 'reuses_job': True})
            continue
        if _summary_result(item, summary) is not None:
            # The same calculation as one of the area summary: its result is read from there.
            passes.append({**item, 'reuses_job': False, 'reuses_summary': True})
            continue
        if _summary_reuses_job(item, summary):
            # (The National calculation of a summary that is the job's own: the job's.)
            passes.append({**item, 'reuses_job': True})
            continue
        if progress is not None:
            progress(86, f"Calculating the Geographical views per {item['kind']}")
        try:
            result = score(item)
        except ValueError:  # Filters that leave none of its measurements (no tests in its cities).
            result = None
        rows = result.get('scoring') if isinstance(result, dict) else None
        # A calculation without measurements of its areas is left out, without a warning: the views are optional.
        if rows and (item['field'] is None or any(row.get(item['field']) not in (None, '') for row in rows)):
            passes.append({**item, 'reuses_job': False, 'result': {key: result[key] for key in _PASS_RESULT_KEYS if key in result}})
    return {'passes': passes} if passes else None


def calculate_geographical(calculate: Callable[..., dict], frames: dict[str, pd.DataFrame], levels: list[str],
                           call_kwargs: dict[str, Any], progress: Callable[[int, str], None] | None = None,
                           summary: dict[str, Any] | None = None, areas: dict[str, Any] | None = None,
                           reuse_job: bool = False) -> dict[str, Any] | None:
    """The Geographical calculations of a job from the rows of the whole country (``frames``: those of the job without
    its Region, Cluster and City filters): ``{'passes': [...]}`` in the form of an area summary, or None; ``areas`` are
    its Breakdown and Separate cities (see geographical_passes). Those equal to the job's own calculation
    (``reuse_job``: a job without area filters) or to a calculation of ``summary`` (an area summary of the same rows and
    filters) take its result."""
    def score(item: dict[str, Any]) -> dict | None:
        source = _city_frames(frames, item['cities']) if 'cities' in item else frames
        return calculate(source, item['levels'], **call_kwargs) if source else None
    return _geographical(score, levels, progress, summary, areas, reuse_job)


def calculate_geographical_from_history(calculate: Callable[..., dict], levels: list[str],
                                        progress: Callable[[int, str], None] | None = None,
                                        summary: dict[str, Any] | None = None,
                                        areas: dict[str, Any] | None = None, reuse_job: bool = False) -> dict[str, Any] | None:
    """The Geographical calculations of a job from the Scoring History; ``calculate(levels, cities=...)`` scores the
    job's CDRs and filters without its Region, Cluster and City filters."""
    return _geographical(lambda item: calculate(item['levels'], cities=item.get('cities')), levels, progress, summary,
                         areas, reuse_job)


def geographical_insights(job: dict[str, Any], result: dict[str, Any], operator_mapping_groups: list[dict] | None = None,
                          *, vendor_mapping_groups: list[dict] | None = None) -> dict[str, list[dict[str, Any]]]:
    """The location cards and rankings of the Geographical calculations of a job split by no area: the Regions, and
    each of its separate cities (else London) on its own card."""
    from src.modules.scoring_views import build_scoring_views

    insights: dict[str, list[dict[str, Any]]] = {'location_cards': [], 'location_rankings': []}
    geographical = result.get('geographical') if isinstance(result, dict) else None
    if not isinstance(geographical, dict):
        return insights
    configuration = result.get('configuration') or job.get('configuration')
    passes = [item for item in geographical.get('passes') or [] if isinstance(item, dict)]
    if not any(item.get('kind') == NATIONAL for item in passes):
        # Results calculated before the scoring Nationwide was one of them: the job's own calculation when it is of the
        # whole country with the same levels, else the National calculation of its area summary.
        levels = list(job.get('levels') or job.get('aggregation_levels') or [])
        base = [level for level in levels if column_identity(level) not in _AREA_IDENTITIES]
        national = {'kind': NATIONAL, 'field': None, 'levels': base}
        if base and len(base) == len(levels) and not has_area_filters(job.get('context_filters')):
            passes.insert(0, {**national, 'reuses_job': True})
        elif base and _summary_result(national, result.get('area_summary')) is not None:
            passes.insert(0, {**national, 'reuses_job': False, 'reuses_summary': True})
    for item in passes:
        if item.get('reuses_job'):
            source = {key: result[key] for key in _PASS_RESULT_KEYS if key in result}
        elif item.get('reuses_summary'):
            source = _summary_result(item, result.get('area_summary'))
        else:
            source = item.get('result')
        if not isinstance(source, dict) or not source.get('scoring'):
            continue
        source_job = {'levels': list(item['levels']), 'aggregation_levels': list(item['levels']),
                      'aggregation_contract_version': job.get('aggregation_contract_version') or 2,
                      'baseline_operator': job.get('baseline_operator') or 'EE',
                      'baseline_aliases': job.get('baseline_aliases') or source.get('baseline_aliases'),
                      'configuration': configuration, 'keep_levels': [item['kind']], 'location_minimum': 1,
                      # The scoring Nationwide: a card of the whole country before the cards of the areas.
                      'national_cards': item['kind'] == NATIONAL}
        payload = {**source, 'configuration': source.get('configuration') or configuration}
        # By campaign, the rows of each methodology are scored with it.
        if result.get('methodology_groups') and not source.get('methodology_groups'):
            payload['methodology_groups'] = result['methodology_groups']
        views = build_scoring_views(source_job, payload, operator_mapping_groups, vendor_mapping_groups=vendor_mapping_groups)
        for key in insights:
            insights[key].extend((views.get('insights') or {}).get(key) or [])
    return insights


def detach_area_summary(result: dict[str, Any]) -> dict[str, Any]:
    """The result with the calculations of its area summary that reuse it holding a copy of it instead: the summary
    of National & Geographical Areas Trends with campaigns of their own is scored apart from the job, which it then joins."""
    summary = result.get('area_summary') if isinstance(result, dict) else None
    if not isinstance(summary, dict):
        return result
    own = {key: result[key] for key in _PASS_RESULT_KEYS if key in result}
    passes = [{**item, 'reuses_job': False, 'result': own} if isinstance(item, dict) and item.get('reuses_job') else item
              for item in summary.get('passes') or []]
    return {**result, 'area_summary': {**summary, 'passes': passes}}


def most_reliable_area_summary(summary: Any, transform: Callable[[dict], dict | None]) -> Any:
    """The area summary of the Most Reliable scoring: each calculation transformed like the job's own result."""
    if not isinstance(summary, dict) or not isinstance(summary.get('passes'), list):
        return summary
    # The calculations of a summary with campaigns of its own follow their methodology.
    own = {key: summary[key] for key in ('configuration', 'methodology_groups') if summary.get(key)}
    passes = []
    for item in summary['passes']:
        # (A calculation that reuses the job's or the summary's reads their transformed rows.)
        if isinstance(item, dict) and isinstance(item.get('result'), dict) and not (item.get('reuses_job') or item.get('reuses_summary')):
            reliable = transform({**item['result'], **own})
            if reliable is None:
                continue
            item = {**item, 'result': reliable}
        passes.append(item)
    return {**summary, 'passes': passes}


def _single_value(rows: list[dict[str, Any]], field: str) -> Any:
    values = {row.get(field) for row in rows if row.get(field) not in (None, '')}
    return next(iter(values)) if len(values) == 1 else None


def _summary_areas(job: dict[str, Any], result: dict[str, Any], summary: dict[str, Any],
                   operator_mapping_groups: list[dict] | None, vendor_mapping_groups: list[dict] | None,
                   kinds: set[str] | None = None) -> list[dict[str, Any]]:
    """The areas of a summary in order (National, the areas of the breakdown, then the cities), each with the score
    tables of every campaign or period; ``kinds`` keeps only the calculations of those kinds."""
    from src.modules.scoring_insights import _scopes
    from src.modules.scoring_views import build_scoring_views

    # A summary with campaigns of its own was scored with their methodology (By campaign, each campaign's).
    default_configuration = summary.get('configuration') or job.get('configuration') or result.get('configuration')
    chosen = [city.casefold() for city in summary.get('cities') or []]
    areas: list[dict[str, Any]] = []
    for item in summary['passes']:
        if kinds is not None and item.get('kind') not in kinds:
            continue
        if item.get('reuses_job'):
            source, source_job = result, job
            configuration = job.get('configuration') or result.get('configuration')
            payload = {**source, 'configuration': configuration}
        else:
            source = item.get('result')
            if not isinstance(source, dict):
                continue
            configuration = source.get('configuration') or default_configuration
            source_job = {'levels': list(item['levels']), 'aggregation_levels': list(item['levels']),
                          'aggregation_contract_version': job.get('aggregation_contract_version') or 2,
                          'baseline_operator': job.get('baseline_operator') or 'EE',
                          'baseline_aliases': job.get('baseline_aliases') or source.get('baseline_aliases'),
                          'configuration': configuration}
            payload = {**source, 'configuration': configuration}
            if summary.get('methodology_groups') and not source.get('methodology_groups'):
                payload['methodology_groups'] = summary['methodology_groups']
        views = build_scoring_views(source_job, payload, operator_mapping_groups, vendor_mapping_groups=vendor_mapping_groups)
        field = item.get('field')
        single = _single_value(source.get('scoring') or [], field) if field else None
        # An area measured in a single campaign has no campaign in its scope: it is that campaign.
        single_campaign = _single_value(source.get('scoring') or [], 'campaign') if 'Campaign' in item['levels'] else None
        by_label: dict[str, dict[str, Any]] = {}
        for scope, tables in _scopes(views.get('score_tables', [])).items():
            context = dict(scope)
            label = NATIONAL if field is None else context.get(field) or single
            if label in (None, ''):
                continue
            area = by_label.setdefault(str(label), {'label': str(label), 'kind': item['kind'], 'campaigns': {}})
            area['campaigns'][context.get('campaign') or single_campaign] = tables
        found = list(by_label.values())
        if item['kind'] == 'City' or (field == 'city' and chosen):
            # The chosen cities first, in the order they were chosen.
            order = {city: index for index, city in enumerate(chosen)}
            found.sort(key=lambda area: (order.get(area['label'].casefold(), len(order)), area['label'].casefold()))
        elif field is not None:
            found.sort(key=lambda area: area['label'].casefold())
        areas.extend(found)
    # National first, then the Regions or Clusters of the breakdown, then the cities (the separate ones first).
    areas.sort(key=area_category)
    return areas


def area_category(area: dict[str, Any]) -> int:
    """The place of an area in a summary: National, the Regions or Clusters, then the cities."""
    return 0 if area.get('kind') == NATIONAL else 2 if area.get('kind') == 'City' else 1


def build_area_summary(job: dict[str, Any], result: dict[str, Any], operator_mapping_groups: list[dict] | None = None,
                       *, vendor_mapping_groups: list[dict] | None = None,
                       include_operator: Callable[[str, str], bool] | None = None) -> list[dict[str, Any]]:
    """One summary per environment: the areas in order (National, the breakdown, the cities) and,
    for each operator, its points in the latest campaign, the GAP to the reference and the change
    from the previous campaign, with its points in every campaign for the trend charts.
    """
    summary = result.get('area_summary') if isinstance(result, dict) else None
    if not isinstance(summary, dict) or not summary.get('passes'):
        return []
    areas = _summary_areas(job, result, summary, operator_mapping_groups, vendor_mapping_groups)
    if not areas:
        return []
    environments = list(dict.fromkeys(
        environment for area in areas for tables in area['campaigns'].values() for environment in tables
    ))
    summaries = [summary_item for environment in environments
                 if (summary_item := _environment_summary(areas, environment, include_operator)) is not None]
    for summary_item in summaries:
        summary_item['time_split'] = summary.get('time_split') or 'Campaign'
    return summaries


def build_national_trends(job: dict[str, Any], result: dict[str, Any], operator_mapping_groups: list[dict] | None = None,
                          *, vendor_mapping_groups: list[dict] | None = None) -> list[dict[str, Any]] | None:
    """The scoring trend of each environment from the National calculation of National & Geographical Areas Trends with campaigns
    of their own (every campaign or period of the summary, from two on), in the form of the job's campaign trends; None
    when the summary has no campaigns of its own (the trends then come from the job's campaigns)."""
    from src.modules.scoring_insights import MIN_TREND_CAMPAIGNS, _display, _scope_summary

    summary = result.get('area_summary') if isinstance(result, dict) else None
    if not isinstance(summary, dict) or not summary.get('campaigns'):
        return None
    if not summary.get('passes'):
        return []
    national = next(iter(_summary_areas(job, result, summary, operator_mapping_groups, vendor_mapping_groups,
                                        kinds={NATIONAL})), None)
    if national is None:
        return []
    campaigns = sorted((campaign for campaign in national['campaigns'] if campaign not in (None, '')), key=campaign_sort_key)
    if len(campaigns) < MIN_TREND_CAMPAIGNS:
        return []
    environments = list(dict.fromkeys(environment for tables in national['campaigns'].values() for environment in tables))
    trends = []
    for environment in environments:
        operators: dict[str, dict[str, Any]] = {}
        maximum = None
        for index, campaign in enumerate(campaigns):
            scope = _scope_summary(national['campaigns'][campaign], environment)
            if scope is None:
                continue
            maximum = scope['maximum'] if maximum is None else max(maximum, scope['maximum'])
            for item in scope['operators']:
                series = operators.setdefault(item['operator'], {
                    'operator': item['operator'], 'label': item['label'], 'color': item['color'],
                    'is_reference': item['is_reference'], 'points': [None] * len(campaigns),
                })
                series['points'][index] = item['total']
        if operators:
            trends.append({'environment': environment, 'title': '', 'maximum': maximum,
                           'campaigns': [_display('Campaign', campaign) for campaign in campaigns],
                           'series': list(operators.values())})
    return trends


def _environment_summary(areas: list[dict[str, Any]], environment: str,
                         include_operator: Callable[[str, str], bool] | None) -> dict[str, Any] | None:
    from src.modules.scoring_insights import _scope_summary

    campaigns = sorted({campaign for area in areas for campaign in area['campaigns'] if campaign not in (None, '')},
                       key=campaign_sort_key)
    latest = campaigns[-1] if campaigns else None
    previous = campaigns[-2] if len(campaigns) > 1 else None
    styles: dict[str, dict[str, Any]] = {}
    rows_by_area = []
    maximum = None
    scaled = False
    for area in areas:
        points: dict[Any, dict[str, dict[str, Any]]] = {}
        for campaign, tables in area['campaigns'].items():
            summary = _scope_summary(tables, environment)
            if summary is None:
                continue
            maximum = summary['maximum'] if maximum is None else max(maximum, summary['maximum'])
            scaled = scaled or summary['scaled']
            points[campaign] = {item['operator']: item for item in summary['operators']}
        current = points.get(latest) if latest is not None else points.get(None)
        # An area without measurements in the latest campaign (one still being measured, for example) keeps its
        # operators and trend, without a score: those of the latest campaign it was measured in.
        measured = bool(current)
        if not measured:
            current = next((points[campaign] for campaign in reversed(campaigns) if points.get(campaign)), None)
            if not current:
                continue
        before = points.get(previous) if previous is not None and measured else None
        reference = next((item for item in current.values() if item['is_reference']), None)
        rows = []
        for operator, item in current.items():
            if include_operator is not None and not item['is_reference'] and not include_operator(operator, item['label']):
                continue
            styles.setdefault(operator, {'label': item['label'], 'color': item['color'],
                                         'is_reference': item['is_reference']})
            prior = (before or {}).get(operator)
            rows.append({
                'operator': operator, 'label': item['label'], 'color': item['color'],
                'is_reference': item['is_reference'], 'points': item['total'] if measured else None,
                'complete': item['complete'] or not measured, 'order': item['total'],
                'gap': None if reference is None or item['is_reference'] or not measured else item['total'] - reference['total'],
                'delta': None if prior is None else item['total'] - prior['total'],
                'trend': [((points.get(campaign) or {}).get(operator) or {}).get('total') for campaign in campaigns],
            })
        if not rows:
            continue
        # The reference first, then the operators from the highest score.
        rows.sort(key=lambda row: (not row['is_reference'], -row.pop('order')))
        rows_by_area.append({'label': area['label'], 'kind': area['kind'], 'measured': measured, 'rows': rows})
    # National alone summarises nothing.
    if len(rows_by_area) < 2:
        return None
    reference = next((style['label'] for style in styles.values() if style['is_reference']), None)
    return {
        'environment': environment, 'maximum': maximum, 'scaled': scaled,
        'campaigns': campaigns, 'latest_campaign': latest, 'previous_campaign': previous,
        'reference_label': reference, 'operators': styles, 'areas': rows_by_area,
    }
