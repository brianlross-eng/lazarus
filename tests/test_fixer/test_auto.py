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


class TestAutoFixInvalidEscapeSequences:
    def test_fixes_invalid_escape_by_doubling_backslash(self, tmp_path: Path) -> None:
        f = tmp_path / "module.py"
        f.write_text('pattern = "hello\\pworld"\n')
        analyzer = StaticAnalyzer()
        issues = analyzer.analyze_file(f)
        auto_issues = [i for i in issues if i.auto_fixable]
        assert len(auto_issues) >= 1

        fixer = AutoFixer()
        result = fixer.apply_all(tmp_path, auto_issues)
        assert result.issues_fixed >= 1

        content = f.read_text()
        assert "\\\\p" in content  # Backslash was doubled
        assert "\\p" not in content.replace("\\\\p", "")  # No bare \p left

    def test_preserves_valid_escapes(self, tmp_path: Path) -> None:
        f = tmp_path / "module.py"
        # Mix of valid (\n) and invalid (\p) escapes
        f.write_text('msg = "line1\\nline2\\pextra"\n')
        analyzer = StaticAnalyzer()
        issues = analyzer.analyze_file(f)
        auto_issues = [i for i in issues if i.auto_fixable]

        fixer = AutoFixer()
        fixer.apply_all(tmp_path, auto_issues)

        content = f.read_text()
        assert "\\n" in content  # Valid escape preserved
        assert "\\\\p" in content  # Invalid escape doubled

    def test_leaves_raw_strings_alone(self, tmp_path: Path) -> None:
        f = tmp_path / "module.py"
        f.write_text('pattern = r"hello\\pworld"\n')
        analyzer = StaticAnalyzer()
        issues = analyzer.analyze_file(f)
        auto_issues = [i for i in issues if i.issue_type == "invalid_escape_sequence"]
        assert len(auto_issues) == 0  # Raw strings shouldn't be flagged

    def test_fixes_slash_in_regex(self, tmp_path: Path) -> None:
        """The schema package pattern: \\/ in a regular string."""
        f = tmp_path / "module.py"
        f.write_text('pattern = "^([a-zA-Z_][a-zA-Z0-9_]*)\\/"\n')
        analyzer = StaticAnalyzer()
        issues = analyzer.analyze_file(f)
        auto_issues = [i for i in issues if i.auto_fixable]

        fixer = AutoFixer()
        result = fixer.apply_all(tmp_path, auto_issues)
        assert result.issues_fixed >= 1

        content = f.read_text()
        # The \/ should become \\/ (doubled backslash)
        assert "\\\\/" in content


class TestAutoFixPkgResources:
    def test_fixes_get_distribution_version(self, tmp_path: Path) -> None:
        """Replace pkg_resources.get_distribution('X').version."""
        f = _make_file(tmp_path, """\
            import pkg_resources
            __version__ = pkg_resources.get_distribution("mypackage").version
        """)
        analyzer = StaticAnalyzer()
        issues = analyzer.analyze_file(f)
        fixer = AutoFixer()
        result = fixer.apply_all(tmp_path, issues)

        assert result.issues_fixed >= 1
        content = f.read_text()
        assert "pkg_resources" not in content
        assert 'importlib.metadata.version("mypackage")' in content
        assert "import importlib.metadata" in content

    def test_fixes_from_import_get_distribution(self, tmp_path: Path) -> None:
        """Replace from pkg_resources import get_distribution."""
        f = _make_file(tmp_path, """\
            from pkg_resources import get_distribution
            __version__ = get_distribution("mypackage").version
        """)
        analyzer = StaticAnalyzer()
        issues = analyzer.analyze_file(f)
        fixer = AutoFixer()
        result = fixer.apply_all(tmp_path, issues)

        assert result.issues_fixed >= 1
        content = f.read_text()
        assert "pkg_resources" not in content
        assert "from importlib.metadata import version as get_distribution" in content

    def test_fixes_require(self, tmp_path: Path) -> None:
        """Replace pkg_resources.require() with pass."""
        f = _make_file(tmp_path, """\
            import pkg_resources
            pkg_resources.require("somepackage>=1.0")
        """)
        analyzer = StaticAnalyzer()
        issues = analyzer.analyze_file(f)
        fixer = AutoFixer()
        result = fixer.apply_all(tmp_path, issues)

        assert result.issues_fixed >= 1
        content = f.read_text()
        assert "pkg_resources" not in content
        assert "pass" in content

    def test_fixes_resource_filename(self, tmp_path: Path) -> None:
        """Replace pkg_resources.resource_filename(X, Y)."""
        f = _make_file(tmp_path, """\
            import pkg_resources
            path = pkg_resources.resource_filename("mypackage", "data/file.txt")
        """)
        analyzer = StaticAnalyzer()
        issues = analyzer.analyze_file(f)
        fixer = AutoFixer()
        result = fixer.apply_all(tmp_path, issues)

        assert result.issues_fixed >= 1
        content = f.read_text()
        assert "pkg_resources" not in content
        assert "importlib.resources.files" in content

    def test_removes_unused_import(self, tmp_path: Path) -> None:
        """Remove bare import pkg_resources when all usages are replaced."""
        f = _make_file(tmp_path, """\
            import pkg_resources
            v = pkg_resources.get_distribution("foo").version
        """)
        analyzer = StaticAnalyzer()
        issues = analyzer.analyze_file(f)
        fixer = AutoFixer()
        result = fixer.apply_all(tmp_path, issues)

        content = f.read_text()
        assert "import pkg_resources" not in content
        assert "importlib.metadata" in content

    def test_fixes_from_import_resource_filename(self, tmp_path: Path) -> None:
        """Replace from pkg_resources import resource_filename."""
        f = _make_file(tmp_path, """\
            from pkg_resources import resource_filename
            path = resource_filename("mypackage", "data/file.txt")
        """)
        analyzer = StaticAnalyzer()
        issues = analyzer.analyze_file(f)
        fixer = AutoFixer()
        result = fixer.apply_all(tmp_path, issues)

        assert result.issues_fixed >= 1
        content = f.read_text()
        assert "pkg_resources" not in content
        assert "_pkg_files" in content


