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


def _make_issue(file_path: str, issue_type: str) -> CompatIssue:
    """Helper to create a CompatIssue for fixer tests."""
    return CompatIssue(
        file_path=file_path,
        line_number=1,
        issue_type=issue_type,
        description="test",
        severity="error",
        auto_fixable=True,
    )


class TestAutoFixDistutils:
    def test_fixes_from_distutils_core(self, tmp_path: Path) -> None:
        f = _make_file(tmp_path, """\
            from distutils.core import setup
            setup(name="foo")
        """)
        fixer = AutoFixer()
        result = fixer.apply_all(tmp_path, [_make_issue(str(f), "removed_module_distutils")])

        assert result.issues_fixed >= 1
        content = f.read_text()
        assert "from setuptools import setup" in content
        assert "distutils" not in content

    def test_fixes_distutils_extension(self, tmp_path: Path) -> None:
        f = _make_file(tmp_path, """\
            from distutils.core import setup, Extension
        """)
        fixer = AutoFixer()
        fixer.apply_all(tmp_path, [_make_issue(str(f), "removed_module_distutils")])

        content = f.read_text()
        assert "from setuptools import setup, Extension" in content

    def test_fixes_distutils_command(self, tmp_path: Path) -> None:
        f = _make_file(tmp_path, """\
            from distutils.command.install import install
        """)
        fixer = AutoFixer()
        fixer.apply_all(tmp_path, [_make_issue(str(f), "removed_module_distutils")])

        content = f.read_text()
        assert "from setuptools.command.install import install" in content


class TestAutoFixImp:
    def test_fixes_imp_reload(self, tmp_path: Path) -> None:
        f = _make_file(tmp_path, """\
            import imp
            imp.reload(os)
        """)
        fixer = AutoFixer()
        result = fixer.apply_all(tmp_path, [_make_issue(str(f), "removed_module_imp")])

        assert result.issues_fixed >= 1
        content = f.read_text()
        assert "import importlib" in content
        assert "importlib.reload(os)" in content
        assert "import imp\n" not in content


class TestAutoFixPy2ConfigParser:
    def test_fixes_import(self, tmp_path: Path) -> None:
        f = tmp_path / "module.py"
        f.write_text("import ConfigParser\nparser = ConfigParser.ConfigParser()\n")
        fixer = AutoFixer()
        result = fixer.apply_all(
            tmp_path, [_make_issue(str(f), "removed_module_py2_configparser")]
        )

        assert result.issues_fixed >= 1
        content = f.read_text()
        assert "import configparser as ConfigParser" in content

    def test_fixes_from_import(self, tmp_path: Path) -> None:
        f = tmp_path / "module.py"
        f.write_text("from ConfigParser import SafeConfigParser\n")
        fixer = AutoFixer()
        fixer.apply_all(
            tmp_path, [_make_issue(str(f), "removed_module_py2_configparser")]
        )

        content = f.read_text()
        assert "from configparser import SafeConfigParser" in content


class TestAutoFixPipes:
    def test_fixes_pipes_quote(self, tmp_path: Path) -> None:
        f = _make_file(tmp_path, """\
            import pipes
            safe = pipes.quote("hello world")
        """)
        fixer = AutoFixer()
        result = fixer.apply_all(tmp_path, [_make_issue(str(f), "removed_module_pipes")])

        assert result.issues_fixed >= 1
        content = f.read_text()
        assert "import shlex" in content
        assert "shlex.quote" in content
        assert "pipes" not in content


class TestAutoFixCgi:
    def test_fixes_cgi_escape(self, tmp_path: Path) -> None:
        f = _make_file(tmp_path, """\
            import cgi
            safe = cgi.escape("<b>hi</b>")
        """)
        fixer = AutoFixer()
        result = fixer.apply_all(tmp_path, [_make_issue(str(f), "removed_module_cgi")])

        assert result.issues_fixed >= 1
        content = f.read_text()
        assert "html.escape" in content
        assert "import html" in content


