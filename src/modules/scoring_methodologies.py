"""Scoring methodologies by campaign.

A methodology can apply to some campaigns (its ``campaigns`` range, from one campaign to another, by year and
quarter). A calculation **By campaign** scores each campaign with the methodology that applies to it, so campaigns
measured with different rules (2026-Q3 added TikTok to Video Streaming) are compared with their own rules: each one
totals the same maximum, and a KPI only exists in the campaigns whose methodology has it.
"""

from __future__ import annotations

import copy
from typing import Any, Iterable

from src.modules.column_names import campaign_sort_key

BY_CAMPAIGN = 'by-campaign'
BY_CAMPAIGN_NAME = 'By campaign'
_RESULT_LISTS = ('scoring', 'global_kpis', 'totals', 'charts', 'gap', 'gap_totals', 'test_counts')


def _quarter(value: object) -> tuple[int, int] | None:
    year, quarter, *_rest = campaign_sort_key(str(value or ''))
    return (year, quarter) if year > 0 and quarter > 0 else None


def normalize_campaign_range(value: object) -> dict[str, str] | None:
    """The campaigns a methodology applies to, ``{'from': '2026-Q3', 'to': ''}`` (either end open), or None."""
    if value in (None, {}):
        return None
    if not isinstance(value, dict) or not set(value) <= {'from', 'to'}:
        raise ValueError('The campaigns of a methodology must give from and to campaigns.')
    bounds = {}
    for end in ('from', 'to'):
        text = str(value.get(end) or '').strip()
        if len(text) > 40:
            raise ValueError('A campaign of a methodology can have up to 40 characters.')
        if text and _quarter(text) is None:
            raise ValueError(f'The campaign {text} of a methodology needs its year and quarter, as 2026-Q3.')
        bounds[end] = text
    if not bounds['from'] and not bounds['to']:
        return None
    if bounds['from'] and bounds['to'] and _quarter(bounds['from']) > _quarter(bounds['to']):
        raise ValueError('The first campaign of a methodology must come before its last one.')
    return bounds


def campaign_quarters(campaigns: Iterable[str]) -> list[str]:
    """The quarters of the workspace's campaigns, as ``2026-Q3``: where a methodology can start or end."""
    quarters = sorted({quarter for quarter in (_quarter(campaign) for campaign in campaigns) if quarter})
    return [f'{year}-Q{quarter}' for year, quarter in quarters]


def check_campaign_overlaps(profiles: list[dict[str, Any]]) -> None:
    """Refuse methodologies whose campaigns overlap: each campaign is scored with one methodology only."""
    bounds = []
    for profile in profiles:
        campaigns = profile.get('campaigns') or {}
        if campaigns:
            low = _quarter(campaigns.get('from')) or (0, 0)
            high = _quarter(campaigns.get('to')) or (10 ** 6, 9)
            bounds.append((profile, low, high))
    for index, (first, low, high) in enumerate(bounds):
        for second, other_low, other_high in bounds[index + 1:]:
            if low <= other_high and other_low <= high:
                raise ValueError(f"The campaigns of {first['name']} and {second['name']} overlap: each campaign can "
                                 'only apply to one methodology.')


def applies_to(profile: dict[str, Any], campaign: object) -> bool:
    """Whether a methodology's campaigns include a campaign (by year and quarter)."""
    bounds = profile.get('campaigns') or {}
    quarter = _quarter(campaign)
    if not bounds or quarter is None:
        return False
    low, high = _quarter(bounds.get('from')), _quarter(bounds.get('to'))
    return (low is None or quarter >= low) and (high is None or quarter <= high)


def methodology_for(profiles: dict[str, Any], campaign: object) -> dict[str, Any]:
    """The methodology of a campaign: the one whose campaigns include it (the one starting latest if methodologies
    saved before overlaps were refused share it), else the default methodology."""
    candidates = [profile for profile in profiles['profiles'] if applies_to(profile, campaign)]
    if candidates:
        return max(candidates, key=lambda profile: _quarter((profile.get('campaigns') or {}).get('from')) or (0, 0))
    return next(profile for profile in profiles['profiles'] if profile['id'] == profiles['active_profile_id'])


