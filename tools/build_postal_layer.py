#!/usr/bin/env python3
"""Build the copy of a postal code layer shipped with the application for a country, from its GeoNames postal code file.

    python tools/build_postal_layer.py GBR /path/to/GB_full.csv.zip --year 2026 --districts

The layer (the areas worked out from the points, see src/modules/postal_areas.py) goes to assets/map-areas/postal, with
its entry in the manifest of that folder; it stands in until a workspace downloads its own. Download the file from
https://download.geonames.org/export/zip/ (CC BY 4.0).
``--districts`` is for a file of full codes (GB_full): each code counts for its district, the part before the space.
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('country', help='ISO 3166 alpha-3 code, for example GBR')
    parser.add_argument('file', type=Path, help='GeoNames postal code ZIP of the country')
    parser.add_argument('--year', default='', help='Year of the file')
    parser.add_argument('--districts', action='store_true', help='The file has full codes: group them by district')
    parser.add_argument('--attribution', default='', help='What the file asks to credit, besides GeoNames')
    arguments = parser.parse_args()
    sys.path.insert(0, str(PROJECT_ROOT))
    # The application is only imported for its functions: its storage stays out of the user's folders.
    with tempfile.TemporaryDirectory(prefix='postal-layer-') as folder:
        os.environ['APP_CONFIG_DIR'] = str(Path(folder) / 'config')
        os.environ['APP_DATA_DIR'] = str(Path(folder) / 'data')
        from src.modules.postal_areas import (
            BUNDLED_DIR, GEONAMES_ATTRIBUTION, GEONAMES_LICENSE, GEONAMES_URL, LEVEL_LABEL, alpha2_code, coarser_codes,
            district_points, land_of, postal_boundaries, read_geonames,
        )

        code = arguments.country.strip().upper()
        alpha2 = alpha2_code(code)
        rows = read_geonames(arguments.file.read_bytes(), alpha2)
        points, level = (district_points(rows), 'Postal district') if arguments.districts else coarser_codes(rows)
        print(f'{code}: {len(rows)} rows, {len(points)} points')
        boundaries = postal_boundaries(points, land_of(None, code))
    BUNDLED_DIR.mkdir(parents=True, exist_ok=True)
    name = f'{code}.json.gz'
    # (No time in the file: the same layer gives the same bytes.)
    with open(BUNDLED_DIR / name, 'wb') as raw, gzip.GzipFile(fileobj=raw, mode='wb', mtime=0, filename='') as handle:
        handle.write(json.dumps({'country_code': code, 'boundaries': boundaries}, ensure_ascii=False,
                                separators=(',', ':')).encode('utf-8'))
    manifest_path = BUNDLED_DIR / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else {}
    manifest[code] = {'country_code': code, 'level': level, 'level_label': LEVEL_LABEL,
                      'source': GEONAMES_URL.format(code=arguments.file.name.removesuffix('.zip')),
                      'license': GEONAMES_LICENSE,
                      'attribution': '; '.join(text for text in (GEONAMES_ATTRIBUTION, arguments.attribution) if text),
                      'year': arguments.year, 'unit_count': len(boundaries), 'file': name}
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(f'{code}: {len(boundaries)} areas in {BUNDLED_DIR / name}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
