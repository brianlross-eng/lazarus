"""AST-based static analysis for Python 3.14 compatibility issues."""

from __future__ import annotations

import ast
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
