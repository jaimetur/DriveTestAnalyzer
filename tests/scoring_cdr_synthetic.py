"""Synthetic NetCheck CDR rows (Data, Voice and Speech) for the scoring views, exports and Points Lost.

Four operators are measured in eight cities and on four Connecting Roads routes over three campaigns, each test with its
start position and time and the Vendor, network, host network, eMOCN scenario and site of the cell that served it. A few
sites fail many tests and the operators differ in strength, so every view has something to show.
"""
from __future__ import annotations

import random
import zlib
from datetime import datetime, timedelta

import pandas as pd

OPERATORS = {'Vodafone UK': .965, 'Three UK': .945, 'EE': .985, 'O2 UK': .955}
CITIES = {
    'London': (51.507, -0.128), 'Birmingham': (52.486, -1.890), 'Manchester': (53.480, -2.242),
    'Leeds': (53.800, -1.549), 'Glasgow': (55.864, -4.252), 'Bristol': (51.454, -2.588),
    'Cardiff': (51.481, -3.179), 'Edinburgh': (55.953, -3.188),
}
ROUTES = {'London to Birmingham': ('London', 'Birmingham'), 'Manchester to Leeds': ('Manchester', 'Leeds'),
          'Glasgow to Edinburgh': ('Glasgow', 'Edinburgh'), 'Bristol to Cardiff': ('Bristol', 'Cardiff')}
CAMPAIGNS = {'2026-Q1': datetime(2026, 2, 9), '2026-Q2': datetime(2026, 5, 11), '2026-Q3': datetime(2026, 8, 3)}
NETWORKS = {'Vodafone UK': 'Vodafone', 'Three UK': 'H3G', 'EE': 'EE', 'O2 UK': 'Telefonica'}
SOUTH = {'London', 'Bristol', 'Cardiff', 'London to Birmingham', 'Bristol to Cardiff'}
# The RAN Vendor of the sites of each network in the south and in the north.
VENDORS = {'Vodafone': ('Ericsson', 'Nokia'), 'H3G': ('Ericsson', 'Samsung'), 'EE': ('Nokia', 'Nokia'),
           'Telefonica': ('Ericsson', 'Nokia')}
# Sites that fail many tests: (operator, place, site index) → the chance that a test served there fails.
BAD_SITES = {('Vodafone UK', 'Leeds', 3): .45, ('Vodafone UK', 'Manchester to Leeds', 2): .35,
             ('Three UK', 'Glasgow', 1): .5, ('Three UK', 'Glasgow to Edinburgh', 4): .4,
             ('O2 UK', 'Birmingham', 5): .4, ('Three UK', 'London', 7): .3}
DATA_TESTS = (('FDFS HTTP DL ST', 'FDFS'), ('FDFS HTTP UL ST', 'FDFS'), ('FDTT HTTP DL MT', 'FDTT'),
              ('UDP UL 7s', 'UDP'), ('Browsing', 'httpBrowser'), ('YouTube', 'VideoStreaming'),
              ('Gaming', 'Interactivity'))
CALL_TYPES = ('CALL', 'CALL', 'MultiRAB CALL', 'WhatsApp CALL')


def _places() -> list[tuple[str, str, float, float, int]]:
    """(place, G_Level_2, latitude, longitude, stretch index) of every test position."""
    positions = []
    for city, (latitude, longitude) in CITIES.items():
        positions.extend((city, 'City', latitude, longitude, 0) for _ in range(6))
    for route, (start, end) in ROUTES.items():
        (lat_a, lon_a), (lat_b, lon_b) = CITIES[start], CITIES[end]
        steps = 10
        for step in range(1, steps):
            share = step / steps
            positions.append((route, 'Connecting Roads', lat_a + (lat_b - lat_a) * share,
                              lon_a + (lon_b - lon_a) * share, step))
    return positions


