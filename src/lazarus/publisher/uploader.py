"""Upload built distributions to a devpi server."""

from __future__ import annotations

from pathlib import Path

import httpx


class UploadError(Exception):
    """Raised when package upload fails."""


class DevpiUploader:
    """Upload packages to a devpi index.

    Uses devpi's native authentication protocol:
    1. POST JSON credentials to /+login to get a session token
    2. Use X-Devpi-Auth header with user,token for all subsequent requests
    3. Upload via POST with :action=file_upload multipart form data
    """

    def __init__(
        self,
        server_url: str,
        index: str = "lazarus/packages",
        user: str = "lazarus",
        password: str = "",
    ) -> None:
        self._server_url = server_url.rstrip("/")
        self._index = index
        self._user = user
        self._password = password
        self._http = httpx.Client(timeout=120.0)
        self._token: str | None = None

    def close(self) -> None:
        self._http.close()

    def _login(self) -> str:
        """Authenticate with devpi and return a session token."""
        resp = self._http.post(
            f"{self._server_url}/+login",
            json={"user": self._user, "password": self._password},
        )
        if resp.status_code != 200:
            raise UploadError(
                f"Login failed: {resp.status_code} {resp.text}"
            )
        data = resp.json()
        token = data["result"]["password"]
        self._token = token
        return token

    def _auth_header(self) -> dict[str, str]:
        """Return the X-Devpi-Auth header, logging in if needed."""
        if self._token is None:
            self._login()
        return {"X-Devpi-Auth": f"{self._user},{self._token}"}

    def _get_upload_url(self) -> str:
        return f"{self._server_url}/{self._index}/"

    def upload(self, dist_paths: list[Path]) -> list[str]:
        """Upload one or more distribution files to the devpi index.

        Returns list of uploaded filenames.
        Raises UploadError if any upload fails.
        """
        upload_url = self._get_upload_url()
        uploaded = []

        for dist_path in dist_paths:
            # devpi uses legacy PyPI upload: all fields as multipart form parts
            with open(dist_path, "rb") as f:
                files = [
                    (":action", (None, "file_upload")),
                    ("name", (None, self._extract_name(dist_path))),
                    ("version", (None, self._extract_version(dist_path))),
                    ("content", (dist_path.name, f, "application/octet-stream")),
                ]
                resp = self._http.post(
                    upload_url,
                    headers=self._auth_header(),
                    files=files,
                )

            if resp.status_code == 401:
                # Token may have expired — re-login and retry
                self._login()
                with open(dist_path, "rb") as f:
                    files = [
                        (":action", (None, "file_upload")),
                        ("name", (None, self._extract_name(dist_path))),
                        ("version", (None, self._extract_version(dist_path))),
                        ("content", (dist_path.name, f, "application/octet-stream")),
                    ]
                    resp = self._http.post(
                        upload_url,
                        headers=self._auth_header(),
                        files=files,
                    )

            if resp.status_code not in (200, 201):
                raise UploadError(
                    f"Upload failed for {dist_path.name}: "
                    f"{resp.status_code} {resp.text[:500]}"
                )
            uploaded.append(dist_path.name)

        return uploaded

    @staticmethod
    def _extract_name(dist_path: Path) -> str:
        """Extract package name from a dist filename."""
        name = dist_path.stem
        # Remove .tar if it's a .tar.gz
        if name.endswith(".tar"):
            name = name[:-4]
        # Split on version separator: name-version
        parts = name.split("-")
        # Package name is everything before the first digit-starting segment
        name_parts = []
        for part in parts:
            if part and part[0].isdigit():
                break
            name_parts.append(part)
        return "-".join(name_parts) if name_parts else parts[0]

    @staticmethod
    def _extract_version(dist_path: Path) -> str:
        """Extract version from a dist filename."""
        name = dist_path.stem
        if name.endswith(".tar"):
            name = name[:-4]
        parts = name.split("-")
        # Version is the first digit-starting segment
        for part in parts:
            if part and part[0].isdigit():
                return part
        return "0.0.0"

    def check_exists(self, package_name: str, version: str) -> bool:
        """Check if a specific version already exists on the index."""
        url = (
            f"{self._server_url}/{self._index}/+simple/"
            f"{package_name.replace('_', '-').lower()}/"
        )
        resp = self._http.get(url)
        if resp.status_code != 200:
            return False
        # Check if this specific version appears in the simple index links
        return version in resp.text

    def remove(self, package_name: str, version: str) -> bool:
        """Remove a package version from the index."""
        url = f"{self._server_url}/{self._index}/{package_name}/{version}"
        resp = self._http.delete(url, headers=self._auth_header())
        return resp.status_code in (200, 204)
