"""Upload built distributions to a devpi server."""

from __future__ import annotations

from pathlib import Path

import httpx


class UploadError(Exception):
    """Raised when package upload fails."""


class DevpiUploader:
    """Upload packages to a devpi index."""

    def __init__(
        self,
        server_url: str,
        index: str = "lazarus/stable",
        user: str = "lazarus",
        password: str = "",
    ) -> None:
        self._server_url = server_url.rstrip("/")
        self._index = index
        self._user = user
        self._password = password
        self._http = httpx.Client(timeout=60.0)

    def close(self) -> None:
        self._http.close()

    def _get_upload_url(self) -> str:
        return f"{self._server_url}/{self._index}/"

    def upload(self, dist_paths: list[Path]) -> bool:
        """Upload one or more distribution files to the devpi index.

        Returns True if all uploads succeeded.
        """
        upload_url = self._get_upload_url()

        for dist_path in dist_paths:
            with open(dist_path, "rb") as f:
                files = {"content": (dist_path.name, f, "application/octet-stream")}
                resp = self._http.post(
                    upload_url,
                    files=files,
                    auth=(self._user, self._password),
                )

            if resp.status_code not in (200, 201):
                raise UploadError(
                    f"Upload failed for {dist_path.name}: "
                    f"{resp.status_code} {resp.text}"
                )

        return True

    def check_exists(self, package_name: str, version: str) -> bool:
        """Check if a specific version already exists on the index."""
        url = f"{self._server_url}/{self._index}/{package_name}/{version}/"
        resp = self._http.get(url)
        return resp.status_code == 200

    def remove(self, package_name: str, version: str) -> bool:
        """Remove a package version from the index."""
        url = f"{self._server_url}/{self._index}/{package_name}/{version}/"
        resp = self._http.delete(
            url, auth=(self._user, self._password)
        )
        return resp.status_code in (200, 204)
