"""Tests for the static analyzer."""

import textwrap
from pathlib import Path

import pytest

from lazarus.compat.analyzer import StaticAnalyzer


@pytest.fixture
def analyzer() -> StaticAnalyzer:
    return StaticAnalyzer()


@pytest.fixture
def tmp_py(tmp_path: Path):
    """Helper to create a temporary Python file."""
    def _make(code: str) -> Path:
        p = tmp_path / "test_module.py"
        p.write_text(textwrap.dedent(code))
        return p
    return _make


class TestDeprecatedAstNodes:
    def test_detects_ast_num(self, analyzer: StaticAnalyzer, tmp_py) -> None:
        f = tmp_py("""\
            import ast
            node = ast.Num
        """)
        issues = analyzer.analyze_file(f)
        assert len(issues) == 1
        assert issues[0].issue_type == "removed_ast_node"
        assert issues[0].auto_fixable is True

    def test_detects_ast_str(self, analyzer: StaticAnalyzer, tmp_py) -> None:
        f = tmp_py("""\
            import ast
            node = ast.Str
        """)
        issues = analyzer.analyze_file(f)
        assert len(issues) == 1
        assert "ast.Str" in issues[0].description

    def test_detects_multiple_deprecated_nodes(self, analyzer: StaticAnalyzer, tmp_py) -> None:
        f = tmp_py("""\
            import ast
            a = ast.Num
            b = ast.Str
            c = ast.Bytes
            d = ast.NameConstant
        """)
        issues = analyzer.analyze_file(f)
        assert len(issues) == 4

    def test_ignores_non_ast_module(self, analyzer: StaticAnalyzer, tmp_py) -> None:
        f = tmp_py("""\
            class my_ast:
                Num = 42
            x = my_ast.Num
        """)
        issues = analyzer.analyze_file(f)
        assert len(issues) == 0


class TestAsyncioChildWatchers:
    def test_detects_attribute_access(self, analyzer: StaticAnalyzer, tmp_py) -> None:
        f = tmp_py("""\
            import asyncio
            watcher = asyncio.SafeChildWatcher()
        """)
        issues = analyzer.analyze_file(f)
        assert len(issues) == 1
        assert issues[0].issue_type == "removed_asyncio_watcher"

    def test_detects_import_from(self, analyzer: StaticAnalyzer, tmp_py) -> None:
        f = tmp_py("""\
            from asyncio import SafeChildWatcher, FastChildWatcher
        """)
        issues = analyzer.analyze_file(f)
        assert len(issues) == 2


class TestPkgutilLoaders:
    def test_detects_find_loader(self, analyzer: StaticAnalyzer, tmp_py) -> None:
        f = tmp_py("""\
            import pkgutil
            loader = pkgutil.find_loader("os")
        """)
        issues = analyzer.analyze_file(f)
        assert len(issues) == 1
        assert issues[0].auto_fixable is True

    def test_detects_import_from(self, analyzer: StaticAnalyzer, tmp_py) -> None:
        f = tmp_py("""\
            from pkgutil import find_loader
        """)
        issues = analyzer.analyze_file(f)
        assert len(issues) == 1


class TestSqlite3Version:
    def test_detects_version(self, analyzer: StaticAnalyzer, tmp_py) -> None:
        f = tmp_py("""\
            import sqlite3
            print(sqlite3.version)
        """)
        issues = analyzer.analyze_file(f)
        assert len(issues) == 1
        assert issues[0].auto_fixable is True


class TestShutilOnerror:
    def test_detects_onerror_kwarg(self, analyzer: StaticAnalyzer, tmp_py) -> None:
        f = tmp_py("""\
            import shutil
            shutil.rmtree("/tmp/foo", onerror=lambda *a: None)
        """)
        issues = analyzer.analyze_file(f)
        assert len(issues) == 1
        assert issues[0].issue_type == "removed_shutil_onerror"


class TestImportlibAbc:
    def test_detects_resource_reader(self, analyzer: StaticAnalyzer, tmp_py) -> None:
        f = tmp_py("""\
            from importlib.abc import Traversable
        """)
        issues = analyzer.analyze_file(f)
        assert len(issues) == 1
        assert issues[0].auto_fixable is True


class TestPtyRemovals:
    def test_detects_master_open(self, analyzer: StaticAnalyzer, tmp_py) -> None:
        f = tmp_py("""\
            import pty
            fd = pty.master_open()
        """)
        issues = analyzer.analyze_file(f)
        assert len(issues) == 1
        assert issues[0].auto_fixable is True


