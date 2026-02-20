"""Build source distributions and wheels from fixed packages."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


class BuildError(Exception):
    """Raised when package building fails."""


class PackageBuilder:
    """Build sdist and wheel distributions using PEP 517.

    Supports SETUPTOOLS_SCM_PRETEND_VERSION to override git-tag-based
    versions for packages using setuptools_scm (zipp, importlib_metadata,
    etc.), ensuring the .post314 suffix appears in built filenames.
    """

    def _build_env(self, version: str | None = None) -> dict[str, str]:
        """Return environment for build subprocess.

        If *version* is given, sets SETUPTOOLS_SCM_PRETEND_VERSION so that
        packages using dynamic version (setuptools_scm) produce dists with
        the correct Lazarus version number.
        """
        env = os.environ.copy()
        if version:
            env["SETUPTOOLS_SCM_PRETEND_VERSION"] = version
        return env

    def build_sdist(
        self, source_dir: Path, output_dir: Path, *, version: str | None = None,
    ) -> Path:
        """Build a source distribution.

        Returns the path to the built .tar.gz file.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            [sys.executable, "-m", "build", "--sdist", "--outdir", str(output_dir)],
            cwd=str(source_dir),
            capture_output=True,
            text=True,
            timeout=300,
            env=self._build_env(version),
        )
        if result.returncode != 0:
            raise BuildError(f"sdist build failed:\n{result.stderr}")

        # Find the built file
        sdists = list(output_dir.glob("*.tar.gz"))
        if not sdists:
            raise BuildError("No .tar.gz found after build")
        return sdists[-1]

    def build_wheel(
        self, source_dir: Path, output_dir: Path, *, version: str | None = None,
    ) -> Path | None:
        """Build a wheel distribution.

        Returns the path to the built .whl file, or None if build fails
        (e.g., C extensions without build tools).
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            [sys.executable, "-m", "build", "--wheel", "--outdir", str(output_dir)],
            cwd=str(source_dir),
            capture_output=True,
            text=True,
            timeout=300,
            env=self._build_env(version),
        )
        if result.returncode != 0:
            return None  # Wheel build failed — may need platform build agents

        wheels = list(output_dir.glob("*.whl"))
        if not wheels:
            return None
        return wheels[-1]

    def build_all(
        self, source_dir: Path, output_dir: Path, *, version: str | None = None,
    ) -> list[Path]:
        """Build both sdist and wheel. Returns list of built distribution paths."""
        results: list[Path] = []

        sdist = self.build_sdist(source_dir, output_dir, version=version)
        results.append(sdist)

        wheel = self.build_wheel(source_dir, output_dir, version=version)
        if wheel is not None:
            results.append(wheel)

        return results
