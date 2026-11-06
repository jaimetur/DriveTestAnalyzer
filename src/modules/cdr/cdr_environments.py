"""The environment of each CDR test: Cities, Towns, or Roads and railways.

Benchmark CDRs say where each test ran in ``G_Level_1`` (Drive or Walk), ``G_Level_2`` (City, Connecting Roads,
Train Route) and ``G_Level_3`` (Big Cities, Medium Cities, Small Cities, Roads, Highway, Train). They are grouped as
benchmark reports group them: big cities, driven and walked, are Cities; medium and small cities are Towns; connecting
roads, highways and train routes are Roads and railways. A test whose level names none of them has no environment.
"""

from __future__ import annotations

import re

ENVIRONMENTS = ('Cities', 'Towns', 'Roads and railways')
# The CDR columns that describe the environment, the most detailed first: the first non-blank one is used.
ENVIRONMENT_COLUMNS = ('G_Level_3', 'G_Level_2')
_CLASSES = {
    **dict.fromkeys(('bigcities', 'bigcity', 'largecities', 'largecity'), 'Cities'),
    **dict.fromkeys(('mediumcities', 'mediumcity', 'smallcities', 'smallcity', 'towns', 'town'), 'Towns'),
    **dict.fromkeys(('roads', 'road', 'highway', 'highways', 'motorway', 'motorways', 'connectingroads', 'connectingroad',
                     'connectionroad', 'connectionroads', 'train', 'trains', 'trainroute', 'trainroutes', 'rail',
                     'railway', 'railways'), 'Roads and railways'),
}


def environment_class(value: object) -> str:
    """Cities, Towns or Roads and railways for a ``G_Level_3`` or ``G_Level_2`` value, else ''."""
    return _CLASSES.get(re.sub(r'[^a-z0-9]+', '', str(value or '').casefold()), '')


def environment_order(value: object) -> int:
    """Position of an environment in :data:`ENVIRONMENTS`; values without one come last."""
    return ENVIRONMENTS.index(value) if value in ENVIRONMENTS else len(ENVIRONMENTS)
