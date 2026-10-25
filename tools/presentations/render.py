"""Render the slides of the presentations that build.js wrote into a folder, as the server does for the Help viewer.

Run it from the project root once ``node tools/presentations/build.js <folder>`` has written them:
``python tools/presentations/render.py <folder>``. The server generates and renders its own (src/modules/presentations.py).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.modules.presentations import MANIFEST, render_slides  # noqa: E402


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit('python tools/presentations/render.py <folder written by build.js>')
    folder = Path(sys.argv[1]).resolve()
    manifest = json.loads((folder / MANIFEST).read_text(encoding='utf-8'))
    render_slides(folder, manifest)
    for presentation in manifest['presentations']:
        print(f"{presentation['id']}: {sum(len(section['slides']) for section in presentation['sections'])} slides")


if __name__ == '__main__':
    main()
