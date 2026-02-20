"""PEP 440 compliant version rewriting for Lazarus packages.

Uses .post releases to indicate Lazarus-patched versions:
    1.04       -> 1.04.post314     (fixed for Python 3.14)
    1.04       -> 1.04.post3141    (revision 1 of the 3.14 fix)
"""

from __future__ import annotations

import re
from pathlib import Path

from packaging.version import Version


def lazarus_version(
    original: str, python_target: str = "314", revision: int = 0
) -> str:
    """Convert a version string to its Lazarus .post variant.

    Args:
        original: The original PEP 440 version string (e.g., "2.31.0").
        python_target: Python version digits (e.g., "314" for 3.14).
        revision: Revision number (0 = first fix, 1 = second, etc.).

    Returns:
        PEP 440 compliant version (e.g., "2.31.0.post314").
    """
    # Validate the original version
    Version(original)  # Raises InvalidVersion if bad

    post_num = int(python_target)
    if revision > 0:
        post_num = int(f"{python_target}{revision}")

    return f"{original}.post{post_num}"


def parse_lazarus_version(version_str: str) -> tuple[str, str, int]:
    """Parse a Lazarus version back into its components.

    Args:
        version_str: A Lazarus version (e.g., "2.31.0.post3141").

    Returns:
        Tuple of (base_version, python_target, revision).
        E.g., ("2.31.0", "314", 1).
    """
    v = Version(version_str)
    if v.post is None:
        raise ValueError(f"Not a Lazarus version (no .post): {version_str}")

    post_str = str(v.post)

    # Python target is first 3 digits, revision is the rest
    if len(post_str) <= 3:
        python_target = post_str
        revision = 0
    else:
        python_target = post_str[:3]
        revision = int(post_str[3:])

    # Reconstruct base version without .post
    base = str(v).replace(f".post{v.post}", "")
    return base, python_target, revision


def is_lazarus_version(version_str: str) -> bool:
    """Check if a version string is a Lazarus-modified version."""
    try:
        v = Version(version_str)
        return v.post is not None and len(str(v.post)) >= 3
    except Exception:
        return False


def rewrite_version_in_source(source_dir: Path, new_version: str) -> list[str]:
    """Update version strings in package config files.

    Rewrites version in PKG-INFO, pyproject.toml, setup.py, setup.cfg,
    and __init__.py.  PKG-INFO is the authoritative metadata in sdists
    and is always rewritten when present — this covers packages with
    dynamic versions (flit, setuptools_scm, hatchling, etc.).

    Returns list of files modified.
    """
    modified: list[str] = []

    # PKG-INFO — authoritative metadata in sdists (always present).
    # Covers packages with dynamic versions that can't be rewritten
    # in source (flit reads __version__ via import, setuptools_scm
    # uses git tags, hatchling uses VCS).
    pkg_info = source_dir / "PKG-INFO"
    if pkg_info.exists():
        content = pkg_info.read_text(encoding="utf-8")
        new_content = re.sub(
            r"(^Version:\s*).+$",
            rf"\g<1>{new_version}",
            content,
            flags=re.MULTILINE,
        )
        if new_content != content:
            pkg_info.write_text(new_content, encoding="utf-8")
            modified.append(str(pkg_info))

    # pyproject.toml
    pyproject = source_dir / "pyproject.toml"
    if pyproject.exists():
        content = pyproject.read_text(encoding="utf-8")
        new_content = re.sub(
            r'(version\s*=\s*["\'])[^"\']+(["\'])',
            rf'\g<1>{new_version}\2',
            content,
        )
        if new_content != content:
            pyproject.write_text(new_content, encoding="utf-8")
            modified.append(str(pyproject))

    # setup.cfg
    setup_cfg = source_dir / "setup.cfg"
    if setup_cfg.exists():
        content = setup_cfg.read_text(encoding="utf-8")
        new_content = re.sub(
            r'(version\s*=\s*).+',
            rf'\g<1>{new_version}',
            content,
        )
        if new_content != content:
            setup_cfg.write_text(new_content, encoding="utf-8")
            modified.append(str(setup_cfg))

    # setup.py
    setup_py = source_dir / "setup.py"
    if setup_py.exists():
        content = setup_py.read_text(encoding="utf-8")
        new_content = re.sub(
            r'(version\s*=\s*["\'])[^"\']+(["\'])',
            rf'\g<1>{new_version}\2',
            content,
        )
        if new_content != content:
            setup_py.write_text(new_content, encoding="utf-8")
            modified.append(str(setup_py))

    # Look for __init__.py with __version__
    for init_file in source_dir.rglob("__init__.py"):
        # Skip test directories (check relative path only)
        rel = init_file.relative_to(source_dir)
        if any(p.startswith("test") for p in rel.parts):
            continue
        try:
            content = init_file.read_text(encoding="utf-8")
        except OSError:
            continue
        if "__version__" in content:
            new_content = re.sub(
                r'(__version__\s*=\s*["\'])[^"\']+(["\'])',
                rf'\g<1>{new_version}\2',
                content,
            )
            if new_content != content:
                init_file.write_text(new_content, encoding="utf-8")
                modified.append(str(init_file))

    return modified