def methodology_groups(profiles: dict[str, Any], campaigns: Iterable[str]) -> list[dict[str, Any]]:
    """The campaigns of a calculation grouped by their methodology, in campaign order."""
    groups: dict[str, dict[str, Any]] = {}
    for campaign in sorted(dict.fromkeys(campaigns), key=lambda value: (campaign_sort_key(value), value)):
        profile = methodology_for(profiles, campaign)
        group = groups.setdefault(profile['id'], {'profile_id': profile['id'], 'profile_name': profile['name'],
                                                  'configuration': profile['configuration'], 'campaigns': []})
        group['campaigns'].append(campaign)
    return list(groups.values())


def display_configuration(groups: list[dict[str, Any]]) -> dict[str, Any]:
    """The methodology that shows a result By campaign: the latest one, with the KPIs that only earlier ones have
    (without points of their own, which every row keeps)."""
    configuration = copy.deepcopy(groups[-1]['configuration'])
    codes = {metric['code'] for metric in configuration['metrics']}
    for group in reversed(groups[:-1]):
        for metric in group['configuration']['metrics']:
            if metric['code'] in codes:
                continue
            extra = copy.deepcopy(metric)
            for context in extra.get('contexts', {}).values():
                context['max_points'] = 0
            configuration['metrics'].append(extra)
            codes.add(metric['code'])
    priority = list(configuration.get('gap_priority') or [])
    configuration['gap_priority'] = [*priority, *(code for group in groups for code in group['configuration'].get(
        'gap_priority') or [] if code not in priority and code in codes)]
    configuration['gap_priority'] = list(dict.fromkeys(configuration['gap_priority']))
    return configuration


def methodology_label(groups: list[dict[str, Any]]) -> str:
    """How a calculation By campaign names its methodologies, such as
    ``By campaign (NetCheck 2026: 2026-Q1, 2026-Q2 · NetCheck 2026-Q3: 2026-Q3)``."""
    parts = [f"{group['profile_name']}: {', '.join(group['campaigns'])}" for group in groups]
    return f"{BY_CAMPAIGN_NAME} ({' · '.join(parts)})"


def _merge_points_loss(documents: list[Any]) -> Any:
    """One Points Lost Map from those of each methodology: the shares of each, on the map areas of all."""
    documents = [document for document in documents if isinstance(document, dict)]
    if not documents:
        return None
    if any(document.get('pending') for document in documents):
        return {'version': 2, 'pending': True}
    merged = copy.deepcopy(documents[0])
    for document in documents[1:]:
        for key, value in document.items():
            if key in ('shares', 'serving_tests'):
                merged.setdefault(key, []).extend(value or [])
            elif isinstance(value, dict) and isinstance(merged.get(key), dict):
                for field, entries in value.items():
                    if isinstance(entries, dict) and isinstance(merged[key].get(field), dict):
                        merged[key][field] = {**entries, **merged[key][field]}
                    else:
                        merged[key].setdefault(field, entries)
            elif isinstance(value, list) and isinstance(merged.get(key), list) and key not in ('shares', 'serving_tests'):
                merged[key] = [*merged[key], *(item for item in value if item not in merged[key])]
            else:
                merged.setdefault(key, value)
    return merged


def _merge_area_summaries(summaries: list[Any]) -> Any:
    """One National & area summary from those of each methodology: each pass with the rows of every campaign."""
    summaries = [summary for summary in summaries if isinstance(summary, dict)]
    if not summaries:
        return None
    merged = copy.deepcopy(summaries[0])
    passes = {(item.get('kind'), str(item.get('field')), tuple(item.get('cities') or [])): item
              for item in merged.get('passes', [])}
    for summary in summaries[1:]:
        for item in summary.get('passes', []):
            key = (item.get('kind'), str(item.get('field')), tuple(item.get('cities') or []))
            target = passes.get(key)
            if target is None:
                merged.setdefault('passes', []).append(copy.deepcopy(item))
                passes[key] = merged['passes'][-1]
                continue
            if item.get('reuses_summary') or target.get('reuses_summary'):
                # (A Geographical calculation read from the merged area summary.)
                continue
            source_result, target_result = item.get('result') or {}, target.setdefault('result', {})
            for field, value in source_result.items():
                if isinstance(value, list):
                    target_result[field] = [*(target_result.get(field) or []), *value]
                else:
                    target_result.setdefault(field, value)
    return merged


