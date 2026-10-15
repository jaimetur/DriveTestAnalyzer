"""Global cell identities of LTE (ECI) and NR (NCI) cells.

An LTE E-UTRAN Cell Identity is ``eNodeB ID × 256 + Cell ID`` and an NR Cell Identity is
``gNodeB ID × 2^(36 − gNodeB ID length) + Cell ID``. The Cell ID is the identity the cell
broadcasts; Huawei and Nokia cells also carry a different internal Local Cell ID, used only
when an inventory has no Cell ID.
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

LTE_CELL_BITS = 8
NR_IDENTITY_BITS = 36
# The gNodeB ID length of the UK operators' NR cells when an inventory does not give it.
DEFAULT_GNODEB_ID_LENGTH = 22


def integer_value(value: Any) -> int | None:
    """The whole number written in ``value`` (``'12.000'`` → 12), or ``None``."""
    if value is None:
        return None
    try:
        if isinstance(value, float) and math.isnan(value):
            return None
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or number != int(number) or number < 0:
        return None
    return int(number)


def nr_cell_bits(gnodeb_id_length: Any = None) -> int:
    """Bits of the cell part of an NCI for a gNodeB ID length (22 to 32 bits)."""
    length = integer_value(gnodeb_id_length)
    if length is None or not 22 <= length <= 32:
        length = DEFAULT_GNODEB_ID_LENGTH
    return NR_IDENTITY_BITS - length


def cell_part(cell_id: Any, local_cell_id: Any, bits: int) -> int | None:
    """The cell part of a global identity: the Cell ID, else the Local Cell ID, within ``bits``."""
    limit = 1 << bits
    for candidate in (integer_value(cell_id), integer_value(local_cell_id)):
        if candidate is not None and candidate < limit:
            return candidate
    return None


def lte_eci(enodeb_id: Any, cell_id: Any, local_cell_id: Any = None) -> int | None:
    """``eNodeB ID × 256 + Cell ID`` (the Local Cell ID only without a usable Cell ID)."""
    node = integer_value(enodeb_id)
    cell = cell_part(cell_id, local_cell_id, LTE_CELL_BITS)
    if node is None or cell is None or node > 0xFFFFF:
        return None
    return (node << LTE_CELL_BITS) | cell


def nr_nci(gnodeb_id: Any, cell_id: Any, local_cell_id: Any = None, gnodeb_id_length: Any = None) -> int | None:
    """``gNodeB ID × 2^(36 − length) + Cell ID`` (22-bit gNodeB IDs unless the inventory says otherwise)."""
    node = integer_value(gnodeb_id)
    bits = nr_cell_bits(gnodeb_id_length)
    cell = cell_part(cell_id, local_cell_id, bits)
    if node is None or cell is None or node >= 1 << (NR_IDENTITY_BITS - bits):
        return None
    return (node << bits) | cell


def nr_gnodeb(nci: Any, gnodeb_id_length: Any = None) -> int | None:
    """The gNodeB ID of an NR Cell Identity."""
    value = integer_value(nci)
    return None if value is None else value >> nr_cell_bits(gnodeb_id_length)


def _numeric(series: pd.Series | None, index: pd.Index) -> pd.Series:
    if series is None:
        return pd.Series(math.nan, index=index, dtype='float64')
    return pd.to_numeric(series, errors='coerce')


def _whole(values: pd.Series) -> pd.Series:
    return values.notna() & values.ge(0) & values.eq(values.round())


def lte_eci_series(enodeb_id: pd.Series, cell_id: pd.Series | None, local_cell_id: pd.Series | None = None) -> pd.Series:
    """Vectorised :func:`lte_eci`, as nullable integers."""
    index = enodeb_id.index
    node = _numeric(enodeb_id, index)
    cell, local = _numeric(cell_id, index), _numeric(local_cell_id, index)
    limit = 1 << LTE_CELL_BITS
    part = cell.where(_whole(cell) & cell.lt(limit), local.where(_whole(local) & local.lt(limit)))
    valid = _whole(node) & node.le(0xFFFFF) & part.notna()
    result = pd.Series(pd.NA, index=index, dtype='Int64')
    result.loc[valid] = node.loc[valid].astype('int64') * limit + part.loc[valid].astype('int64')
    return result


def nr_nci_series(
    gnodeb_id: pd.Series, cell_id: pd.Series | None, local_cell_id: pd.Series | None = None,
    gnodeb_id_length: pd.Series | None = None,
) -> pd.Series:
    """Vectorised :func:`nr_nci`, as nullable integers."""
    index = gnodeb_id.index
    node = _numeric(gnodeb_id, index)
    cell, local = _numeric(cell_id, index), _numeric(local_cell_id, index)
    lengths = _numeric(gnodeb_id_length, index)
    lengths = lengths.where(lengths.between(22, 32) & _whole(lengths), DEFAULT_GNODEB_ID_LENGTH)
    bits = NR_IDENTITY_BITS - lengths
    limit = 2.0 ** bits
    part = cell.where(_whole(cell) & cell.lt(limit), local.where(_whole(local) & local.lt(limit)))
    valid = _whole(node) & node.lt(2.0 ** lengths) & part.notna()
    result = pd.Series(pd.NA, index=index, dtype='Int64')
    result.loc[valid] = (node.loc[valid].astype('int64') * limit.loc[valid].astype('int64')
                         + part.loc[valid].astype('int64'))
    return result
