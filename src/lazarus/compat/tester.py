"""Run package test suites in isolated Python 3.14 virtual environments."""

from __future__ import annotations

import subprocess
import sys
import venv
from dataclasses import dataclass
from pathlib import Path


@dataclass
class TestResult:
    passed: bool
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    test_framework: str | None = None


class CompatTester:
    """Test packages against a target Python version in isolated venvs."""

    def __init__(self, python_binary: str = "python3.14") -> None:
        self._python = python_binary

    def detect_test_framework(self, source_dir: Path) -> str | None:
        """Detect which test framework a package uses."""
        # Check for pytest markers
        if (source_dir / "pytest.ini").exists():
            return "pytest"
        if (source_dir / "setup.cfg").exists():
            cfg = (source_dir / "setup.cfg").read_text(errors="replace")
            if "[tool:pytest]" in cfg:
                return "pytest"
        if (source_dir / "pyproject.toml").exists():
            toml = (source_dir / "pyproject.toml").read_text(errors="replace")
            if "[tool.pytest" in toml:
                return "pytest"
        if (source_dir / "tox.ini").exists():
            return "tox"

        # Check for test directories
        test_dirs = ["tests", "test"]
        for td in test_dirs:
            test_path = source_dir / td
            if test_path.is_dir():
                # Look for pytest vs unittest
                for py_file in test_path.rglob("*.py"):
                    try:
                        content = py_file.read_text(errors="replace")
                    except OSError:
                        continue
                    if "import pytest" in content or "@pytest" in content:
                        return "pytest"
                    if "import unittest" in content or "TestCase" in content:
                        return "unittest"
                return "pytest"  # Default if test dir exists

        return None

    def create_venv(self, path: Path) -> Path:
        """Create a virtual environment at the given path."""
        venv.create(path, with_pip=True, system_site_packages=False)
        return path

    def _get_venv_python(self, venv_path: Path) -> str:
        """Get the Python executable path within a venv."""
        if sys.platform == "win32":
            return str(venv_path / "Scripts" / "python.exe")
        return str(venv_path / "bin" / "python")

    def _get_venv_pip(self, venv_path: Path) -> str:
        """Get the pip executable path within a venv."""
        if sys.platform == "win32":
            return str(venv_path / "Scripts" / "pip.exe")
        return str(venv_path / "bin" / "pip")

    def install_package(self, source_dir: Path, venv_path: Path) -> TestResult:
        """Install a package from source into a venv."""
        import time

        pip = self._get_venv_pip(venv_path)
        start = time.monotonic()

        result = subprocess.run(
            [pip, "install", str(source_dir)],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(source_dir),
        )

        duration = time.monotonic() - start
        return TestResult(
            passed=result.returncode == 0,
            exit_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            duration_seconds=duration,
        )

    def run_tests(self, source_dir: Path, venv_path: Path,
                  timeout: int = 300) -> TestResult:
        """Run the test suite for a package."""
        import time

        framework = self.detect_test_framework(source_dir)
        python = self._get_venv_python(venv_path)

        if framework == "pytest":
            cmd = [python, "-m", "pytest", "-x", "--tb=short", "-q"]
        elif framework == "unittest":
            cmd = [python, "-m", "unittest", "discover", "-s", "tests"]
        elif framework == "tox":
            # Fall back to pytest since tox may have complex env configs
            cmd = [python, "-m", "pytest", "-x", "--tb=short", "-q"]
        else:
            # No test framework detected — just try importing
            return self.try_import(source_dir, venv_path)

        start = time.monotonic()
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(source_dir),
            )
            duration = time.monotonic() - start
            return TestResult(
                passed=result.returncode == 0,
                exit_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                duration_seconds=duration,
                test_framework=framework,
            )
        except subprocess.TimeoutExpired:
            duration = time.monotonic() - start
            return TestResult(
                passed=False,
                exit_code=-1,
                stdout="",
                stderr=f"Tests timed out after {timeout}s",
                duration_seconds=duration,
                test_framework=framework,
            )

    def try_import(self, source_dir: Path, venv_path: Path) -> TestResult:
        """Fall-back test: just try importing the package."""
        import time

        python = self._get_venv_python(venv_path)

        # Guess the import name from the source directory
        import_name = self._guess_import_name(source_dir)
        if not import_name:
            return TestResult(
                passed=False,
                exit_code=-1,
                stdout="",
                stderr="Could not determine import name",
                duration_seconds=0.0,
            )

        start = time.monotonic()
        result = subprocess.run(
            [python, "-c", f"import {import_name}"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        duration = time.monotonic() - start

        return TestResult(
            passed=result.returncode == 0,
            exit_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            duration_seconds=duration,
        )

    def _guess_import_name(self, source_dir: Path) -> str | None:
        """Guess the importable package name from a source directory."""
        # Look for top-level packages in src/ or directly
        for base in [source_dir / "src", source_dir]:
            if not base.exists():
                continue
            for item in base.iterdir():
                if item.is_dir() and (item / "__init__.py").exists():
                    # Skip common non-package dirs
                    if item.name not in ("tests", "test", "docs", "examples"):
                        return item.name

        # Fall back to directory name, cleaned up
        name = source_dir.name.split("-")[0].replace(".", "_").replace("-", "_")
        return name
