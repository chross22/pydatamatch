"""The download cache.

Each time step is one NetCDF file, named from everything that determines its
contents, so a re-run reads from disk and only the missing steps cost a
download. Set ``PYDATAMATCH_CACHE`` to move it; the default lives under the
user cache directory.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path


def cache_dir() -> Path:
    root = os.environ.get("PYDATAMATCH_CACHE")
    if root is None:
        root = Path.home() / ".cache" / "pydatamatch"
    path = Path(root)
    path.mkdir(parents=True, exist_ok=True)
    return path


def cache_file(dataset_id: str, time, codes, bounding_box: dict, depth) -> Path:
    """The cache path for one time step of one request.

    The bounding box, variables and depth are part of the name (hashed, to
    keep it a filename) because a different subset of the same dataset and
    day is a different file.
    """
    key = repr((sorted(codes), sorted(bounding_box.items()), tuple(depth)))
    digest = hashlib.sha1(key.encode()).hexdigest()[:12]
    stamp = time.strftime("%Y%m%d")
    return cache_dir() / f"{dataset_id}_{stamp}_{digest}.nc"