class TestPkgResources:
    def test_detects_import(self, analyzer: StaticAnalyzer, tmp_py) -> None:
        f = tmp_py("""\
            import pkg_resources
            version = pkg_resources.get_distribution("foo").version
        """)
        issues = analyzer.analyze_file(f)
        assert len(issues) == 1
        assert issues[0].issue_type == "deprecated_pkg_resources"
        assert issues[0].auto_fixable is False

    def test_detects_from_import(self, analyzer: StaticAnalyzer, tmp_py) -> None:
        f = tmp_py("""\
            from pkg_resources import get_distribution
        """)
        issues = analyzer.analyze_file(f)
        assert len(issues) == 1
        assert issues[0].issue_type == "deprecated_pkg_resources"

    def test_detects_submodule_import(self, analyzer: StaticAnalyzer, tmp_py) -> None:
        f = tmp_py("""\
            import pkg_resources.extern
        """)
        issues = analyzer.analyze_file(f)
        assert len(issues) == 1

    def test_ignores_unrelated_pkg(self, analyzer: StaticAnalyzer, tmp_py) -> None:
        f = tmp_py("""\
            import pkg_other
        """)
        issues = analyzer.analyze_file(f)
        assert len(issues) == 0


class TestInvalidEscapeSequences:
    def test_detects_invalid_escape(self, analyzer: StaticAnalyzer, tmp_py) -> None:
        # Write raw content to avoid Python processing the escapes
        p = tmp_py("x = 1")  # Create the file first
        p.write_text('pattern = "hello\\pworld"\n')
        issues = analyzer.analyze_file(p)
        escape_issues = [i for i in issues if i.issue_type == "invalid_escape_sequence"]
        assert len(escape_issues) == 1
        assert escape_issues[0].auto_fixable is True
        assert escape_issues[0].severity == "warning"

    def test_ignores_valid_escapes(self, analyzer: StaticAnalyzer, tmp_py) -> None:
        p = tmp_py("x = 1")
        # Use raw string so \\n and \\t are written literally as \n and \t in the file
        p.write_text(r'msg = "hello\nworld\t!"' + "\n")
        issues = analyzer.analyze_file(p)
        escape_issues = [i for i in issues if i.issue_type == "invalid_escape_sequence"]
        assert len(escape_issues) == 0

    def test_ignores_raw_strings(self, analyzer: StaticAnalyzer, tmp_py) -> None:
        p = tmp_py("x = 1")
        p.write_text('pattern = r"hello\\pworld"\n')
        issues = analyzer.analyze_file(p)
        escape_issues = [i for i in issues if i.issue_type == "invalid_escape_sequence"]
        assert len(escape_issues) == 0

    def test_detects_in_single_quotes(self, analyzer: StaticAnalyzer, tmp_py) -> None:
        p = tmp_py("x = 1")
        p.write_text("pattern = 'hello\\dworld'\n")
        issues = analyzer.analyze_file(p)
        escape_issues = [i for i in issues if i.issue_type == "invalid_escape_sequence"]
        assert len(escape_issues) == 1

    def test_ignores_comments(self, analyzer: StaticAnalyzer, tmp_py) -> None:
        p = tmp_py("x = 1")
        p.write_text('# This \\p is in a comment\nx = 1\n')
        issues = analyzer.analyze_file(p)
        escape_issues = [i for i in issues if i.issue_type == "invalid_escape_sequence"]
        assert len(escape_issues) == 0

    def test_detects_common_regex_pattern(self, analyzer: StaticAnalyzer, tmp_py) -> None:
        """The schema package example: \\/ in a regular string."""
        p = tmp_py("x = 1")
        p.write_text('pattern = "^([a-zA-Z_][a-zA-Z0-9_]*)\\/"\n')
        issues = analyzer.analyze_file(p)
        escape_issues = [i for i in issues if i.issue_type == "invalid_escape_sequence"]
        assert len(escape_issues) == 1


class TestAnalyzeTree:
    def test_scans_directory(self, analyzer: StaticAnalyzer, tmp_path: Path) -> None:
        (tmp_path / "a.py").write_text("import ast\nx = ast.Num\n")
        (tmp_path / "b.py").write_text("import pkgutil\npkgutil.find_loader('x')\n")
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "c.py").write_text("import sqlite3\nsqlite3.version\n")

        issues = analyzer.analyze_tree(tmp_path)
        assert len(issues) == 3

    def test_handles_syntax_error(self, analyzer: StaticAnalyzer, tmp_path: Path) -> None:
        (tmp_path / "bad.py").write_text("def foo(:\n")
        issues = analyzer.analyze_tree(tmp_path)
        assert len(issues) == 1
        assert issues[0].issue_type == "syntax_error"