def _serving(operator: str, place: str, generator: random.Random, stretch: int) -> dict:
    network = NETWORKS[operator]
    # Three is served by Vodafone cells on part of its tests (eMOCN), Vodafone by Telefonica cells (Beacon).
    serving_network = 'Vodafone' if operator == 'Three UK' and generator.random() < .2 else network
    host = 'Telefonica' if serving_network == 'Vodafone' and generator.random() < .22 else serving_network
    south, north = VENDORS[host]
    index = (stretch or generator.randint(1, 8)) if place in ROUTES else generator.randint(1, 8)
    return {
        'Vendor': south if place in SOUTH else north,
        'Serving_Network': serving_network, 'Serving_Host_Network': host,
        'Serving_eMOCN_Scenario': 'NNS' if serving_network != network else ('S1' if host != serving_network else ''),
        'Serving_Site_ID': f'{zlib.crc32(place.encode()) % 900 + 100}{index:02d}', '_site_index': index,
    }


def _failure_chance(operator: str, place: str, campaign_index: int, site_index: int) -> float:
    chance = (1 - OPERATORS[operator]) * (1.4 if place in ROUTES else 1.0) - campaign_index * .004
    bad = BAD_SITES.get((operator, place, site_index))
    if bad is not None and (campaign_index > 0 or site_index % 2):
        chance = bad
    return max(.0, chance)


def synthetic_cdr_frames(seed: int = 11, campaigns: tuple[str, ...] = tuple(CAMPAIGNS),
                         operators: tuple[str, ...] = tuple(OPERATORS), repeats: int = 2) -> dict[str, pd.DataFrame]:
    """CDR Data, Voice and Speech rows of every campaign, operator, city and route."""
    generator = random.Random(seed)
    data, voice, speech = [], [], []
    positions = _places()
    for campaign_index, campaign in enumerate(campaigns):
        start = CAMPAIGNS.get(campaign, datetime(2026, 1, 5) + timedelta(days=91 * campaign_index))
        for operator in operators:
            strength = OPERATORS.get(operator, .95) + campaign_index * .004
            for repeat in range(repeats):
                for place, level, latitude, longitude, stretch in positions:
                    when = start + timedelta(days=generator.randint(0, 18), minutes=generator.randint(0, 600))
                    base = {'Campaign': campaign, 'Operator': operator, 'G_Level_1': 'Drive', 'G_Level_2': level,
                            'City': place}
                    for name, kind in DATA_TESTS:
                        serving = _serving(operator, place, generator, stretch)
                        fails = generator.random() < _failure_chance(operator, place, campaign_index, serving['_site_index'])
                        quality = max(.05, min(1.0, generator.gauss(strength - (.15 if fails else 0), .08)))
                        rate = max(.3, generator.lognormvariate(4.6 + (quality - .9) * 6, .55))
                        row = {**base, **{key: value for key, value in serving.items() if not key.startswith('_')},
                               'Test_Name': name, 'Type_of_Test': kind,
                               'Test_Result': 'Failed' if fails else 'Completed',
                               'Test_Start_Time': when.strftime('%Y-%m-%d %H:%M:%S'),
                               'Test_Start_Latitude': latitude + generator.uniform(-.03, .03),
                               'Test_Start_Longitude': longitude + generator.uniform(-.04, .04),
                               'Mean_Data_Rate': None if fails else round(rate / (8 if 'UL' in name else 1), 2),
                               'Transfer_Duration': None if fails else round(max(.4, 8 / max(rate, 1) * 4), 2)}
                        if kind == 'httpBrowser':
                            row.update(http_Browser_Transferred_Bytes=1_200_000,
                                       http_Browser_1MB_Reached_Duration=round(max(600, generator.gauss(2600 - quality * 900, 250))))
                        if kind == 'VideoStreaming':
                            row.update(VideoStream_Time_to_First_Picture=round(max(.5, generator.gauss(3 + (1 - quality) * 14, 1.5)), 2),
                                       Irritating_Video_Playout='Yes' if generator.random() < (1 - quality) * .4 else None)
                        if kind == 'Interactivity':
                            sent = 600
                            row.update(Packets_Sent=sent, Packets_Lost=int(max(0, generator.gauss((1 - quality) * 40, 4))),
                                       Packets_Discarded=0, Packets_Corrupted=0, Packets_Not_Sent=0,
                                       Interactivity_RTT_Median=round(max(12, generator.gauss(26 + (1 - quality) * 50, 4)), 1))
                        data.append(row)
                    for session in CALL_TYPES:
                        serving = _serving(operator, place, generator, stretch)
                        chance = _failure_chance(operator, place, campaign_index, serving['_site_index'])
                        draw = generator.random()
                        status = 'Failed' if draw < chance * .55 else 'Dropped' if draw < chance else 'Completed'
                        call = {**base, **{key: value for key, value in serving.items() if not key.startswith('_')},
                                'Session_Type': session, 'Call_Status': status,
                                'Call_Start_Time': when.strftime('%Y-%m-%d %H:%M:%S'),
                                'Call_Start_Latitude_A': latitude + generator.uniform(-.03, .03),
                                'Call_Start_Longitude_A': longitude + generator.uniform(-.04, .04),
                                'Call_Setup_Time': round(max(.8, generator.gauss(1.7 + (1 - strength) * 6, .35)), 2)
                                if status != 'Failed' else None,
                                'Disturbed_and_Impaired_Call': 'Yes' if generator.random() < (1 - strength) * .5 else 'No',
                                'Unsustainable_Call': 'Yes' if status == 'Completed' and generator.random() < .01 else 'No',
                                'Test_Status': ('Successful' if generator.random() > (1 - strength) * 1.2 else 'Failed')
                                if session == 'MultiRAB CALL' else None}
                        voice.append(call)
                        if status == 'Failed':
                            continue
                        for _sample in range(2):
                            speech.append({**base, 'Session_Type': session, 'Vendor': serving['Vendor'],
                                           'Serving_Network': serving['Serving_Network'],
                                           'Serving_Host_Network': serving['Serving_Host_Network'],
                                           'Serving_Site_ID': serving['Serving_Site_ID'],
                                           'Recording_Start_Time': call['Call_Start_Time'],
                                           'Recording_Latitude': call['Call_Start_Latitude_A'],
                                           'Recording_Longitude': call['Call_Start_Longitude_A'],
                                           'LQ': round(max(1.0, min(4.75, generator.gauss(3.6 + strength - (.9 if serving['_site_index'] == 3 else 0), .45))), 2)})
    return {'data': pd.DataFrame(data), 'voice': pd.DataFrame(voice), 'speech': pd.DataFrame(speech)}


