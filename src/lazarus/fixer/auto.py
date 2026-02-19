"""Automatic fixes for well-defined Python 3.14 API removals.

These are mechanical substitutions that don't require AI — just pattern
matching and replacement.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from lazarus.compat.analyzer import CompatIssue


@dataclass
class FixResult:
    files_modified: list[str] = field(default_factory=list)
    issues_fixed: int = 0
    issues_skipped: int = 0
    errors: list[str] = field(default_factory=list)


class AutoFixer:
    """Apply deterministic fixes for known Python 3.14 breakages."""

    def apply_all(self, source_dir: Path, issues: list[CompatIssue]) -> FixResult:
        """Apply all auto-fixable issues found by the analyzer."""
        result = FixResult()
        # Group issues by file
        by_file: dict[str, list[CompatIssue]] = {}
        for issue in issues:
            if issue.auto_fixable:
                by_file.setdefault(issue.file_path, []).append(issue)

        for file_path, file_issues in by_file.items():
            path = Path(file_path)
            try:
                source = path.read_text(encoding="utf-8")
            except OSError as e:
                result.errors.append(f"Cannot read {file_path}: {e}")
                continue

            modified = source

            # Group issues by type to avoid double-counting when one fix
            # handles multiple issues of the same type in a single pass
            by_type: dict[str, list[CompatIssue]] = {}
            for issue in file_issues:
                by_type.setdefault(issue.issue_type, []).append(issue)

            fixed_count = 0
            for issue_type, type_issues in by_type.items():
                new_source = self._apply_fix(modified, type_issues[0])
                if new_source != modified:
                    modified = new_source
                    fixed_count += len(type_issues)
                else:
                    result.issues_skipped += len(type_issues)

            if modified != source:
                path.write_text(modified, encoding="utf-8")
                result.files_modified.append(file_path)
                result.issues_fixed += fixed_count

        return result

    def _apply_fix(self, source: str, issue: CompatIssue) -> str:
        """Apply a single fix to source code. Returns modified source."""
        handler = {
            "removed_ast_node": self._fix_ast_nodes,
            "removed_pkgutil_loader": self._fix_pkgutil_loaders,
            "removed_sqlite3_version": self._fix_sqlite3_version,
            "removed_shutil_onerror": self._fix_shutil_onerror,
            "removed_pty_function": self._fix_pty_functions,
            "removed_importlib_abc": self._fix_importlib_abc,
        }.get(issue.issue_type)

        if handler is None:
            return source
        return handler(source, issue)

    def _fix_ast_nodes(self, source: str, issue: CompatIssue) -> str:
        """Replace ast.Num/Str/Bytes/NameConstant/Ellipsis with ast.Constant."""
        deprecated = ["Num", "Str", "Bytes", "NameConstant", "Ellipsis"]
        for name in deprecated:
            source = re.sub(rf'\bast\.{name}\b', 'ast.Constant', source)
        return source

    def _fix_pkgutil_loaders(self, source: str, issue: CompatIssue) -> str:
        """Replace pkgutil.find_loader/get_loader with importlib.util.find_spec."""
        # Replace function calls
        source = re.sub(
            r'pkgutil\.find_loader\(([^)]+)\)',
            r'importlib.util.find_spec(\1)',
            source,
        )
        source = re.sub(
            r'pkgutil\.get_loader\(([^)]+)\)',
            r'importlib.util.find_spec(\1)',
            source,
        )
        # Replace imports
        source = re.sub(
            r'from pkgutil import (find_loader|get_loader)',
            'from importlib.util import find_spec',
            source,
        )
        # Ensure importlib.util is imported if using the module-level form
        if 'importlib.util.find_spec' in source and 'import importlib.util' not in source:
            if 'import importlib' in source:
                source = source.replace('import importlib', 'import importlib\nimport importlib.util', 1)
            elif 'from importlib' not in source:
                # Add import at the top, after other imports
                lines = source.split('\n')
                insert_idx = 0
                for i, line in enumerate(lines):
                    if line.startswith('import ') or line.startswith('from '):
                        insert_idx = i + 1
                lines.insert(insert_idx, 'import importlib.util')
                source = '\n'.join(lines)
        return source

    def _fix_sqlite3_version(self, source: str, issue: CompatIssue) -> str:
        """Replace sqlite3.version with sqlite3.sqlite_version."""
        source = re.sub(r'\bsqlite3\.version_info\b', 'sqlite3.sqlite_version_info', source)
        source = re.sub(r'\bsqlite3\.version\b', 'sqlite3.sqlite_version', source)
        return source

    def _fix_shutil_onerror(self, source: str, issue: CompatIssue) -> str:
        """Replace shutil.rmtree onerror parameter with onexc."""
        source = re.sub(
            r'(shutil\.rmtree\([^)]*)\bonerror\b',
            r'\1onexc',
            source,
        )
        return source

    def _fix_pty_functions(self, source: str, issue: CompatIssue) -> str:
        """Replace pty.master_open/slave_open with pty.openpty."""
        source = re.sub(r'\bpty\.master_open\b', 'pty.openpty', source)
        source = re.sub(r'\bpty\.slave_open\b', 'pty.openpty', source)
        return source

    def _fix_importlib_abc(self, source: str, issue: CompatIssue) -> str:
        """Replace importlib.abc with importlib.resources.abc for removed classes."""
        removed = ["ResourceReader", "Traversable", "TraversableResources"]
        for cls in removed:
            source = re.sub(
                rf'from importlib\.abc import ({cls})',
                rf'from importlib.resources.abc import \1',
                source,
            )
            source = re.sub(
                rf'\bimportlib\.abc\.{cls}\b',
                f'importlib.resources.abc.{cls}',
                source,
            )
        return source
