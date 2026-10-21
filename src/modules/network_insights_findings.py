"""Key Findings of Network Insights: six benchmark views of the CDR Data tests, each with its headline.

Every view compares the groups of the analysis (the Operators, or the grouping chosen without the environment) on one
value per Data test, as benchmark reports do: the LTE and 5G signal at the test per environment, the spread of the total
bandwidth of the downloads and their share under 40 MHz, how often 5G was used (drive and walk apart), the main 4G band
and 5G on 3.5 GHz, and the primary bandwidth ladder. Each one carries a headline written from its figures, what it means,
its basis and a footnote; the page and the PowerPoint and Word exports draw them in the colours of the chosen theme.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from src.modules.cdr_environments import environment_order

ALL_ENVIRONMENTS = 'All environments'
# A group needs this many tests in a view for its headline to name it.
MIN_FINDING_TESTS = 10
# The signal classes of benchmark reports, worst first (the theme gives them its five-step scale).
LTE_RSRP_CLASSES = (('< −110', -110.0), ('−110 to −100', -100.0), ('−100 to −90', -90.0), ('−90 to −80', -80.0), ('≥ −80', None))
SINR_CLASSES = (('≤ 0', 0.0), ('0 to 5', 5.0), ('5 to 10', 10.0), ('10 to 15', 15.0), ('> 15', None))
# RSRP below this is weak signal in the headlines (the two worst classes).
WEAK_RSRP_DBM = -100.0
NARROW_DOWNLOAD_MHZ = 40.0
WIDE_DOWNLOAD_MHZ = 100.0
# The main 4G band of a test (its LTE PCell) in the classes of benchmark reports.
LTE_BAND_GROUPS = (
    ('2600 MHz', {'B7'}), ('2600 MHz TDD', {'B38', 'B41'}), ('2100 MHz', {'B1'}), ('1800 MHz', {'B3'}),
    ('2300 MHz', {'B40'}), ('700–900 MHz', {'B8', 'B20', 'B28'}),
)
OTHER_BAND = 'Other'
MID_BAND_NR = {'n77', 'n78'}
NUMBER_WORDS = ('zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten', 'eleven', 'twelve')
VIEW_TITLES = {
    'lte_signal': 'LTE signal at the test: RSRP and SINR',
    'nr_signal': '5G signal at the test: RSRP and quality (SINR)',
    'bandwidth_spread': 'Primary bandwidth: spread and narrow tests',
    'technology': 'Technology in use',
    'bands': 'Bands in use',
    'total_bandwidth': 'Primary bandwidth',
}


def mode_of_test(value: object) -> str:
    """Drive or Walk from the route level of a test (G_Level_1); other values as they are."""
    text = str(value or '').strip()
    folded = text.casefold()
    if 'walk' in folded:
        return 'Walk'
    if 'drive' in folded:
        return 'Drive'
    return text[:1].upper() + text[1:] if text else ''


def mode_order(value: str) -> tuple[int, str]:
    return ({'Drive': 0, 'Walk': 1}.get(value, 2), value.casefold())


def _words(count: int) -> str:
    return NUMBER_WORDS[count] if 0 <= count < len(NUMBER_WORDS) else str(count)


def _join(items: list[str]) -> str:
    items = [item for item in items if item]
    return items[0] if len(items) == 1 else ', '.join(items[:-1]) + ' and ' + items[-1] if items else ''


def _possessive(name: str) -> str:
    return f"{name}'" if name.endswith('s') else f"{name}'s"


def _percent(value: float | None, digits: int = 0) -> str:
    if value is None:
        return '–'
    text = f'{value:.{digits}f}'
    return f'{text}%'


def _round(value: Any, digits: int = 1) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if np.isnan(number) else round(number, digits)


def _number(value: Any, digits: int = 1) -> str:
    """A value with a true minus sign (−93.7)."""
    number = _round(value, digits)
    return '–' if number is None else f'{number:g}'.replace('-', '−')


def _environment_phrase(environment: str) -> str:
    folded = environment.casefold()
    if environment == ALL_ENVIRONMENTS:
        return 'overall'
    return f'on {folded}' if 'road' in folded or 'rail' in folded else f'in {folded}'


def _class_shares(values: pd.Series, classes: tuple[tuple[str, float | None], ...]) -> list[float]:
    """The share (%) of the values in each class, worst first: a value belongs to the first class whose upper bound it
    is below (or, for SINR, at or below)."""
    known = values.dropna().to_numpy(dtype=float)
    if not len(known):
        return [0.0] * len(classes)
    remaining = np.ones(len(known), dtype=bool)
    shares = []
    for index, (_label, upper) in enumerate(classes):
        if upper is None:
            inside = remaining
        else:
            inside = remaining & ((known <= upper) if classes is SINR_CLASSES else (known < upper))
        shares.append(round(float(inside.sum()) / len(known) * 100, 1))
        remaining = remaining & ~inside
    return shares


def _environments(tests: pd.DataFrame) -> tuple[list[str], pd.Series]:
    values = tests['environment'].fillna('').astype(str) if 'environment' in tests else pd.Series('', index=tests.index)
    rows = sorted({value for value in values if value}, key=environment_order)
    if not rows:
        return [ALL_ENVIRONMENTS], pd.Series(ALL_ENVIRONMENTS, index=tests.index)
    return rows, values


def _modes(tests: pd.DataFrame) -> tuple[list[str], pd.Series]:
    values = tests['mode'].fillna('').astype(str) if 'mode' in tests else pd.Series('', index=tests.index)
    modes = sorted({value for value in values if value}, key=mode_order)
    return modes, values


def tag_text(modes: list[str]) -> str:
    """The pill of a view: the CDR type and the test modes it covers (Data · drive and walk)."""
    return 'Data' + (f' · {_join([mode.lower() for mode in modes])}' if modes else '')


def _signal_view(tests: pd.DataFrame, groups: pd.Series, order: list[str], radio: str) -> dict[str, Any] | None:
    rsrp_field, sinr_field = f'{radio}_rsrp', f'{radio}_sinr'
    frame = pd.DataFrame({'group': groups.loc[tests.index].to_numpy(), 'rsrp': tests[rsrp_field].to_numpy(dtype=float),
                          'sinr': tests[sinr_field].to_numpy(dtype=float)}, index=tests.index)
    all_tests = frame['group'].value_counts()
    frame = frame.loc[frame[['rsrp', 'sinr']].notna().any(axis=1)]
    if frame.empty:
        return None
    label = 'LTE' if radio == 'lte' else '5G'
    environments, values = _environments(tests.loc[frame.index])
    frame['environment'] = values.to_numpy()
    by_cell = {key: part for key, part in frame.groupby(['group', 'environment'], sort=False)}
    by_group = {key: part for key, part in frame.groupby('group', sort=False)}
    tested = 'data tests' if radio == 'lte' else 'tests with 5G'
    panels = []
    for metric, classes, title in (
        ('rsrp', LTE_RSRP_CLASSES, f'{label} RSRP (dBm), % of {tested}'),
        ('sinr', SINR_CLASSES, f'{label} SINR (dB), % of {tested}' if radio == 'lte' else f'5G quality (SINR, dB), % of {tested}'),
    ):
        blocks = []
        for environment in environments:
            rows = []
            for group in order:
                part = by_cell.get((group, environment))
                values_of = part[metric].dropna() if part is not None else ()
                if len(values_of):
                    rows.append({'group': group, 'tests': int(len(values_of)), 'shares': _class_shares(values_of, classes),
                                 'median': _round(values_of.median())})
            if rows:
                blocks.append({'environment': environment, 'rows': rows})
        panels.append({'title': title, 'classes': [name for name, _upper in classes], 'environments': blocks})
    # The headline compares the medians of the groups with enough tests, overall and in each environment.
    statistics = {}
    for group in order:
        part = by_group.get(group)
        if part is None or len(part) < MIN_FINDING_TESTS:
            continue
        rsrp, sinr = part['rsrp'].dropna(), part['sinr'].dropna()
        weak = {}
        for environment in environments:
            cell = by_cell.get((group, environment))
            cell_rsrp = cell['rsrp'].dropna() if cell is not None else ()
            weak[environment] = float((cell_rsrp < WEAK_RSRP_DBM).mean()) * 100 if len(cell_rsrp) else None
        statistics[group] = {'rsrp': rsrp.median() if len(rsrp) else None, 'sinr': sinr.median() if len(sinr) else None,
                             'weak': weak, 'share': float(len(part)) / max(1, int(all_tests.get(group, 0))) * 100}

    def extreme(metric: str, highest: bool) -> tuple[str | None, bool]:
        """The group with the lowest (or highest) median, and whether it is so in every environment."""
        known = {group: figures[metric] for group, figures in statistics.items() if figures[metric] is not None}
        if len(known) < 2:
            return next(iter(known), None), False
        pick = max if highest else min
        chosen = pick(known, key=known.get)
        everywhere = len(environments) > 1
        for environment in environments:
            medians = {}
            for group in known:
                cell = by_cell.get((group, environment))
                cell_values = cell[metric].dropna() if cell is not None else ()
                if len(cell_values) >= MIN_FINDING_TESTS:
                    medians[group] = cell_values.median()
            if len(medians) < 2 or chosen not in medians or pick(medians, key=medians.get) != chosen:
                everywhere = False
        return chosen, everywhere

    count = _words(len(statistics))
    weakest, weakest_everywhere = extreme('rsrp', False)
    lowest_sinr, sinr_everywhere = extreme('sinr', False)
    best_sinr, best_everywhere = extreme('sinr', True)
    every = ' in every environment'
    if len(statistics) < 2:
        group = next(iter(statistics), order[0] if order else '')
        figures = statistics.get(group, {})
        headline = (f"{_possessive(group)} median {label} RSRP was {_number(figures.get('rsrp'))} dBm and its median SINR "
                    f"{_number(figures.get('sinr'))} dB") if figures else f'{label} signal at the test'
    elif radio == 'lte':
        # A group is named only for the values its tests have (a CDR may log RSRP without SINR).
        parts = []
        if weakest:
            parts.append(f"{_possessive(weakest)} LTE signal is the weakest of the {count}{every if weakest_everywhere else ''}")
        if lowest_sinr:
            parts.append(f"its LTE SINR is the lowest{every if sinr_everywhere else ''}" if lowest_sinr == weakest
                         else f"{_possessive(lowest_sinr)} LTE SINR is the lowest{every if sinr_everywhere else ''}")
        headline = '; '.join(parts) or f'{label} signal at the test'
    else:
        parts = []
        if best_sinr:
            parts.append(f"{_possessive(best_sinr)} 5G quality is the best of the {count}{every if best_everywhere else ''}")
        if weakest:
            parts.append(f"yet its 5G signal is the weakest{every if weakest_everywhere else ''}" if weakest == best_sinr
                         else f"{_possessive(weakest)} 5G signal is the weakest{every if weakest_everywhere else ''}")
        headline = '; '.join(parts) or f'{label} signal at the test'
        headline = headline[:1].upper() + headline[1:]
    meaning = ''
    if radio == 'lte' and weakest and statistics.get(weakest):
        parts = [f'{_environment_phrase(environment)} {_percent(share)}'
                 for environment, share in statistics[weakest]['weak'].items() if share is not None]
        if parts:
            meaning = f"{_join(parts)} of {_possessive(weakest)} tests ran below −100 dBm on LTE."
    elif radio == 'nr' and len(statistics) > 1:
        parts = []
        if best_sinr:
            parts.append(f"{_possessive(best_sinr)} 5G is the cleanest (median SINR {_number(statistics[best_sinr]['sinr'])} dB)")
        if weakest and weakest != best_sinr:
            parts.append(f"{_possessive(weakest)} 5G is the weakest (median RSRP {_number(statistics[weakest]['rsrp'])} dBm)")
        shares = [f"{group} {_percent(figures['share'])}" for group, figures in statistics.items()]
        meaning = ' and '.join(parts) + ('; ' if parts else '') + f"5G was logged in {_join(shares)} of the Data tests."
    field_names = 'LTE PCell RSRP Avg, LTE PCell SINR Avg' if radio == 'lte' else 'NR PCell RSRP Avg, NR PCell SINR Avg'
    basis = (f"one value per test, the test average on the primary {label} {'carrier' if radio == 'lte' else 'cell'} "
             f"({field_names}); not the individual samples.")
    footnote = (f"Data tests with {'an LTE' if radio == 'lte' else 'a 5G'} value: {len(frame):,} of {len(tests):,}; "
                'claims checked in each environment.')
    return {'kind': 'signal', 'panels': panels, 'headline': headline, 'meaning': meaning, 'basis': basis,
            'footnote': footnote, 'tests': int(len(frame))}


def _downloads(tests: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    """The download tests, else every Data test, and the word that names them."""
    downloads = tests.loc[tests['download'].astype(bool)] if 'download' in tests else tests.iloc[0:0]
    return (downloads, 'downloads') if len(downloads) else (tests, 'tests')


def _spread_view(tests: pd.DataFrame, groups: pd.Series, order: list[str]) -> dict[str, Any] | None:
    from src.modules.network_insights import total_bandwidth

    downloads, noun = _downloads(tests)
    totals = total_bandwidth(downloads)
    known = totals.dropna()
    if known.empty:
        return None
    spread, narrow = [], []
    for group in order:
        part = known.loc[groups.loc[known.index] == group]
        if not len(part):
            continue
        spread.append({'group': group, 'tests': int(len(part)), 'p10': _round(part.quantile(.1), 0),
                       'median': _round(part.median(), 0), 'p90': _round(part.quantile(.9), 0)})
        narrow.append({'group': group, 'tests': int(len(part)),
                       'share': _round(float((part < NARROW_DOWNLOAD_MHZ).mean()) * 100, 1)})
    # The rank of each share among the groups: green the fewest, red the most.
    ranked = sorted((row for row in narrow if row['tests'] >= MIN_FINDING_TESTS), key=lambda row: row['share'])
    for position, row in enumerate(ranked):
        row['rank'] = position / (len(ranked) - 1) if len(ranked) > 1 else 0.0
    eligible = [row for row in spread if row['tests'] >= MIN_FINDING_TESTS] or spread
    widest = sorted(eligible, key=lambda row: -(row['median'] or 0))
    fewest = ranked[0] if ranked else None
    top = widest[0]
    narrow_of = {row['group']: row['share'] for row in narrow}
    headline = f"{_possessive(top['group'])} median {noun[:-1]} had {top['median']:g} MHz of primary bandwidth"
    if len(widest) > 1:
        headline += f" ({widest[1]['group']} {widest[1]['median']:g})"
    if fewest is not None and fewest['group'] == top['group'] and len(ranked) > 1:
        headline += f"; {_percent(narrow_of[top['group']], 1)} under {NARROW_DOWNLOAD_MHZ:g} MHz, the fewest"
    elif fewest is not None and len(ranked) > 1:
        headline += f"; {fewest['group']} had the fewest under {NARROW_DOWNLOAD_MHZ:g} MHz ({_percent(fewest['share'], 1)})"
    else:
        headline += f"; {_percent(narrow_of[top['group']], 1)} under {NARROW_DOWNLOAD_MHZ:g} MHz"
    meaning = ''
    if fewest is not None and len(ranked) > 1:
        if fewest['share'] > 15:
            meaning = (f"narrow bandwidth is common: even {fewest['group']} ran {_percent(fewest['share'], 1)} of its "
                       f'{noun} under {NARROW_DOWNLOAD_MHZ:g} MHz.')
        else:
            meaning = f"narrow bandwidth is rare on {_possessive(fewest['group'])} {noun}, rarer than on {_possessive(ranked[1]['group'])}."
    unknown = int(totals.isna().sum())
    return {
        'kind': 'spread', 'headline': headline, 'meaning': meaning,
        'panels': [
            {'title': 'Primary bandwidth, 4G and 5G together, MHz (wider is better)', 'rows': spread,
             'note': 'Left number: P10; above the mark: the median; right: P90 (narrowest to widest tenth).'},
            {'title': f'{noun.title()} under {NARROW_DOWNLOAD_MHZ:g} MHz, % (lower is better)', 'rows': narrow,
             'note': f'Colour: the fewest of the {_words(len(ranked))} in the best colour of the scale, the most in the worst.'
             if len(ranked) > 1 else ''},
        ],
        'basis': 'the primary downlink bandwidth of each test: LTE as the mean width of its aggregated carriers, 5G as the '
                 'width of its primary cell, added up (the CDRs do not report the 5G secondary carriers, so 5G carrier '
                 'aggregation is not included).',
        'footnote': f'{len(known):,} {noun} with a known width' + (f' ({unknown:,} left out).' if unknown else '.'),
        'tests': int(len(known)),
    }


def _uses_nr(tests: pd.DataFrame) -> pd.Series:
    """Whether 5G served a test at some moment: NR time over zero, or an NR value or band logged."""
    used = pd.Series(False, index=tests.index)
    if 'nr_time' in tests:
        used |= pd.to_numeric(tests['nr_time'], errors='coerce').fillna(0) > 0
    for field in ('nr_rsrp', 'nr_sinr'):
        if field in tests:
            used |= tests[field].notna()
    if 'nr_band' in tests:
        used |= tests['nr_band'].fillna('').astype(str) != ''
    return used


def _nr_time_share(tests: pd.DataFrame) -> pd.Series:
    """The share (0–1) of the time of each test on 5G, where the CDR reports the NR time and the test duration."""
    if 'nr_time' not in tests or 'test_duration' not in tests:
        return pd.Series(np.nan, index=tests.index)
    time = pd.to_numeric(tests['nr_time'], errors='coerce')
    duration = pd.to_numeric(tests['test_duration'], errors='coerce')
    return (time.fillna(0) / duration).where(duration > 0).clip(0, 1)


def _technology_view(tests: pd.DataFrame, groups: pd.Series, order: list[str]) -> dict[str, Any] | None:
    if tests.empty:
        return None
    modes, values = _modes(tests)
    used = _uses_nr(tests)
    time_share = _nr_time_share(tests)
    panels = []
    figures: dict[str, dict[str, dict[str, float]]] = {}
    for mode in modes or ['']:
        in_mode = values == mode if mode else pd.Series(True, index=tests.index)
        rows = []
        for group in order:
            mask = in_mode & (groups.loc[tests.index] == group)
            count = int(mask.sum())
            if not count:
                continue
            nr_share = float(used.loc[mask].mean()) * 100
            share_time = time_share.loc[mask].dropna()
            rows.append({'group': group, 'tests': count, 'shares': [round(nr_share, 1), round(100 - nr_share, 1)],
                         'time_share': _round(share_time.mean() * 100, 0) if len(share_time) else None})
            if count >= MIN_FINDING_TESTS:
                figures.setdefault(group, {})[mode] = {'nr': nr_share, 'lte': 100 - nr_share,
                                                       'time': share_time.mean() * 100 if len(share_time) else None,
                                                       'tests': count}
        if rows:
            panels.append({'title': f'{mode} data tests, %' if mode else 'Data tests, %', 'mode': mode, 'rows': rows})
    if not panels:
        return None
    first = modes[0] if modes else ''
    named = {group: modes_of[first] for group, modes_of in figures.items() if first in modes_of}
    word = f' {first.lower()}' if first else ''
    headline, meaning, reading = 'How often the tests used 5G', '', []
    if named:
        rare = [group for group, values_of in named.items() if values_of['lte'] <= 6]
        others = sorted((group for group in named if group not in rare), key=lambda group: named[group]['lte'])
        if rare and others:
            shares = [named[group]['lte'] for group in others]
            if max(shares) - min(shares) <= 5:
                headline = (f'{_join(rare)} rarely run on 4G alone; {_join(others)} about one{word} test in '
                            f'{max(2, round(100 / (sum(shares) / len(shares))))}')
            else:
                headline = (f"{_join(rare)} rarely run on 4G alone; {_join(others)} on "
                            f"{_join([_percent(share) for share in shares])} of{word} tests")
        elif rare:
            headline = f'{_join(rare)} rarely run on 4G alone: 5G served almost every{word} test'
        else:
            most = max(named, key=lambda group: named[group]['lte'])
            least = min(named, key=lambda group: named[group]['lte'])
            headline = (f"{most} runs on 4G alone most often ({_percent(named[most]['lte'])} of{word} tests); "
                        f"{least} least ({_percent(named[least]['lte'])})")
        ranked = sorted(named, key=lambda group: -named[group]['nr'])
        leader = ranked[0]
        if len(ranked) > 1:
            gap = named[leader]['nr'] - named[ranked[1]]['nr']
            meaning = (f"on how often 5G is used, {leader} is level with {ranked[1]}." if gap <= 1
                       else f"on how often 5G is used, {leader} leads ({_percent(named[leader]['nr'])}), ahead of "
                            f"{ranked[1]} ({_percent(named[ranked[1]]['nr'])}).")
        per_mode = [f"{_percent(values_of['nr'])} of {mode.lower() + ' ' if mode else ''}tests"
                    for mode, values_of in sorted(figures[leader].items(), key=lambda item: mode_order(item[0]))]
        text = f"{_join(per_mode)} used 5G at some point"
        if named[leader]['time'] is not None:
            text += f"; on average {_percent(named[leader]['time'])} of each{word} test's time was on 5G"
        reading.append({'lead': f'{leader}:', 'text': text + '.'})
        lagging = [group for group in sorted(named, key=lambda group: -named[group]['lte']) if named[group]['lte'] > 6][:2]
        if lagging:
            reading.append({'lead': _join(lagging), 'text': f"ran {_join([_percent(named[group]['lte']) for group in lagging])} "
                                                             f"of{word} tests on 4G alone."})
    counts = ', '.join(f"{panel['mode'].lower() if panel['mode'] else 'all'} {sum(row['tests'] for row in panel['rows']):,}"
                       for panel in panels)
    return {
        'kind': 'technology', 'classes': ['5G at some point', '4G only'], 'panels': panels,
        'headline': headline, 'meaning': meaning, 'reading': {'title': 'Reading it', 'lines': reading},
        'basis': '',
        'footnote': f'Data tests: {counts}. 5G at some point: a 5G leg at any moment of the test (NR time over zero, or an '
                    'NR value logged).',
        'tests': int(len(tests)),
    }


def lte_band_group(band: object) -> str:
    text = str(band or '').strip()
    if not text:
        return ''
    return next((label for label, bands in LTE_BAND_GROUPS if text in bands), OTHER_BAND)


def _bands_view(tests: pd.DataFrame, groups: pd.Series, order: list[str]) -> dict[str, Any] | None:
    downloads, noun = _downloads(tests)
    if downloads.empty:
        return None
    modes, values = _modes(downloads)
    band_groups = downloads['lte_band'].map(lte_band_group) if 'lte_band' in downloads else pd.Series('', index=downloads.index)
    known = band_groups != ''
    classes = [label for label, _bands in LTE_BAND_GROUPS] + [OTHER_BAND]
    panels = []
    leaders: dict[str, str] = {}
    for mode in modes or ['']:
        in_mode = (values == mode) if mode else pd.Series(True, index=downloads.index)
        rows = []
        for group in order:
            mask = in_mode & known & (groups.loc[downloads.index] == group)
            count = int(mask.sum())
            if not count:
                continue
            counts = band_groups.loc[mask].value_counts()
            rows.append({'group': group, 'tests': count,
                         'shares': [round(float(counts.get(label, 0)) / count * 100, 1) for label in classes]})
        if rows:
            panels.append({'title': f'{mode}: main 4G band, %' if mode else 'Main 4G band, %', 'mode': mode, 'rows': rows})
    if not panels:
        return None
    # The band most tests used, and the group that used it most.
    overall = band_groups.loc[known].value_counts()
    main_band = next((label for label in overall.index if label != OTHER_BAND), overall.index[0])
    main_index = classes.index(main_band)
    first = panels[0]
    eligible = [row for row in first['rows'] if row['tests'] >= MIN_FINDING_TESTS] or first['rows']
    leader = max(eligible, key=lambda row: row['shares'][main_index])
    for panel in panels:
        candidates = [row for row in panel['rows'] if row['tests'] >= MIN_FINDING_TESTS]
        if candidates:
            leaders[panel['mode']] = max(candidates, key=lambda row: row['shares'][main_index])['group']
    headline = f"4G mostly on {main_band}, the most on {_possessive(leader['group'])} {noun} ({_percent(leader['shares'][main_index])})"
    # The main 5G carrier on 3.5 GHz among the downloads with 5G.
    nr_bands = downloads['nr_band'].fillna('').astype(str) if 'nr_band' in downloads else pd.Series('', index=downloads.index)
    with_nr = nr_bands != ''
    side_lines = []
    mid_shares: list[float] = []
    for mode in modes or ['']:
        in_mode = (values == mode) if mode else pd.Series(True, index=downloads.index)
        parts = []
        for group in order:
            mask = in_mode & with_nr & (groups.loc[downloads.index] == group)
            if int(mask.sum()) >= MIN_FINDING_TESTS:
                share = float(nr_bands.loc[mask].isin(MID_BAND_NR).mean()) * 100
                parts.append(f'{group} {_percent(share, 1)}')
                if mode == (modes[0] if modes else ''):
                    mid_shares.append(share)
        if parts:
            lead = (f"Main 5G carrier on 3.5 GHz, share of {mode.lower() + ' ' if mode else ''}{noun} with 5G:"
                    if not side_lines else f'{mode}:')
            side_lines.append({'lead': lead, 'text': ', '.join(parts) + '.'})
    tdd = downloads.loc[band_groups == '2600 MHz TDD']
    if len(tdd):
        users = groups.loc[tdd.index].value_counts()
        top = users.index[0]
        share = float(len(tdd.loc[groups.loc[tdd.index] == top])) / max(1, int((groups.loc[downloads.index] == top).sum())) * 100
        side_lines.append({'lead': '2600 MHz TDD:', 'text': f"{_percent(share, 1)} of {_possessive(top)} {noun}."})
    if mid_shares:
        low, high = min(mid_shares), max(mid_shares)
        mode_word = f'{modes[0].lower()} ' if modes else ''
        headline += (f'; 5G on 3.5 GHz in {low:.1f}–{_percent(high, 1)} of the {mode_word}{noun} with 5G' if high - low >= 0.5
                     else f'; 5G on 3.5 GHz in {_percent(high, 1)} of the {mode_word}{noun} with 5G')
    same_leader = len(set(leaders.values())) == 1 and len(leaders) > 1
    meaning = (f"{_possessive(leader['group'])} 4G rests on {main_band} more than any rival's"
               + (f", on {_join([mode.lower() for mode in leaders])}." if same_leader else '.'))
    unknown = int((~known).sum())
    return {
        'kind': 'bands', 'classes': classes, 'panels': panels, 'headline': headline, 'meaning': meaning,
        'side': {'title': '5G on 3.5 GHz', 'lines': side_lines} if side_lines else None,
        'basis': '',
        'footnote': (f'{noun.title()}: the main 4G band is the carrier of the LTE PCell of the test'
                     + (f'; {unknown:,} without a logged 4G band left out (5G SA among them).' if unknown else '.')),
        'tests': int(known.sum()),
    }


def _ladder_view(tests: pd.DataFrame, groups: pd.Series, order: list[str]) -> dict[str, Any] | None:
    from src.modules.network_insights import BANDWIDTH_CLASSES, bandwidth_classes, total_bandwidth

    downloads, noun = _downloads(tests)
    totals = total_bandwidth(downloads)
    known = totals.dropna()
    if known.empty:
        return None
    positions = bandwidth_classes(totals)
    columns = []
    for group in order:
        part = known.loc[groups.loc[known.index] == group]
        if not len(part):
            continue
        counts = np.bincount(positions.loc[part.index].to_numpy(dtype=int), minlength=len(BANDWIDTH_CLASSES))
        columns.append({'group': group, 'tests': int(len(part)),
                        'shares': [round(int(count) / len(part) * 100, 1) for count in counts],
                        'wide_share': _round(float((part >= WIDE_DOWNLOAD_MHZ).mean()) * 100, 0)})
    eligible = [column for column in columns if column['tests'] >= MIN_FINDING_TESTS] or columns
    leader = max(eligible, key=lambda column: column['wide_share'] or 0)
    count = _words(len(eligible))
    headline = (f"{_percent(leader['wide_share'])} of {_possessive(leader['group'])} {noun} had {WIDE_DOWNLOAD_MHZ:g} MHz or more "
                f"of primary bandwidth (4G and 5G)" + (f', the most of the {count}' if len(eligible) > 1 else ''))
    modes, values = _modes(downloads)
    mode_leaders = set()
    for mode in modes:
        shares = {}
        for group in order:
            part = known.loc[(groups.loc[known.index] == group) & (values.loc[known.index] == mode)]
            if len(part) >= MIN_FINDING_TESTS:
                shares[group] = float((part >= WIDE_DOWNLOAD_MHZ).mean())
        if shares:
            mode_leaders.add(max(shares, key=shares.get))
    meaning = ''
    if len(eligible) > 1:
        runner_up = sorted(eligible, key=lambda column: -(column['wide_share'] or 0))[1]
        gap = (leader['wide_share'] or 0) - (runner_up['wide_share'] or 0)
        meaning = (f"{leader['group']} leads {runner_up['group']} by {gap:g} points at {WIDE_DOWNLOAD_MHZ:g} MHz or more"
                   + (f", on {_join([mode.lower() for mode in modes])}" if len(modes) > 1 and mode_leaders == {leader['group']} else ''))
        # The narrowest class (under 25 MHz): the group whose tests fall in it most often.
        narrowest = max(eligible, key=lambda column: column['shares'][-1])
        if narrowest['shares'][-1] >= 1:
            meaning += (f"; {_possessive(narrowest['group'])} {noun} fall under {BANDWIDTH_CLASSES[-1][2]:g} MHz most often "
                        f"({_percent(narrowest['shares'][-1], 1)})")
        meaning += '.'
    return {
        'kind': 'ladder', 'classes': [{'label': label, 'width': width} for label, _lower, _upper, _colour, width in BANDWIDTH_CLASSES],
        'columns': columns, 'headline': headline, 'meaning': meaning, 'note': 'Bar width grows with the bandwidth.',
        'basis': '',
        'footnote': (f'{noun.title()}: primary bandwidth, the 4G carriers of each test (aggregated) plus its 5G primary cell; '
                     'the CDRs do not report the 5G secondary carriers'
                     + (f'; {int(totals.isna().sum()):,} of {len(totals):,} without a known width left out.'
                        if totals.isna().any() else '.')),
        'tests': int(len(known)),
    }


def findings_payload(samples: pd.DataFrame, groups: pd.Series, order: list[str], colours: dict[str, str]) -> dict[str, Any]:
    """The Key Findings of the CDR Data tests of ``samples``: ``groups`` names the group of each sample (the columns of
    the views), in ``order``; ``colours`` the colour of each group."""
    data = samples['kind'].eq('Data') if 'kind' in samples else pd.Series(False, index=samples.index)
    tests = samples.loc[data]
    present = [group for group in order if (groups.loc[tests.index] == group).any()]
    views = []
    if not tests.empty:
        builders = (
            ('lte_signal', lambda: _signal_view(tests, groups, present, 'lte')),
            ('nr_signal', lambda: _signal_view(tests, groups, present, 'nr')),
            ('bandwidth_spread', lambda: _spread_view(tests, groups, present)),
            ('technology', lambda: _technology_view(tests, groups, present)),
            ('bands', lambda: _bands_view(tests, groups, present)),
            ('total_bandwidth', lambda: _ladder_view(tests, groups, present)),
        )
        for key, build in builders:
            view = build()
            if view is None:
                continue
            scope = _downloads(tests)[0] if key in {'bandwidth_spread', 'bands', 'total_bandwidth'} else tests
            views.append({'key': key, 'title': VIEW_TITLES[key], 'tag': tag_text(_modes(scope)[0]), **view})
    return {'groups': present, 'colours': {group: colours.get(group, '') for group in present}, 'views': views,
            'tests': int(len(tests))}
