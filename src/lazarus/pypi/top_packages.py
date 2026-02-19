"""Fetch top PyPI packages by download count and seed the job queue."""

from __future__ import annotations

import httpx

from lazarus.db.queue import JobQueue

# Monthly top packages dataset maintained by hugovk
TOP_PACKAGES_URL = (
    "https://hugovk.github.io/top-pypi-packages/top-pypi-packages-30-days.min.json"
)


def fetch_top_packages(
    count: int = 1000, http: httpx.Client | None = None
) -> list[tuple[str, int]]:
    """Fetch the top N packages from PyPI by download count.

    Returns a list of (package_name, download_count) sorted by downloads descending.
    """
    client = http or httpx.Client(timeout=30.0)
    close_client = http is None

    try:
        resp = client.get(TOP_PACKAGES_URL)
        resp.raise_for_status()
        data = resp.json()
    finally:
        if close_client:
            client.close()

    rows = data.get("rows", [])
    result = []
    for row in rows[:count]:
        name = row.get("project") or row.get("download_count", {}).get("project", "")
        downloads = row.get("download_count", 0)
        if isinstance(downloads, dict):
            downloads = downloads.get("download_count", 0)
        if name:
            result.append((name, downloads))

    return result


def seed_queue(
    queue: JobQueue,
    count: int = 1000,
    python_target: str = "3.14",
    pypi_client: object | None = None,
    http: httpx.Client | None = None,
) -> int:
    """Seed the job queue with the top N packages from PyPI.

    Downloads the top packages list, resolves latest versions via PyPI,
    and adds them to the queue ordered by download count.

    Returns the number of new jobs added.
    """
    from lazarus.pypi.client import PyPIClient
    from pathlib import Path
    import tempfile

    packages = fetch_top_packages(count, http=http)

    if pypi_client is None:
        cache_dir = Path(tempfile.mkdtemp(prefix="lazarus_"))
        client = PyPIClient(cache_dir)
    else:
        client = pypi_client  # type: ignore[assignment]

    batch: list[tuple[str, str, int]] = []
    for name, downloads in packages:
        try:
            version = client.get_latest_version(name)
            batch.append((name, version, downloads))
        except Exception:
            # Skip packages we can't resolve
            continue

    return queue.add_batch(batch, python_target=python_target)
