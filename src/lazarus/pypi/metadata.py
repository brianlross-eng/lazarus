"""Package metadata dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PackageMetadata:
    name: str
    latest_version: str
    summary: str
    license: str | None = None
    requires_python: str | None = None
    has_sdist: bool = False
    python_classifiers: list[str] = field(default_factory=list)


@dataclass
class VersionMetadata:
    name: str
    version: str
    requires_python: str | None = None
    sdist_url: str | None = None
    sdist_filename: str | None = None
    sdist_size: int | None = None
    has_c_extensions: bool = False
