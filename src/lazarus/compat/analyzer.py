"""AST-based static analysis for Python 3.14 compatibility issues."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CompatIssue:
    file_path: str
    line_number: int
    issue_type: str
    description: str
    severity: str  # "error" or "warning"
    auto_fixable: bool


class StaticAnalyzer:
    """Detect Python 3.14 incompatibilities via AST inspection.

    Checks for APIs removed or changed in Python 3.14, based on the official
    deprecation schedule at https://docs.python.org/3/deprecations/.
    """

    def analyze_file(self, file_path: Path) -> list[CompatIssue]:
        """Analyze a single Python file for 3.14 incompatibilities."""
        try:
            source = file_path.read_text(encoding="utf-8", errors="replace")
        except (OSError, UnicodeDecodeError):
            return []

        try:
            tree = ast.parse(source, filename=str(file_path))
        except SyntaxError:
            return [CompatIssue(
                file_path=str(file_path),
                line_number=0,
                issue_type="syntax_error",
                description="File has syntax errors and cannot be parsed",
                severity="error",
                auto_fixable=False,
            )]

        path_str = str(file_path)
        issues: list[CompatIssue] = []
        issues.extend(self._check_deprecated_ast_nodes(tree, path_str))
        issues.extend(self._check_asyncio_child_watchers(tree, path_str))
        issues.extend(self._check_pkgutil_loaders(tree, path_str))
        issues.extend(self._check_sqlite3_version(tree, path_str))
        issues.extend(self._check_urllib_removals(tree, path_str))
        issues.extend(self._check_importlib_abc_removals(tree, path_str))
        issues.extend(self._check_shutil_onerror(tree, path_str))
        issues.extend(self._check_pathlib_extra_args(tree, path_str))
        issues.extend(self._check_pty_removals(tree, path_str))
        issues.extend(self._check_pkg_resources(tree, path_str))
        # Non-AST checks (operate on raw source text)
        issues.extend(self._check_invalid_escape_sequences(source, path_str))
        return issues

    def analyze_tree(self, source_dir: Path) -> list[CompatIssue]:
        """Analyze all Python files in a directory tree."""
        issues: list[CompatIssue] = []
        for py_file in source_dir.rglob("*.py"):
            issues.extend(self.analyze_file(py_file))
        return issues

    def _check_deprecated_ast_nodes(
        self, tree: ast.AST, path: str
    ) -> list[CompatIssue]:
        """Check for removed ast.Num, ast.Str, ast.Bytes, ast.NameConstant, ast.Ellipsis."""
        issues: list[CompatIssue] = []
        # These are references to ast module attributes, not actual node types in the tree.
        # We look for attribute access patterns like `ast.Num`, `ast.Str`, etc.
        deprecated_attrs = {
            "Num": "ast.Constant",
            "Str": "ast.Constant",
            "Bytes": "ast.Constant",
            "NameConstant": "ast.Constant",
            "Ellipsis": "ast.Constant",
        }

        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in deprecated_attrs:
                # Check if it's accessing the `ast` module
                if isinstance(node.value, ast.Name) and node.value.id == "ast":
                    replacement = deprecated_attrs[node.attr]
                    issues.append(CompatIssue(
                        file_path=path,
                        line_number=node.lineno,
                        issue_type="removed_ast_node",
                        description=f"ast.{node.attr} was removed in 3.14. Use {replacement} instead.",
                        severity="error",
                        auto_fixable=True,
                    ))

        return issues

    def _check_asyncio_child_watchers(
        self, tree: ast.AST, path: str
    ) -> list[CompatIssue]:
        """Check for removed asyncio child watcher APIs."""
        issues: list[CompatIssue] = []
        removed_attrs = {
            "AbstractChildWatcher",
            "SafeChildWatcher",
            "FastChildWatcher",
            "MultiLoopChildWatcher",
            "ThreadedChildWatcher",
            "PidfdChildWatcher",
            "get_child_watcher",
            "set_child_watcher",
        }

        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in removed_attrs:
                if isinstance(node.value, ast.Name) and node.value.id == "asyncio":
                    issues.append(CompatIssue(
                        file_path=path,
                        line_number=node.lineno,
                        issue_type="removed_asyncio_watcher",
                        description=f"asyncio.{node.attr} was removed in 3.14.",
                        severity="error",
                        auto_fixable=False,
                    ))
            # Also check `from asyncio import ...`
            if isinstance(node, ast.ImportFrom) and node.module == "asyncio":
                for alias in node.names:
                    if alias.name in removed_attrs:
                        issues.append(CompatIssue(
                            file_path=path,
                            line_number=node.lineno,
                            issue_type="removed_asyncio_watcher",
                            description=f"asyncio.{alias.name} was removed in 3.14.",
                            severity="error",
                            auto_fixable=False,
                        ))

        return issues

    def _check_pkgutil_loaders(
        self, tree: ast.AST, path: str
    ) -> list[CompatIssue]:
        """Check for removed pkgutil.find_loader() and get_loader()."""
        issues: list[CompatIssue] = []
        removed_funcs = {"find_loader", "get_loader"}

        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in removed_funcs:
                if isinstance(node.value, ast.Name) and node.value.id == "pkgutil":
                    issues.append(CompatIssue(
                        file_path=path,
                        line_number=node.lineno,
                        issue_type="removed_pkgutil_loader",
                        description=f"pkgutil.{node.attr}() was removed in 3.14. Use importlib.util.find_spec() instead.",
                        severity="error",
                        auto_fixable=True,
                    ))
            if isinstance(node, ast.ImportFrom) and node.module == "pkgutil":
                for alias in node.names:
                    if alias.name in removed_funcs:
                        issues.append(CompatIssue(
                            file_path=path,
                            line_number=node.lineno,
                            issue_type="removed_pkgutil_loader",
                            description=f"pkgutil.{alias.name}() was removed in 3.14. Use importlib.util.find_spec() instead.",
                            severity="error",
                            auto_fixable=True,
                        ))

        return issues

    def _check_sqlite3_version(
        self, tree: ast.AST, path: str
    ) -> list[CompatIssue]:
        """Check for removed sqlite3.version and sqlite3.version_info."""
        issues: list[CompatIssue] = []
        removed_attrs = {"version", "version_info"}

        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in removed_attrs:
                if isinstance(node.value, ast.Name) and node.value.id == "sqlite3":
                    issues.append(CompatIssue(
                        file_path=path,
                        line_number=node.lineno,
                        issue_type="removed_sqlite3_version",
                        description=f"sqlite3.{node.attr} was removed in 3.14. Use sqlite3.sqlite_version instead.",
                        severity="error",
                        auto_fixable=True,
                    ))

        return issues

    def _check_urllib_removals(
        self, tree: ast.AST, path: str
    ) -> list[CompatIssue]:
        """Check for removed urllib classes."""
        issues: list[CompatIssue] = []
        # urllib.request removals
        removed_request = {"URLopener", "FancyURLopener"}

        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in removed_request:
                if isinstance(node.value, ast.Attribute):
                    if (node.value.attr == "request"
                            and isinstance(node.value.value, ast.Name)
                            and node.value.value.id == "urllib"):
                        issues.append(CompatIssue(
                            file_path=path,
                            line_number=node.lineno,
                            issue_type="removed_urllib_class",
                            description=f"urllib.request.{node.attr} was removed in 3.14. Use urllib.request.urlopen() instead.",
                            severity="error",
                            auto_fixable=False,
                        ))
            if isinstance(node, ast.ImportFrom) and node.module == "urllib.request":
                for alias in node.names:
                    if alias.name in removed_request:
                        issues.append(CompatIssue(
                            file_path=path,
                            line_number=node.lineno,
                            issue_type="removed_urllib_class",
                            description=f"urllib.request.{alias.name} was removed in 3.14.",
                            severity="error",
                            auto_fixable=False,
                        ))

        return issues

    def _check_importlib_abc_removals(
        self, tree: ast.AST, path: str
    ) -> list[CompatIssue]:
        """Check for removed importlib.abc classes."""
        issues: list[CompatIssue] = []
        removed_classes = {"ResourceReader", "Traversable", "TraversableResources"}

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "importlib.abc":
                for alias in node.names:
                    if alias.name in removed_classes:
                        issues.append(CompatIssue(
                            file_path=path,
                            line_number=node.lineno,
                            issue_type="removed_importlib_abc",
                            description=f"importlib.abc.{alias.name} was removed in 3.14. Use importlib.resources.abc.{alias.name} instead.",
                            severity="error",
                            auto_fixable=True,
                        ))

        return issues

    def _check_shutil_onerror(
        self, tree: ast.AST, path: str
    ) -> list[CompatIssue]:
        """Check for shutil.rmtree() onerror parameter."""
        issues: list[CompatIssue] = []

        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "rmtree"):
                for kw in node.keywords:
                    if kw.arg == "onerror":
                        issues.append(CompatIssue(
                            file_path=path,
                            line_number=node.lineno,
                            issue_type="removed_shutil_onerror",
                            description="shutil.rmtree() 'onerror' parameter was removed in 3.14. Use 'onexc' instead.",
                            severity="error",
                            auto_fixable=True,
                        ))

        return issues

    def _check_pathlib_extra_args(
        self, tree: ast.AST, path: str
    ) -> list[CompatIssue]:
        """Check for pathlib extra args in is_relative_to() and relative_to()."""
        issues: list[CompatIssue] = []

        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in ("is_relative_to", "relative_to")):
                # Flag if more than 1 positional arg
                if len(node.args) > 1:
                    issues.append(CompatIssue(
                        file_path=path,
                        line_number=node.lineno,
                        issue_type="pathlib_extra_args",
                        description=f"pathlib.{node.func.attr}() no longer accepts multiple arguments in 3.14.",
                        severity="warning",
                        auto_fixable=False,
                    ))

        return issues

    def _check_pty_removals(
        self, tree: ast.AST, path: str
    ) -> list[CompatIssue]:
        """Check for removed pty.master_open() and pty.slave_open()."""
        issues: list[CompatIssue] = []
        removed_funcs = {"master_open", "slave_open"}

        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in removed_funcs:
                if isinstance(node.value, ast.Name) and node.value.id == "pty":
                    issues.append(CompatIssue(
                        file_path=path,
                        line_number=node.lineno,
                        issue_type="removed_pty_function",
                        description=f"pty.{node.attr}() was removed in 3.14. Use pty.openpty() instead.",
                        severity="error",
                        auto_fixable=True,
                    ))

        return issues

    def _check_pkg_resources(
        self, tree: ast.AST, path: str
    ) -> list[CompatIssue]:
        """Check for pkg_resources usage (removed from setuptools on 3.14).

        pkg_resources has been deprecated for years in favor of
        importlib.metadata and importlib.resources. In Python 3.14,
        setuptools no longer bundles it by default, causing
        ModuleNotFoundError at build/import time.
        """
        issues: list[CompatIssue] = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "pkg_resources" or alias.name.startswith("pkg_resources."):
                        issues.append(CompatIssue(
                            file_path=path,
                            line_number=node.lineno,
                            issue_type="deprecated_pkg_resources",
                            description=(
                                "pkg_resources is deprecated and removed from "
                                "setuptools on Python 3.14. Use importlib.metadata "
                                "or importlib.resources instead."
                            ),
                            severity="error",
                            auto_fixable=False,
                        ))
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module == "pkg_resources" or node.module.startswith("pkg_resources."):
                    issues.append(CompatIssue(
                        file_path=path,
                        line_number=node.lineno,
                        issue_type="deprecated_pkg_resources",
                        description=(
                            "pkg_resources is deprecated and removed from "
                            "setuptools on Python 3.14. Use importlib.metadata "
                            "or importlib.resources instead."
                        ),
                        severity="error",
                        auto_fixable=False,
                    ))

        return issues

    def _check_invalid_escape_sequences(
        self, source: str, path: str
    ) -> list[CompatIssue]:
        r"""Check for invalid escape sequences in string literals.

        Python 3.14 emits SyntaxWarning for unrecognized escape sequences
        like \p, \/, \d (outside raw strings). These will become SyntaxError
        in a future Python version.

        Valid escapes: \\, \', \", \a, \b, \f, \n, \r, \t, \v,
                       \0, \N{}, \uXXXX, \UXXXXXXXX, \xHH, \ooo, \newline
        """
        issues: list[CompatIssue] = []
        # Characters that are valid after a backslash in Python string literals.
        # These are the literal characters as they appear in source code (not the
        # escape values themselves). E.g., 'n' for \n, 't' for \t, etc.
        valid_after_backslash = set(
            "\\'\""           # \\, \', \"
            "abfnrtv"         # \a, \b, \f, \n, \r, \t, \v
            "0123456789"      # \0, \ooo (octal), \1-\7
            "NuUxo"           # \N{name}, \uXXXX, \UXXXXXXXX, \xHH, \ooo
            "\n"              # line continuation (actual newline)
        )

        # Match string literals (avoiding raw strings which don't have this issue)
        # We use a simple regex to find quoted strings on each line
        for lineno, line in enumerate(source.splitlines(), start=1):
            stripped = line.lstrip()
            # Skip comments
            if stripped.startswith("#"):
                continue
            # Skip lines with raw strings prefix — crude but fast
            # We need a more precise check: find string tokens with backslashes
            # that aren't in raw strings
            self._scan_line_for_bad_escapes(
                line, lineno, path, valid_after_backslash, issues
            )

        return issues

    @staticmethod
    def _scan_line_for_bad_escapes(
        line: str,
        lineno: int,
        path: str,
        valid_after_backslash: set[str],
        issues: list[CompatIssue],
    ) -> None:
        r"""Scan a single line for invalid escape sequences in string literals.

        Uses a simple state machine to track whether we're inside a string
        and whether the string is raw.
        """
        # Pattern to find string openings (not raw strings)
        # This is a simplified scanner — handles most common cases
        # We look for non-raw string literals containing backslashes
        i = 0
        length = len(line)
        while i < length:
            ch = line[i]

            # Skip comments
            if ch == "#":
                return

            # Check for string start
            if ch in ('"', "'"):
                # Look back to see if there's an 'r' or 'R' prefix
                prefix_start = i - 1
                while prefix_start >= 0 and line[prefix_start] in "bBuUfFrR":
                    prefix_start -= 1
                prefix = line[prefix_start + 1:i].lower()
                if "r" in prefix:
                    # Raw string — skip to end
                    i = _skip_string(line, i)
                    continue

                # Regular string — scan for bad escapes
                quote_char = ch
                # Check for triple quote
                if i + 2 < length and line[i + 1] == quote_char and line[i + 2] == quote_char:
                    # Triple-quoted string on same line — scan to closing triple
                    end_quote = quote_char * 3
                    j = i + 3
                    found_bad = False
                    while j < length:
                        if line[j] == "\\" and j + 1 < length:
                            next_ch = line[j + 1]
                            if next_ch not in valid_after_backslash:
                                found_bad = True
                                break
                            j += 2
                            continue
                        if line[j:j + 3] == end_quote:
                            break
                        j += 1
                    if found_bad:
                        issues.append(CompatIssue(
                            file_path=path,
                            line_number=lineno,
                            issue_type="invalid_escape_sequence",
                            description=(
                                f"Invalid escape sequence '\\{next_ch}'. "
                                f"Use a raw string (r'...') or escape the backslash (\\\\{next_ch}). "
                                f"This is a SyntaxWarning in 3.14 and will become an error."
                            ),
                            severity="warning",
                            auto_fixable=True,
                        ))
                    i = j + 3 if j + 3 <= length else length
                else:
                    # Single-quoted string
                    j = i + 1
                    found_bad = False
                    while j < length:
                        if line[j] == "\\" and j + 1 < length:
                            next_ch = line[j + 1]
                            if next_ch not in valid_after_backslash:
                                found_bad = True
                                break
                            j += 2
                            continue
                        if line[j] == quote_char:
                            break
                        j += 1
                    if found_bad:
                        issues.append(CompatIssue(
                            file_path=path,
                            line_number=lineno,
                            issue_type="invalid_escape_sequence",
                            description=(
                                f"Invalid escape sequence '\\{next_ch}'. "
                                f"Use a raw string (r'...') or escape the backslash (\\\\{next_ch}). "
                                f"This is a SyntaxWarning in 3.14 and will become an error."
                            ),
                            severity="warning",
                            auto_fixable=True,
                        ))
                    i = j + 1
            else:
                i += 1


def _skip_string(line: str, start: int) -> int:
    """Skip past a string literal starting at `start` (the opening quote)."""
    quote_char = line[start]
    length = len(line)

    # Triple quote?
    if start + 2 < length and line[start + 1] == quote_char and line[start + 2] == quote_char:
        end_quote = quote_char * 3
        j = start + 3
        while j < length:
            if line[j] == "\\" and j + 1 < length:
                j += 2
                continue
            if line[j:j + 3] == end_quote:
                return j + 3
            j += 1
        return length

    # Single quote
    j = start + 1
    while j < length:
        if line[j] == "\\" and j + 1 < length:
            j += 2
            continue
        if line[j] == quote_char:
            return j + 1
        j += 1
    return length