def netcheck_2026_configuration() -> dict:
    """The NetCheck 2026 methodology shipped with the application."""
    import json
    from pathlib import Path

    from src.modules.scoring_config import validate_scoring_configuration
    document = json.loads((Path(__file__).resolve().parents[1] / 'assets' / 'scoring-methodologies'
                           / 'NetCheck_2026.json').read_text())
    return validate_scoring_configuration(document['profiles'][0]['configuration'])


def synthetic_cdr_result(levels=('Operator', 'City', 'Campaign'), **options) -> tuple[dict, dict]:
    """A job and its result calculated from the synthetic CDR rows with NetCheck 2026 (once per run, see
    tests.shared_results)."""
    from tests.shared_results import shared_result
    return shared_result('synthetic_cdr_result', _synthetic_cdr_result, tuple(levels),
                         **{key: tuple(value) if isinstance(value, list) else value for key, value in options.items()})


def _synthetic_cdr_result(levels, **options) -> tuple[dict, dict]:
    from src.modules.scoring import calculate_scoring
    configuration = netcheck_2026_configuration()
    result = calculate_scoring(synthetic_cdr_frames(**options), list(levels), baseline_operator='EE',
                               configuration=configuration)
    job = {'id': 1, 'levels': list(levels), 'aggregation_levels': list(levels), 'baseline_operator': 'EE',
           'configuration': result['configuration'], 'campaigns': list(result.get('campaigns') or []),
           'nr_mode': 'NSA', 'status': 'completed'}
    return job, result
