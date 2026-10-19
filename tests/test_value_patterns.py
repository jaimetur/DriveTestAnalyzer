"""Patterns among the values of the Operator filters and the Focus operators: * for any characters, - or NOT to leave a
value out, resolved each time a filter is used."""
import sqlite3

import pandas as pd

from src.modules.value_maps import ValueMapper
from src.modules.value_patterns import ValueSet, expand, is_exclusion, is_pattern, sql_condition

OPERATORS = ['EE', 'VF', 'VF SA', 'VF SM', 'Three', 'Lebara', 'Lebara UK']


def taken(values):
    return [operator for operator in OPERATORS if operator in ValueSet(values)]


def test_values_patterns_and_exclusions_whatever_their_case():
    assert taken(['ee', 'VF*']) == ['EE', 'VF', 'VF SA', 'VF SM']
    # - or NOT (with a space) before a value leaves it out; several exclusions leave out each one.
    assert taken(['-Lebara']) == ['EE', 'VF', 'VF SA', 'VF SM', 'Three', 'Lebara UK']
    assert taken(['NOT Leb*']) == taken(['not leb*']) == ['EE', 'VF', 'VF SA', 'VF SM', 'Three']
    assert taken(['-Lebara', '-Three']) == ['EE', 'VF', 'VF SA', 'VF SM', 'Lebara UK']
    # Values and exclusions: those values but the excluded ones.
    assert taken(['VF*', '-VF SM']) == ['VF', 'VF SA']
    assert is_pattern('Not Lebara') and is_exclusion('-Lebara') and not is_pattern('Nothing') and not is_pattern('-')
    # A value known by several names (its label and the spellings of the CDRs) is left out by any of them.
    assert not ValueSet(['Not Lebara']).accepts(['Lebara', 'Lebara UK']) and ValueSet(['Not Lebara']).accepts(['EE'])
    frame = pd.Series(OPERATORS)
    assert list(frame[ValueSet(['VF*', '-VF SM']).mask(frame)]) == ['VF', 'VF SA']


def test_patterns_in_sql_take_the_same_rows():
    connection = sqlite3.connect(':memory:')
    connection.execute('CREATE TABLE rows (operator TEXT)')
    connection.executemany('INSERT INTO rows VALUES (?)', [(value,) for value in [*OPERATORS, 'A_B%C', None]])
    column = 'LOWER(TRIM(CAST(operator AS TEXT)))'
    for values in (['ee', 'VF*'], ['-Lebara'], ['NOT Leb*', '-Three'], ['VF*', '-VF SM'], ['a_b%*']):
        clause, params = sql_condition(column, values)
        rows = [row[0] for row in connection.execute(f'SELECT operator FROM rows WHERE {clause}', params)]
        assert [value for value in rows if value in OPERATORS] == taken(values), values
    # Other characters are taken as they are; a blank value stays with an exclusion.
    assert [row[0] for row in connection.execute(*(lambda clause, params: (f'SELECT operator FROM rows WHERE {clause}', params))(
        *sql_condition(column, ['a_b%*'])))] == ['A_B%C']
    assert None in [row[0] for row in connection.execute(*(lambda clause, params: (f'SELECT operator FROM rows WHERE {clause}', params))(
        *sql_condition(column, ['-Lebara'])))]


def test_patterns_take_the_spellings_of_the_operator_maps():
    mapper = ValueMapper(operator_mappings={'Lebara UK': 'Lebara', 'Vodafone': 'VF'})
    # The spellings of the CDRs that a pattern takes, by their own value or by their label.
    assert mapper.expand('operator', ['VF*'], ['Vodafone', 'VF SA', 'EE']) == ['Vodafone', 'VF SA', 'VF*']
    assert mapper.expand('operator', ['Not Lebara'], ['Lebara UK', 'Lebara', 'EE']) == ['EE', 'Not Lebara']
    # Resolved with the values available: a pattern that takes none stays, so the filter takes no value.
    assert expand(['Not Lebara'], OPERATORS) == ['EE', 'VF', 'VF SA', 'VF SM', 'Three', 'Lebara UK']
    assert expand(['Orange*'], OPERATORS) == ['Orange*']
