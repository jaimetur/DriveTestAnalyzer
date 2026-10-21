"""Render the slides of the presentations kept in static/presentations for the Help viewer.

Run it from the project root once build.js has written them: ``python tools/presentations/render.py``. The server renders
those it generates itself in the same way (src/modules/presentations.py).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.modules.presentations import MANIFEST, STATIC_PRESENTATIONS, render_slides  # noqa: E402


def main() -> None:
    manifest = json.loads((STATIC_PRESENTATIONS / MANIFEST).read_text(encoding='utf-8'))
    render_slides(STATIC_PRESENTATIONS, manifest)
    for presentation in manifest['presentations']:
        print(f"{presentation['id']}: {sum(len(section['slides']) for section in presentation['sections'])} slides")


if __name__ == '__main__':
    main()
