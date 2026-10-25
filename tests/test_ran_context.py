"""The network around a Non-Qualified Call from the Network Inventory (ran_context): the inter-site distance of the sites,
the nearest site, the cells of the call, PCI collisions, cells out of service and ping-pongs."""
import math

import pandas as pd
import pytest

from src.modules import ran_context

# About 1 km of latitude (the haversine of the module measures within 1 %).
KM = 1 / 110.574


def cell(site: str, identity: str, latitude: float, longitude: float, *, family: str = 'vodafone', technology: str = 'LTE',
         pci: str = '', channel: str = '', state: str = '', in_service: bool = True) -> dict:
    return {'network_family': family, 'network': family.title(), 'host_network': family.title(), 'site_id': site,
            'cell_identity': identity, 'technology': technology, 'latitude': latitude, 'longitude': longitude, 'pci': pci,
            'channel': channel, 'state': state, 'in_service': in_service}


def city_and_country() -> pd.DataFrame:
    """A city of sites 1 km apart in a row, and a road far away with sites 6 km apart."""
    rows = [cell(f'C{index}', f'1{index}', 51.0 + index * KM, -1.0) for index in range(6)]
    rows += [cell(f'R{index}', f'2{index}', 53.0 + index * 6 * KM, -2.0) for index in range(4)]
    return pd.DataFrame(rows)


def test_the_isd_of_a_site_is_the_mean_distance_to_its_three_nearest_sites():
    index = ran_context.RanIndex(city_and_country())
    # The second site of the city has sites at 1, 1 and 2 km; the first one of the road at 6, 12 and 18 km.
    assert index.isd('vodafone|c1') == pytest.approx(4 / 3, rel=.01)
    assert index.isd('vodafone|r0') == pytest.approx(12, rel=.01)
    # A site alone in its network has no ISD.
    lonely = ran_context.RanIndex(pd.DataFrame([cell('L1', '9', 50.0, 0.0)]))
    assert lonely.isd('vodafone|l1') is None


def test_the_nearest_site_of_the_networks_serving_the_operator():
    rows = city_and_country().to_dict('records') + [cell('O1', '31', 51.0 + 2.6 * KM, -1.0, family='o2')]
    index = ran_context.RanIndex(pd.DataFrame(rows))
    point = (51.0 + 2.5 * KM, -1.0)
    assert index.nearest(point, ('vodafone',))['site_id'] in {'C2', 'C3'}
    nearest = index.nearest(point, ('vodafone', 'o2'))
    assert nearest['site_id'] == 'O1' and nearest['distance_km'] == pytest.approx(.1, rel=.02)
    assert index.nearest(None, ('vodafone',)) is None and index.nearest(point, ('three',)) is None


def test_a_cell_of_the_call_is_the_inventory_cell_of_the_first_network_nearest_to_it():
    rows = [cell('A', '100', 51.0, -1.0, family='o2'), cell('B', '100', 51.0 + 3 * KM, -1.0), cell('C', '100', 51.0 + 40 * KM, -1.0)]
    index = ran_context.RanIndex(pd.DataFrame(rows))
    where = (51.0 + 2 * KM, -1.0)
    # Its own network first, the nearest within the distance allowed.
    found = index.resolve('100', 'LTE', ('vodafone', 'o2'), where, 30.0)
    assert found['site_id'] == 'B' and found['distance_km'] == pytest.approx(1, rel=.01)
    assert index.resolve('100', 'LTE', ('o2', 'vodafone'), where, 30.0)['site_id'] == 'A'
    assert index.resolve('100', 'NR', ('vodafone',), where, 30.0) is None
    assert index.resolve('100', 'LTE', ('vodafone',), (51.0 + 80 * KM, -1.0), 30.0) is None


def test_pci_collisions_cells_out_of_service_and_ping_pongs():
    rows = [cell('A', '1', 51.0, -1.0, pci='101', channel='1392'), cell('B', '2', 51.0 + KM, -1.0, pci='101', channel='1392'),
            cell('C', '3', 51.0 + 5 * KM, -1.0, pci='101', channel='1392'), cell('B', '4', 51.0 + KM, -1.0, state='Locked'),
            cell('D', '5', 51.0, -1.001, pci='101', channel='6300')]
    index = ran_context.RanIndex(pd.DataFrame(rows))
    steps = [{'cell': '1', 'technology': 'LTE', 'pci': '101', 'channel': '1392'}]
    # Only B shares its PCI and channel within 2 km; D has another channel and C is too far.
    assert index.pci_collisions(steps, (51.0, -1.0), ran_context.PCI_RADIUS_KM) == 1
    assert index.out_of_service(['vodafone|b', 'vodafone|a']) == 1
    assert ran_context.ping_pongs(['1', '2', '1', '3', '1', '3']) == [('1', '2'), ('1', '3'), ('3', '1')]
    assert ran_context.ping_pongs(['1', '2', '3']) == []


def test_the_context_of_a_call_judges_its_serving_site_by_its_isd():
    index = ran_context.RanIndex(city_and_country())
    # Ending 3.5 km from the city and served by its last site: 3.5 km is about three times its ISD.
    end = (51.0 + 8.5 * KM, -1.0)
    steps = [{'cell': '15', 'technology': 'LTE', 'pci': '', 'channel': ''}]
    context = ran_context.call_context(index, ('vodafone',), steps, end, end, 30.0)
    assert context['serving_distance'] == pytest.approx(3.5, rel=.01)
    assert context['serving_isd_ratio'] == pytest.approx(context['serving_distance'] / index.isd('vodafone|c5'), abs=.01)
    assert context['nearest_site_distance'] == context['serving_distance'] and context['cells_out_of_service'] == 0
    assert context['network_note'].startswith(f"Network Inventory: served from Site C5 (Vodafone) at {context['serving_distance']:.2f} km")
    # The same 3.5 km on the road is less than its ISD there.
    road = (53.0 + 3.5 * KM, -2.0)
    context = ran_context.call_context(index, ('vodafone',), [{'cell': '20', 'technology': 'LTE'}], road, road, 30.0)
    assert context['serving_isd_ratio'] < 1 and context['nearest_site_isd_ratio'] < 1
    # Without the networks of the operator in the inventory, only the PCI collisions and cells out of service are known.
    assert set(ran_context.call_context(index, ('three',), [], end, end, 30.0)) == {'pci_collisions', 'cells_out_of_service'}
    assert math.isclose(ran_context.serving_isd_ratio(3.0, 1.5), 2.0) and ran_context.serving_isd_ratio(3.0, None) is None