class TestAutoFixCommands:
    def test_fixes_getoutput(self, tmp_path: Path) -> None:
        f = _make_file(tmp_path, """\
            import commands
            out = commands.getoutput("ls")
        """)
        fixer = AutoFixer()
        result = fixer.apply_all(tmp_path, [_make_issue(str(f), "removed_module_commands")])

        assert result.issues_fixed >= 1
        content = f.read_text()
        assert "import subprocess" in content
        assert "subprocess.getoutput" in content
        assert "commands" not in content


class TestAutoFixUrllib2:
    def test_fixes_import(self, tmp_path: Path) -> None:
        f = tmp_path / "module.py"
        f.write_text("import urllib2\nresp = urllib2.urlopen('http://example.com')\n")
        fixer = AutoFixer()
        result = fixer.apply_all(tmp_path, [_make_issue(str(f), "removed_module_urllib2")])

        assert result.issues_fixed >= 1
        content = f.read_text()
        assert "import urllib.request as urllib2" in content

    def test_fixes_from_import(self, tmp_path: Path) -> None:
        f = tmp_path / "module.py"
        f.write_text("from urllib2 import urlopen\n")
        fixer = AutoFixer()
        result = fixer.apply_all(tmp_path, [_make_issue(str(f), "removed_module_urllib2")])

        content = f.read_text()
        assert "from urllib.request import urlopen" in content


class TestAutoFixQueue:
    def test_fixes_import(self, tmp_path: Path) -> None:
        f = tmp_path / "module.py"
        f.write_text("import Queue\nq = Queue.Queue()\n")
        fixer = AutoFixer()
        result = fixer.apply_all(tmp_path, [_make_issue(str(f), "removed_module_Queue")])

        assert result.issues_fixed >= 1
        content = f.read_text()
        assert "import queue as Queue" in content

    def test_fixes_from_import(self, tmp_path: Path) -> None:
        f = tmp_path / "module.py"
        f.write_text("from Queue import Queue\n")
        fixer = AutoFixer()
        result = fixer.apply_all(tmp_path, [_make_issue(str(f), "removed_module_Queue")])

        content = f.read_text()
        assert "from queue import Queue" in content


class TestAutoFixExecfile:
    def test_fixes_simple_call(self, tmp_path: Path) -> None:
        f = tmp_path / "module.py"
        f.write_text("execfile('setup.py')\n")
        fixer = AutoFixer()
        result = fixer.apply_all(tmp_path, [_make_issue(str(f), "python2_builtin_execfile")])

        assert result.issues_fixed >= 1
        content = f.read_text()
        assert "exec(open('setup.py').read())" in content
        assert "execfile" not in content

    def test_fixes_two_arg_form(self, tmp_path: Path) -> None:
        f = tmp_path / "module.py"
        f.write_text("execfile('setup.py', globals())\n")
        fixer = AutoFixer()
        fixer.apply_all(tmp_path, [_make_issue(str(f), "python2_builtin_execfile")])

        content = f.read_text()
        assert "exec(open('setup.py').read(), globals())" in content


class TestAutoFixRawInput:
    def test_fixes_raw_input(self, tmp_path: Path) -> None:
        f = tmp_path / "module.py"
        f.write_text("name = raw_input('Enter name: ')\n")
        fixer = AutoFixer()
        result = fixer.apply_all(tmp_path, [_make_issue(str(f), "python2_builtin_raw_input")])

        assert result.issues_fixed >= 1
        content = f.read_text()
        assert "input('Enter name: ')" in content
        assert "raw_input" not in content


class TestAutoFixAstConstantAttrs:
    def test_fixes_constant_s(self, tmp_path: Path) -> None:
        f = _make_file(tmp_path, """\
            import ast
            value = node.Constant.s
        """)
        fixer = AutoFixer()
        result = fixer.apply_all(
            tmp_path, [_make_issue(str(f), "removed_ast_constant_attr")]
        )

        assert result.issues_fixed >= 1
        content = f.read_text()
        assert ".Constant.value" in content
        assert ".Constant.s" not in content

    def test_fixes_constant_n(self, tmp_path: Path) -> None:
        f = _make_file(tmp_path, """\
            import ast
            value = node.Constant.n
        """)
        fixer = AutoFixer()
        result = fixer.apply_all(
            tmp_path, [_make_issue(str(f), "removed_ast_constant_attr")]
        )

        content = f.read_text()
        assert ".Constant.value" in content
        assert ".Constant.n" not in content