class TestAutoFixConfigparserSafeConfigParser:
    def test_fixes_attribute_access(self, tmp_path: Path) -> None:
        f = _make_file(tmp_path, """\
            import configparser
            parser = configparser.SafeConfigParser()
        """)
        analyzer = StaticAnalyzer()
        issues = analyzer.analyze_file(f)
        fixer = AutoFixer()
        result = fixer.apply_all(tmp_path, issues)

        assert result.issues_fixed >= 1
        content = f.read_text()
        assert "SafeConfigParser" not in content
        assert "configparser.ConfigParser()" in content

    def test_fixes_from_import(self, tmp_path: Path) -> None:
        f = _make_file(tmp_path, """\
            from configparser import SafeConfigParser
            parser = SafeConfigParser()
        """)
        analyzer = StaticAnalyzer()
        issues = analyzer.analyze_file(f)
        fixer = AutoFixer()
        result = fixer.apply_all(tmp_path, issues)

        assert result.issues_fixed >= 1
        content = f.read_text()
        assert "SafeConfigParser" not in content
        assert "from configparser import ConfigParser" in content
        assert "ConfigParser()" in content

    def test_fixes_readfp(self, tmp_path: Path) -> None:
        f = _make_file(tmp_path, """\
            import configparser
            parser = configparser.ConfigParser()
            parser.readfp(open("config.ini"))
        """)
        analyzer = StaticAnalyzer()
        issues = analyzer.analyze_file(f)
        fixer = AutoFixer()
        result = fixer.apply_all(tmp_path, issues)

        assert result.issues_fixed >= 1
        content = f.read_text()
        assert "readfp" not in content
        assert "read_file" in content


class TestAutoFixPython2Print:
    def test_fixes_print_string(self, tmp_path: Path) -> None:
        f = tmp_path / "module.py"
        f.write_text('print "hello"\n')
        issue = CompatIssue(
            file_path=str(f),
            line_number=1,
            issue_type="python2_print_statement",
            description="Python 2 print",
            severity="error",
            auto_fixable=True,
        )
        fixer = AutoFixer()
        result = fixer.apply_all(tmp_path, [issue])

        assert result.issues_fixed >= 1
        content = f.read_text()
        assert 'print("hello")' in content

    def test_fixes_print_multiple_args(self, tmp_path: Path) -> None:
        f = tmp_path / "module.py"
        f.write_text('print "a", "b", "c"\n')
        issue = CompatIssue(
            file_path=str(f),
            line_number=1,
            issue_type="python2_print_statement",
            description="Python 2 print",
            severity="error",
            auto_fixable=True,
        )
        fixer = AutoFixer()
        result = fixer.apply_all(tmp_path, [issue])

        content = f.read_text()
        assert 'print("a", "b", "c")' in content

    def test_fixes_trailing_comma(self, tmp_path: Path) -> None:
        f = tmp_path / "module.py"
        f.write_text('print "hello",\n')
        issue = CompatIssue(
            file_path=str(f),
            line_number=1,
            issue_type="python2_print_statement",
            description="Python 2 print",
            severity="error",
            auto_fixable=True,
        )
        fixer = AutoFixer()
        fixer.apply_all(tmp_path, [issue])

        content = f.read_text()
        assert 'print("hello", end=" ")' in content

    def test_fixes_redirect(self, tmp_path: Path) -> None:
        f = tmp_path / "module.py"
        f.write_text('print >>sys.stderr, "error"\n')
        issue = CompatIssue(
            file_path=str(f),
            line_number=1,
            issue_type="python2_print_statement",
            description="Python 2 print",
            severity="error",
            auto_fixable=True,
        )
        fixer = AutoFixer()
        fixer.apply_all(tmp_path, [issue])

        content = f.read_text()
        assert 'print("error", file=sys.stderr)' in content

    def test_preserves_print_function(self, tmp_path: Path) -> None:
        f = tmp_path / "module.py"
        f.write_text('print("already function")\nprint "statement"\n')
        issue = CompatIssue(
            file_path=str(f),
            line_number=2,
            issue_type="python2_print_statement",
            description="Python 2 print",
            severity="error",
            auto_fixable=True,
        )
        fixer = AutoFixer()
        fixer.apply_all(tmp_path, [issue])

        content = f.read_text()
        assert 'print("already function")' in content
        assert 'print("statement")' in content
