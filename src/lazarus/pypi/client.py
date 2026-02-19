"""PyPI JSON API client for fetching package metadata and source distributions."""

from __future__ import annotations

import tarfile
import zipfile
from pathlib import Path

import httpx

from lazarus.pypi.metadata import PackageMetadata, VersionMetadata


class PyPIError(Exception):
    """Raised when a PyPI API request fails."""


class PyPIClient:
    """Client for the PyPI JSON API."""

    BASE_URL = "https://pypi.org"

    def __init__(self, cache_dir: Path, http: httpx.Client | None = None) -> None:
        self._cache_dir = cache_dir
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._http = http or httpx.Client(timeout=30.0)

    def close(self) -> None:
        self._http.close()

    def get_metadata(self, package_name: str) -> PackageMetadata:
        """Fetch metadata for the latest version of a package."""
        url = f"{self.BASE_URL}/pypi/{package_name}/json"
        resp = self._http.get(url)
        if resp.status_code == 404:
            raise PyPIError(f"Package not found: {package_name}")
        resp.raise_for_status()
        data = resp.json()

        info = data["info"]
        classifiers = [c for c in info.get("classifiers", []) if "Python" in c]

        # Check if any release has an sdist
        has_sdist = False
        for url_info in data.get("urls", []):
            if url_info.get("packagetype") == "sdist":
                has_sdist = True
                break

        return PackageMetadata(
            name=info["name"],
            latest_version=info["version"],
            summary=info.get("summary", ""),
            license=info.get("license"),
            requires_python=info.get("requires_python"),
            has_sdist=has_sdist,
            python_classifiers=classifiers,
        )

    def get_version_metadata(self, package_name: str, version: str) -> VersionMetadata:
        """Fetch metadata for a specific version of a package."""
        url = f"{self.BASE_URL}/pypi/{package_name}/{version}/json"
        resp = self._http.get(url)
        if resp.status_code == 404:
            raise PyPIError(f"Version not found: {package_name}=={version}")
        resp.raise_for_status()
        data = resp.json()

        info = data["info"]
        sdist_url = None
        sdist_filename = None
        sdist_size = None

        for url_info in data.get("urls", []):
            if url_info.get("packagetype") == "sdist":
                sdist_url = url_info["url"]
                sdist_filename = url_info["filename"]
                sdist_size = url_info.get("size")
                break

        return VersionMetadata(
            name=info["name"],
            version=info["version"],
            requires_python=info.get("requires_python"),
            sdist_url=sdist_url,
            sdist_filename=sdist_filename,
            sdist_size=sdist_size,
        )

    def download_sdist(self, package_name: str, version: str) -> Path:
        """Download the source distribution for a package version.

        Returns the path to the downloaded file.
        """
        meta = self.get_version_metadata(package_name, version)
        if meta.sdist_url is None:
            raise PyPIError(f"No sdist available for {package_name}=={version}")

        filename = meta.sdist_filename or f"{package_name}-{version}.tar.gz"
        dest = self._cache_dir / filename

        if dest.exists():
            return dest

        resp = self._http.get(meta.sdist_url, follow_redirects=True)
        resp.raise_for_status()
        dest.write_bytes(resp.content)
        return dest

    def extract_sdist(self, sdist_path: Path, dest: Path) -> Path:
        """Extract a source distribution archive.

        Returns the path to the extracted source directory.
        """
        dest.mkdir(parents=True, exist_ok=True)

        if sdist_path.name.endswith((".tar.gz", ".tgz")):
            with tarfile.open(sdist_path, "r:gz") as tar:
                tar.extractall(dest, filter="data")
        elif sdist_path.name.endswith(".zip"):
            with zipfile.ZipFile(sdist_path) as zf:
                zf.extractall(dest)
        else:
            raise PyPIError(f"Unknown archive format: {sdist_path.name}")

        # Find the extracted directory (usually packagename-version/)
        subdirs = [p for p in dest.iterdir() if p.is_dir()]
        if len(subdirs) == 1:
            return subdirs[0]
        return dest

    def get_latest_version(self, package_name: str) -> str:
        """Get the latest version string for a package."""
        meta = self.get_metadata(package_name)
        return meta.latest_version
