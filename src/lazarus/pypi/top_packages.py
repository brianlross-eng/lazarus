"""Fetch top PyPI packages by download count and seed the job queue."""

from __future__ import annotations

import concurrent.futures
import logging

import httpx

from lazarus.db.queue import JobQueue

log = logging.getLogger(__name__)

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


def _resolve_version(name: str, downloads: int) -> tuple[str, str, int] | None:
    """Resolve latest version for a single package via PyPI JSON API."""
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(f"https://pypi.org/pypi/{name}/json")
            resp.raise_for_status()
            version = resp.json()["info"]["version"]
            return (name, version, downloads)
    except Exception:
        return None


def seed_queue(
    queue: JobQueue,
    count: int = 1000,
    python_target: str = "3.14",
    pypi_client: object | None = None,
    http: httpx.Client | None = None,
    max_workers: int = 30,
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

    # Filter out packages already in the queue to avoid wasted API calls
    existing = queue.get_package_names()
    new_packages = [(n, d) for n, d in packages if n not in existing]
    log.info(
        "Seed: %d total, %d already queued, %d to resolve",
        len(packages), len(packages) - len(new_packages), len(new_packages),
    )

    if not new_packages:
        return 0

    # Use concurrent resolution for speed (sequential for tests or small batches)
    if pypi_client is not None or len(new_packages) <= 50:
        # Legacy sequential path (used by tests with mock client)
        if pypi_client is None:
            cache_dir = Path(tempfile.mkdtemp(prefix="lazarus_"))
            client = PyPIClient(cache_dir)
        else:
            client = pypi_client  # type: ignore[assignment]

        batch: list[tuple[str, str, int]] = []
        for name, downloads in new_packages:
            try:
                version = client.get_latest_version(name)
                batch.append((name, version, downloads))
            except Exception:
                continue
    else:
        # Concurrent resolution via thread pool
        batch = []
        resolved = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {
                pool.submit(_resolve_version, name, downloads): name
                for name, downloads in new_packages
            }
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                if result is not None:
                    batch.append(result)
                resolved += 1
                if resolved % 500 == 0:
                    log.info("  Resolved %d / %d versions...", resolved, len(new_packages))

        log.info("Resolved %d / %d versions", len(batch), len(new_packages))

    return queue.add_batch(batch, python_target=python_target)


def fetch_all_package_names() -> list[str]:
    """Fetch all package names from the PyPI simple index."""
    import re

    with httpx.Client(timeout=120.0) as client:
        resp = client.get("https://pypi.org/simple/")
        resp.raise_for_status()
        # Links are like href="/simple/package-name/" — extract just the name
        return re.findall(r'href="/simple/([^"]+)/"', resp.text)


def seed_queue_deep(
    queue: JobQueue,
    count: int = 5000,
    python_target: str = "3.14",
    max_workers: int = 30,
) -> int:
    """Seed the queue from the full PyPI index (beyond the top-15k).

    Fetches all package names from PyPI, filters out already-queued ones,
    then randomly samples ``count`` packages and resolves their versions
    concurrently.

    Returns the number of new jobs added.
    """
    import random

    print("Fetching full PyPI package index...")
    all_names = fetch_all_package_names()
    print(f"PyPI index contains {len(all_names)} packages")

    existing = queue.get_package_names()
    new_names = [n for n in all_names if n not in existing]
    print(
        f"Deep seed: {len(all_names)} total on PyPI, "
        f"{len(all_names) - len(new_names)} already queued, "
        f"{len(new_names)} new candidates"
    )

    if not new_names:
        return 0

    # Sample randomly from the long tail
    sample = random.sample(new_names, min(count, len(new_names)))
    print(f"Sampled {len(sample)} packages to resolve")

    # Concurrent version resolution
    batch: list[tuple[str, str, int]] = []
    resolved = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_resolve_version, name, 0): name
            for name in sample
        }
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result is not None:
                batch.append(result)
            resolved += 1
            if resolved % 500 == 0:
                print(f"  Resolved {resolved} / {len(sample)} versions...")

    log.info("Resolved %d / %d versions", len(batch), len(sample))
    return queue.add_batch(batch, python_target=python_target)
