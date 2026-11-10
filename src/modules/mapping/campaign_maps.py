"""Campaign Maps of a workspace: how every chart, table, legend, filter and report shows campaigns.

The map is stored in the workspace state as JSON: a label format with markers, the
order of the radio modes inside a quarter and exceptions for campaigns that do not
follow the pattern (see ``column_names`` for their meaning). It travels with the
Mappings & Reference Data in Import / Export, transfers and backups.
"""
from __future__ import annotations

import json
from threading import Lock
from typing import Any

from src.modules.cdr.column_names import (
    DEFAULT_CAMPAIGN_MAP, campaign_sort_key, format_campaign, normalize_campaign_map,
)

CAMPAIGN_MAP_STATE_KEY = 'campaign_map'
_cache: dict[str, dict] = {}
_cache_lock = Lock()


def load_campaign_map(repository: Any) -> dict:
    """The workspace's Campaign Map, or the default one."""
    key = str(getattr(repository, 'db_path', ''))
    with _cache_lock:
        if key in _cache:
            return _cache[key]
    try:
        stored = json.loads(repository.get_workspace_state(CAMPAIGN_MAP_STATE_KEY) or 'null')
        config = normalize_campaign_map(stored) if stored else normalize_campaign_map(DEFAULT_CAMPAIGN_MAP)
    except (TypeError, ValueError):
        config = normalize_campaign_map(DEFAULT_CAMPAIGN_MAP)
    with _cache_lock:
        _cache[key] = config
    return config


def invalidate_campaign_maps() -> None:
    with _cache_lock:
        _cache.clear()


def save_campaign_map(repository: Any, config: Any, username: str = '') -> dict:
    """Validate and save the workspace's Campaign Map; None restores the default one."""
    previous = load_campaign_map(repository)
    if config is None:
        repository.set_workspace_state(CAMPAIGN_MAP_STATE_KEY, '')
    else:
        repository.set_workspace_state(CAMPAIGN_MAP_STATE_KEY, json.dumps(normalize_campaign_map(config), ensure_ascii=False))
    invalidate_campaign_maps()
    saved = load_campaign_map(repository)
    if username and hasattr(repository, 'try_add_log'):
        # What the map is now and, for what changed, what it was.
        repository.try_add_log(username, 'campaign_map', json.dumps({
            'restored_default': config is None,
            **{key: saved.get(key) for key in ('format', 'mode_order', 'modes_in_label')},
            'exceptions': [str(item.get('label') or '') for item in saved.get('exceptions') or []],
            'previous': {key: previous.get(key) for key in ('format', 'mode_order', 'modes_in_label', 'exceptions')
                         if previous.get(key) != saved.get(key)},
        }, ensure_ascii=False))
    return saved


def campaign_map_preview(campaigns: list[str], config: dict) -> list[dict[str, Any]]:
    """The workspace campaigns with their label, in the order of the map.

    ``assigned`` is False for a campaign without a year and quarter and without an exception, and
    ``merged`` counts the campaigns that share its label.
    """
    from src.modules.mapping.mapping_assignments import campaign_assignment

    values = list(dict.fromkeys(str(value).strip() for value in campaigns if str(value).strip()))
    items = []
    for value in sorted(values, key=lambda value: campaign_sort_key(value, config)):
        label, assigned = campaign_assignment(value, config)
        items.append({'campaign': value, 'label': label, 'assigned': assigned})
    for item in items:
        item['merged'] = sum(other['label'].casefold() == item['label'].casefold() for other in items) if item['assigned'] else 1
    return items
