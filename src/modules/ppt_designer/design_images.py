"""The pictures of the Image elements of slides (table design_images, ticket #26).

An Image element keeps the id of its picture (``content.image``, 32 hexadecimal characters); the picture itself is a row
of the workspace database. The PPT Designs and PPT Templates that use pictures carry them in exports, transfers and
backups (a JSON map of id -> picture, base64), and an import adds those the destination does not have yet: ids are
random, so the same id is the same picture."""
from __future__ import annotations

import base64
import binascii
import re
import sqlite3
from typing import Any, Iterable

IMAGES_TABLE = 'design_images'
IMAGE_ID = re.compile(r'[0-9a-f]{32}')
IMAGE_TYPES = {'image/png', 'image/jpeg', 'image/gif'}
# The id of a picture in the Format column of a template CSV, whose JSON doubles its quotes ("image": "<id>").
_FORMAT_IMAGE = re.compile(r'image"+\s*:\s*"+([0-9a-f]{32})')


def ensure_table(connection: Any) -> None:
    connection.execute(
        f'CREATE TABLE IF NOT EXISTS {IMAGES_TABLE} ('
        'id TEXT PRIMARY KEY, name TEXT NOT NULL DEFAULT \'\', content_type TEXT NOT NULL, data BLOB NOT NULL, '
        'width INTEGER NOT NULL DEFAULT 0, height INTEGER NOT NULL DEFAULT 0, created_by TEXT NOT NULL DEFAULT \'\', '
        'created_at TEXT NOT NULL)'
    )


def referenced_images(value: Any) -> set[str]:
    """The pictures a slide set, a PPT Design or several of them use (the ``image`` of an element's content)."""
    found: set[str] = set()
    if isinstance(value, dict):
        image = value.get('image')
        if isinstance(image, str) and IMAGE_ID.fullmatch(image):
            found.add(image)
        for item in value.values():
            found |= referenced_images(item)
    elif isinstance(value, list):
        for item in value:
            found |= referenced_images(item)
    return found


def template_images(contents: Iterable[bytes]) -> set[str]:
    """The pictures the slides of templates use, read from their CSV (the Format column)."""
    return {match for content in contents for match in _FORMAT_IMAGE.findall(bytes(content or b'').decode('utf-8', errors='replace'))}


def portable_images(repository: Any, ids: Iterable[str]) -> dict[str, dict[str, Any]]:
    """The pictures with these ids, as they travel: their name, type, size, creator and data (base64)."""
    wanted = sorted({image for image in ids if IMAGE_ID.fullmatch(str(image))})
    if not wanted:
        return {}
    try:
        with repository.connection() as connection:
            rows = connection.execute(
                f'SELECT id, name, content_type, data, width, height, created_by, created_at FROM {IMAGES_TABLE} '
                f"WHERE id IN ({', '.join('?' for _ in wanted)})", wanted).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {str(row['id']): {
        'name': str(row['name']), 'content_type': str(row['content_type']), 'width': int(row['width'] or 0),
        'height': int(row['height'] or 0), 'created_by': str(row['created_by'] or ''), 'created_at': str(row['created_at']),
        'data': base64.b64encode(bytes(row['data'])).decode('ascii'),
    } for row in rows}


def restore_images(repository: Any, images: Any) -> int:
    """Add the pictures of a package that this workspace does not have yet; returns how many were added."""
    if not isinstance(images, dict) or not images:
        return 0
    rows = []
    for image_id, picture in images.items():
        if not IMAGE_ID.fullmatch(str(image_id)) or not isinstance(picture, dict) or picture.get('content_type') not in IMAGE_TYPES:
            continue
        try:
            data = base64.b64decode(str(picture.get('data') or ''), validate=True)
        except (binascii.Error, ValueError):
            continue
        if not data:
            continue
        rows.append((str(image_id), str(picture.get('name') or '')[:200], picture['content_type'], sqlite3.Binary(data),
                     int(picture.get('width') or 0), int(picture.get('height') or 0), str(picture.get('created_by') or ''),
                     str(picture.get('created_at') or '')))
    if not rows:
        return 0
    with repository.connection() as connection:
        ensure_table(connection)
        before = connection.total_changes
        connection.executemany(
            f'INSERT OR IGNORE INTO {IMAGES_TABLE} (id, name, content_type, data, width, height, created_by, created_at) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?)', rows)
        return connection.total_changes - before
