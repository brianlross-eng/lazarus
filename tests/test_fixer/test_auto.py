"""Tests for the auto-fixer."""

import textwrap
from pathlib import Path

from lazarus.compat.analyzer import CompatIssue, StaticAnalyzer
from lazarus.fixer.auto import AutoFixer


def _make_file(tmp_path: Path, code: str) -> Path:
    p = tmp_path / "module.py"
    p.write_text(textwrap.dedent(code))
    return p


class TestAutoFixAstNodes:
    def test_replaces_ast_num(self, tmp_path: Path) -> None:
        f = _make_file(tmp_path, """\
            import ast
            node = ast.Num
            other = ast.Str
        """)
        analyzer = StaticAnalyzer()
        issues = analyzer.analyze_file(f)
        fixer = AutoFixer()
        result = fixer.apply_all(tmp_path, issues)

        assert result.issues_fixed == 2
        content = f.read_text()
        assert "ast.Constant" in content
        assert "ast.Num" not in content
        assert "ast.Str" not in content


class TestAutoFixPkgutil:
    def test_replaces_find_loader(self, tmp_path: Path) -> None:
        f = _make_file(tmp_path, """\
            import pkgutil
            loader = pkgutil.find_loader("os")
        """)
        analyzer = StaticAnalyzer()
        issues = analyzer.analyze_file(f)
        fixer = AutoFixer()
        result = fixer.apply_all(tmp_path, issues)

        assert result.issues_fixed >= 1
        content = f.read_text()
        assert "importlib.util.find_spec" in content
        assert "pkgutil.find_loader" not in content


class TestAutoFixSqlite3:
    def test_replaces_version(self, tmp_path: Path) -> None:
        f = _make_file(tmp_path, """\
            import sqlite3
            v = sqlite3.version
            vi = sqlite3.version_info
        """)
        analyzer = StaticAnalyzer()
        issues = analyzer.analyze_file(f)
        fixer = AutoFixer()
        result = fixer.apply_all(tmp_path, issues)

        assert result.issues_fixed >= 1
        content = f.read_text()
        assert "sqlite3.sqlite_version" in content
        assert "sqlite3.sqlite_version_info" in content


class TestAutoFixShutil:
    def test_replaces_onerror(self, tmp_path: Path) -> None:
        f = _make_file(tmp_path, """\
            import shutil
            shutil.rmtree("/tmp/foo", onerror=handler)
        """)
        analyzer = StaticAnalyzer()
        issues = analyzer.analyze_file(f)
        fixer = AutoFixer()
        result = fixer.apply_all(tmp_path, issues)

        assert result.issues_fixed == 1
        content = f.read_text()
        assert "onexc" in content
        assert "onerror" not in content


class TestAutoFixPty:
    def test_replaces_master_open(self, tmp_path: Path) -> None:
        f = _make_file(tmp_path, """\
            import pty
            fd = pty.master_open()
        """)
        analyzer = StaticAnalyzer()
        issues = analyzer.analyze_file(f)
        fixer = AutoFixer()
        result = fixer.apply_all(tmp_path, issues)

        assert result.issues_fixed == 1
        content = f.read_text()
        assert "pty.openpty" in content
        assert "pty.master_open" not in content


class TestAutoFixImportlibAbc:
    def test_replaces_import(self, tmp_path: Path) -> None:
        f = _make_file(tmp_path, """\
            from importlib.abc import Traversable
        """)
        analyzer = StaticAnalyzer()
        issues = analyzer.analyze_file(f)
        fixer = AutoFixer()
        result = fixer.apply_all(tmp_path, issues)

        assert result.issues_fixed == 1
        content = f.read_text()
        assert "importlib.resources.abc" in content
