"""Local data store: one JSON file, written atomically.

Writes go to a temporary file and are then moved into place, so a
crash mid-save never leaves a half-written file.  The previous version
is kept as ``<file>.bak`` so a bad import can always be undone.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile

from .models import Store

DEFAULT_DATA_FILE = "social-data.json"


def load_store(path: str) -> Store:
    """Load the store, or return an empty one if the file is missing."""
    if not os.path.exists(path):
        return Store()
    with open(path, "r", encoding="utf-8") as handle:
        return Store.from_dict(json.load(handle))


def save_store(store: Store, path: str) -> None:
    """Save atomically and keep the previous version as .bak."""
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".smad-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(store.to_dict(), handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        if os.path.exists(path):
            shutil.copy2(path, path + ".bak")
        os.replace(tmp_path, path)
    except BaseException:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def existing_keys(store: Store) -> set:
    """Post keys already in the store (used to skip duplicates)."""
    return {post.key() for post in store.posts}