def _tag(rows: Any, profile_id: str) -> list[dict[str, Any]]:
    return [{**row, 'methodology': profile_id} for row in rows or [] if isinstance(row, dict)]


def merge_results(parts: list[tuple[dict[str, Any], dict[str, Any]]]) -> dict[str, Any]:
    """One result from the result of each methodology (``(group, result)`` pairs): every row keeps the methodology it
    was scored with."""
    groups = [group for group, _result in parts]
    merged = copy.deepcopy(parts[-1][1])
    for field in _RESULT_LISTS:
        merged[field] = [row for group, result in parts for row in _tag(result.get(field), group['profile_id'])]
    # A warning of the area summary concerns the campaigns of one methodology only.
    from src.modules.column_names import format_campaign
    from src.modules.scoring_area_summary import WARNING_PREFIXES
    # (Its campaigns as the workspace Campaign Maps name them.)
    merged['warnings'] = list(dict.fromkeys(
        (f"{group['profile_name']} ({', '.join(format_campaign(value) or value for value in group['campaigns'])}): {warning}"
         if str(warning).startswith(WARNING_PREFIXES) else warning)
        for group, result in parts for warning in result.get('warnings') or []))
    merged['notices'] = [notice for _group, result in parts for notice in result.get('notices') or []]
    merged['campaigns'] = sorted({campaign for _group, result in parts for campaign in result.get('campaigns') or []},
                                 key=lambda value: (campaign_sort_key(value), value))
    from src.modules.scoring import environment_scaling
    merged['environment_scaling'] = environment_scaling(merged['totals'])
    merged['points_loss'] = _merge_points_loss([result.get('points_loss') for _group, result in parts])
    windows = [result['test_window'] for _group, result in parts if isinstance(result.get('test_window'), dict)]
    if windows:
        merged['test_window'] = {'first': min(window['first'] for window in windows),
                                 'last': max(window['last'] for window in windows),
                                 'days': sum(int(window.get('days') or 0) for window in windows)}
    # The National & Geographical Areas Trends and the Geographical calculations of a job split by no area.
    for key in ('area_summary', 'geographical'):
        if not any(key in result for _group, result in parts):
            continue
        for group, result in parts:
            for item in (result.get(key) or {}).get('passes', []):
                for field, value in (item.get('result') or {}).items():
                    if isinstance(value, list):
                        item['result'][field] = _tag(value, group['profile_id'])
        merged[key] = _merge_area_summaries([result.get(key) for _group, result in parts])
    merged['configuration'] = display_configuration(groups)
    merged['methodology_groups'] = [{key: group[key] for key in ('profile_id', 'profile_name', 'campaigns')}
                                    | {'configuration': group['configuration']} for group in groups]
    return merged


def rows_of(rows: Any, profile_id: str) -> list[dict[str, Any]]:
    """The rows a methodology scored, in a result By campaign."""
    return [row for row in rows or [] if isinstance(row, dict) and row.get('methodology') == profile_id]


def split_result(result: dict[str, Any], group: dict[str, Any]) -> dict[str, Any]:
    """The part of a result By campaign that one methodology scored, with that methodology."""
    part = {**result, 'configuration': group['configuration'], 'methodology_groups': None}
    for field in _RESULT_LISTS:
        part[field] = rows_of(result.get(field), group['profile_id'])
    for key in ('area_summary', 'geographical'):
        summary = result.get(key)
        if isinstance(summary, dict):
            part[key] = {**summary, 'passes': [
                item if item.get('reuses_summary') else
                {**item, 'result': {field: (rows_of(value, group['profile_id']) if isinstance(value, list) else value)
                                    for field, value in (item.get('result') or {}).items()}}
                for item in summary.get('passes') or []]}
    return part
