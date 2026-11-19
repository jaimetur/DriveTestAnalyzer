"""The result of a Saved Scoring as the Scoring page is served it: the views of both scorings, their National & area
summaries and, with NSA vs SA, each NR Mode on its own (ticket #188).

Building it takes from seconds to a minute of pure Python for a large Saved Scoring, so the application builds it in a
process of its own (see scoring_result_worker): the other users are answered meanwhile.
"""
from __future__ import annotations

import gzip
import json
from typing import Any

from fastapi.encoders import jsonable_encoder

from src.modules.mapping.operator_roles import out_of_scope_pairs
from src.modules.scoring.saved_scorings import POINTS_LOSS_STOPPED
from src.modules.scoring.scoring_vendors import normalize_scoring_vendor_result


class ResultViewsError(ValueError):
    """The views of a saved result cannot be built (shown as a conflict: the result no longer matches its methodology)."""


def packed_payload(payload: dict[str, Any]) -> bytes:
    """A result as served: JSON compressed with gzip."""
    return gzip.compress(json.dumps(jsonable_encoder(payload), ensure_ascii=False, allow_nan=False,
                                    separators=(',', ':')).encode('utf-8'), 5)


def saved_scoring_payload(saved_scoring: dict[str, Any], operator_groups: list[dict], vendor_groups: list[dict],
                             fallback: dict[str, Any] | None) -> dict[str, Any]:
    """The saved result of a Saved Scoring with the views of both scorings and their National & area summaries.

    NSA vs SA also gives the results of each NR Mode on their own (``nr_mode_parts``, NSA then SA), which the page shows
    one below the other in every tab."""
    from src.modules.scoring.scoring_views import normalize_result_gaps, nr_mode_result
    from src.modules.cdr.nr_mode import NR_MODES, NSA_VS_SA, normalize_scoring_nr_mode, nr_modes_of

    def out_of_scope(nr_mode: Any) -> dict[str, Any]:
        # The NR Mode · operator pairs out of scope in the NR Modes of a result (the NR Modes of the Operator Maps), which
        # the headings of its panels name.
        modes = nr_modes_of(nr_mode)
        pairs = [f"{pair['nr_mode']} · {pair['operator']}" for pair in out_of_scope_pairs(operator_groups) if pair['nr_mode'] in modes]
        return {'out_of_scope': pairs} if pairs else {}

    result = normalize_scoring_vendor_result(normalize_result_gaps(saved_scoring.get('result') or {}), operator_groups)
    payload = {**scoring_result_payload(saved_scoring, result, operator_groups, vendor_groups, fallback),
               **out_of_scope(saved_scoring.get('nr_mode'))}
    if normalize_scoring_nr_mode(saved_scoring.get('nr_mode')) == NSA_VS_SA and payload['views']:
        parts = []
        for mode in NR_MODES:
            part_result = nr_mode_result(result, mode)
            if not part_result.get('totals'):
                continue
            part_filter = {**nr_mode_result({key: value for key, value in saved_scoring.items() if key != 'result'}, mode),
                           'nr_mode': mode}
            parts.append({'nr_mode': mode, **scoring_result_payload(part_filter, part_result, operator_groups,
                                                                      vendor_groups, fallback), **out_of_scope(mode)})
        if len(parts) > 1:
            payload['nr_mode_parts'] = parts
    return payload


def scoring_result_payload(saved_scoring: dict[str, Any], result: dict[str, Any], operator_groups: list[dict],
                            vendor_groups: list[dict], fallback: dict[str, Any] | None) -> dict[str, Any]:
    """A result with the views of both scorings and their National & area summaries."""
    from src.modules.scoring.scoring_views import build_scoring_views, refresh_baseline_warning, scoring_coverage_notes
    views = {}
    scorings = {}
    if result.get('scoring') or result.get('score_rows'):
        from src.modules.scoring.scoring import most_reliable_result
        from src.modules.scoring.scoring_config import MOST_RELIABLE_SCORING, SCORING_LABELS
        baseline = str(saved_scoring.get('baseline_operator') or 'EE')
        try:
            views = build_scoring_views(
                saved_scoring, result, operator_groups, fallback,
                vendor_mapping_groups=vendor_groups,
            )
            refresh_baseline_warning(result, views, baseline)
            # The National & Geographical Areas Trends of the Saved Scoring, shown in Scoring Trends.
            from src.modules.scoring.scoring_area_summary import build_area_summary
            views.setdefault('insights', {})['area_summaries'] = build_area_summary(
                saved_scoring if saved_scoring.get('configuration') or result.get('configuration') else {**saved_scoring, 'configuration': fallback},
                result, operator_groups,
                vendor_mapping_groups=vendor_groups,
            )
            # The Most Reliable scoring is derived from the same saved KPI scores and filters.
            reliable = most_reliable_result(result, baseline, saved_scoring.get('configuration') or fallback)
            if reliable is not None:
                reliable_views = build_scoring_views(
                    saved_scoring, reliable, operator_groups,
                    vendor_mapping_groups=vendor_groups,
                )
                refresh_baseline_warning(reliable, reliable_views, baseline)
                reliable_views.setdefault('insights', {})['area_summaries'] = build_area_summary(
                    {**saved_scoring, 'configuration': reliable['configuration']}, reliable,
                    operator_groups,
                    vendor_mapping_groups=vendor_groups,
                )
                scorings[MOST_RELIABLE_SCORING] = {
                    'label': SCORING_LABELS[MOST_RELIABLE_SCORING], 'views': reliable_views,
                    'configuration': reliable['configuration'], 'notices': reliable['notices'],
                    'warnings': reliable['warnings'], 'environment_scaling': reliable['environment_scaling'],
                    'totals': reliable['totals'], 'gap_totals': reliable['gap_totals'],
                    'coverage_notes': scoring_coverage_notes(reliable),
                }
        except ValueError as exc:
            raise ResultViewsError(str(exc)) from exc
    result['coverage_notes'] = scoring_coverage_notes(result)
    # The points-lost shares and polygons reach the page through the views' insights and the boundaries endpoint.
    points_loss = result.get('points_loss')
    return {'saved_scoring': {key: value for key, value in saved_scoring.items() if key != 'result'},
            **{key: value for key, value in result.items() if key not in {'points_loss', 'area_summary'}},
            # A result from the Scoring History gets its Points Lost Map once the rows of the tests are read.
            'points_loss_pending': bool(isinstance(points_loss, dict) and points_loss.get('pending')),
            # Why the map is missing: stopped by a user (it is drawn again once the application is idle), or its error.
            'points_loss_error': points_loss.get('error') if isinstance(points_loss, dict) else None,
            'points_loss_stopped': bool(isinstance(points_loss, dict) and points_loss.get('error') == POINTS_LOSS_STOPPED),
            'views': views, 'scorings': scorings}
