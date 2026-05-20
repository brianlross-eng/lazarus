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
        assert issues[0].auto_fixable is True

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


class TestConfigparserSafeConfigParser:
    def test_detects_attribute_access(self, analyzer: StaticAnalyzer, tmp_py) -> None:
        f = tmp_py("""\
            import configparser
            parser = configparser.SafeConfigParser()
        """)
        issues = analyzer.analyze_file(f)
        assert len(issues) == 1
        assert issues[0].issue_type == "removed_configparser_safeconfigparser"
        assert issues[0].auto_fixable is True

    def test_detects_from_import(self, analyzer: StaticAnalyzer, tmp_py) -> None:
        f = tmp_py("""\
            from configparser import SafeConfigParser
            parser = SafeConfigParser()
        """)
        issues = analyzer.analyze_file(f)
        assert len(issues) == 1
        assert issues[0].issue_type == "removed_configparser_safeconfigparser"

    def test_ignores_configparser(self, analyzer: StaticAnalyzer, tmp_py) -> None:
        f = tmp_py("""\
            import configparser
            parser = configparser.ConfigParser()
        """)
        issues = analyzer.analyze_file(f)
        assert len(issues) == 0

    def test_detects_readfp(self, analyzer: StaticAnalyzer, tmp_py) -> None:
        f = tmp_py("""\
            import configparser
            parser = configparser.ConfigParser()
            parser.readfp(open("config.ini"))
        """)
        issues = analyzer.analyze_file(f)
        readfp_issues = [i for i in issues if i.issue_type == "removed_configparser_readfp"]
        assert len(readfp_issues) == 1
        assert readfp_issues[0].auto_fixable is True


class TestPython2PrintStatement:
    def test_detects_print_statement(self, analyzer: StaticAnalyzer, tmp_py) -> None:
        p = tmp_py("x = 1")
        p.write_text('print "hello"\n')
        issues = analyzer.analyze_file(p)
        print_issues = [i for i in issues if i.issue_type == "python2_print_statement"]
        assert len(print_issues) == 1
        assert print_issues[0].auto_fixable is True

    def test_detects_print_redirect(self, analyzer: StaticAnalyzer, tmp_py) -> None:
        p = tmp_py("x = 1")
        p.write_text('print >>sys.stderr, "error"\n')
        issues = analyzer.analyze_file(p)
        print_issues = [i for i in issues if i.issue_type == "python2_print_statement"]
        assert len(print_issues) == 1

    def test_ignores_print_function(self, analyzer: StaticAnalyzer, tmp_py) -> None:
        f = tmp_py('print("hello")\n')
        issues = analyzer.analyze_file(f)
        print_issues = [i for i in issues if i.issue_type == "python2_print_statement"]
        assert len(print_issues) == 0

    def test_ignores_print_in_comment(self, analyzer: StaticAnalyzer, tmp_py) -> None:
        f = tmp_py('# print "old code"\nx = 1\n')
        issues = analyzer.analyze_file(f)
        print_issues = [i for i in issues if i.issue_type == "python2_print_statement"]
        assert len(print_issues) == 0

    def test_no_syntax_error_when_print_detected(self, analyzer: StaticAnalyzer, tmp_py) -> None:
        """When print statements are detected, generic syntax_error should not be added."""
        p = tmp_py("x = 1")
        p.write_text('print "hello"\nprint "world"\n')
        issues = analyzer.analyze_file(p)
        assert not any(i.issue_type == "syntax_error" for i in issues)
        assert any(i.issue_type == "python2_print_statement" for i in issues)


class TestRemovedStdlibModules:
    def test_detects_import_distutils(self, analyzer: StaticAnalyzer, tmp_py) -> None:
        f = tmp_py("""\
            from distutils.core import setup
            setup(name="foo")
        """)
        issues = analyzer.analyze_file(f)
        dist_issues = [i for i in issues if i.issue_type == "removed_module_distutils"]
        assert len(dist_issues) == 1
        assert dist_issues[0].auto_fixable is True

    def test_detects_import_imp(self, analyzer: StaticAnalyzer, tmp_py) -> None:
        f = tmp_py("""\
            import imp
            imp.reload(os)
        """)
        issues = analyzer.analyze_file(f)
        imp_issues = [i for i in issues if i.issue_type == "removed_module_imp"]
        assert len(imp_issues) == 1

    def test_detects_import_pipes(self, analyzer: StaticAnalyzer, tmp_py) -> None:
        f = tmp_py("""\
            import pipes
            pipes.quote("hello world")
        """)
        issues = analyzer.analyze_file(f)
        pipe_issues = [i for i in issues if i.issue_type == "removed_module_pipes"]
        assert len(pipe_issues) == 1

    def test_detects_import_cgi(self, analyzer: StaticAnalyzer, tmp_py) -> None:
        f = tmp_py("""\
            import cgi
            cgi.escape("<b>hi</b>")
        """)
        issues = analyzer.analyze_file(f)
        cgi_issues = [i for i in issues if i.issue_type == "removed_module_cgi"]
        assert len(cgi_issues) == 1

    def test_reports_once_per_module(self, analyzer: StaticAnalyzer, tmp_py) -> None:
        f = tmp_py("""\
            import distutils
            from distutils.core import setup
        """)
        issues = analyzer.analyze_file(f)
        dist_issues = [i for i in issues if i.issue_type == "removed_module_distutils"]
        assert len(dist_issues) == 1

    def test_detects_py2_configparser(self, analyzer: StaticAnalyzer, tmp_py) -> None:
        p = tmp_py("x = 1")
        p.write_text("import ConfigParser\n")
        issues = analyzer.analyze_file(p)
        cp_issues = [i for i in issues if i.issue_type == "removed_module_py2_configparser"]
        assert len(cp_issues) == 1

    def test_ignores_py3_configparser(self, analyzer: StaticAnalyzer, tmp_py) -> None:
        f = tmp_py("""\
            import configparser
        """)
        issues = analyzer.analyze_file(f)
        cp_issues = [i for i in issues if i.issue_type == "removed_module_py2_configparser"]
        assert len(cp_issues) == 0


class TestPython2Builtins:
    def test_detects_execfile(self, analyzer: StaticAnalyzer, tmp_py) -> None:
        p = tmp_py("x = 1")
        p.write_text("execfile('setup.py')\n")
        issues = analyzer.analyze_file(p)
        exec_issues = [i for i in issues if i.issue_type == "python2_builtin_execfile"]
        assert len(exec_issues) == 1
        assert exec_issues[0].auto_fixable is True

    def test_detects_raw_input(self, analyzer: StaticAnalyzer, tmp_py) -> None:
        p = tmp_py("x = 1")
        p.write_text("name = raw_input('Enter name: ')\n")
        issues = analyzer.analyze_file(p)
        ri_issues = [i for i in issues if i.issue_type == "python2_builtin_raw_input"]
        assert len(ri_issues) == 1

    def test_detects_xrange(self, analyzer: StaticAnalyzer, tmp_py) -> None:
        p = tmp_py("x = 1")
        p.write_text("for i in xrange(10): pass\n")
        issues = analyzer.analyze_file(p)
        xr_issues = [i for i in issues if i.issue_type == "python2_builtin_xrange"]
        assert len(xr_issues) == 1
        assert xr_issues[0].auto_fixable is True

    def test_detects_reload(self, analyzer: StaticAnalyzer, tmp_py) -> None:
        p = tmp_py("x = 1")
        p.write_text("import os\nreload(os)\n")
        issues = analyzer.analyze_file(p)
        rl_issues = [i for i in issues if i.issue_type == "python2_builtin_reload"]
        assert len(rl_issues) == 1

    def test_detects_unicode(self, analyzer: StaticAnalyzer, tmp_py) -> None:
        p = tmp_py("x = 1")
        p.write_text("s = unicode('hello')\n")
        issues = analyzer.analyze_file(p)
        u_issues = [i for i in issues if i.issue_type == "python2_builtin_unicode"]
        assert len(u_issues) == 1

    def test_detects_long(self, analyzer: StaticAnalyzer, tmp_py) -> None:
        p = tmp_py("x = 1")
        p.write_text("n = long(42)\n")
        issues = analyzer.analyze_file(p)
        l_issues = [i for i in issues if i.issue_type == "python2_builtin_long"]
        assert len(l_issues) == 1

    def test_ignores_execfile_as_method(self, analyzer: StaticAnalyzer, tmp_py) -> None:
        f = tmp_py("obj.execfile('foo.py')\n")
        issues = analyzer.analyze_file(f)
        exec_issues = [i for i in issues if i.issue_type == "python2_builtin_execfile"]
        assert len(exec_issues) == 0

    def test_ignores_reload_as_method(self, analyzer: StaticAnalyzer, tmp_py) -> None:
        f = tmp_py("obj.reload()\n")
        issues = analyzer.analyze_file(f)
        rl_issues = [i for i in issues if i.issue_type == "python2_builtin_reload"]
        assert len(rl_issues) == 0

    def test_ignores_comment(self, analyzer: StaticAnalyzer, tmp_py) -> None:
        f = tmp_py("# execfile('old.py')\nx = 1\n")
        issues = analyzer.analyze_file(f)
        exec_issues = [i for i in issues if i.issue_type == "python2_builtin_execfile"]
        assert len(exec_issues) == 0

    def test_detects_file_builtin(self, analyzer: StaticAnalyzer, tmp_py) -> None:
        p = tmp_py("x = 1")
        p.write_text("f = file('data.txt', 'r')\n")
        issues = analyzer.analyze_file(p)
        f_issues = [i for i in issues if i.issue_type == "python2_builtin_file"]
        assert len(f_issues) == 1
        assert f_issues[0].auto_fixable is True

    def test_ignores_file_as_method(self, analyzer: StaticAnalyzer, tmp_py) -> None:
        f = tmp_py("obj.file('data.txt')\n")
        issues = analyzer.analyze_file(f)
        f_issues = [i for i in issues if i.issue_type == "python2_builtin_file"]
        assert len(f_issues) == 0


class TestPy2StdlibModules:
    def test_detects_urllib2(self, analyzer: StaticAnalyzer, tmp_py) -> None:
        p = tmp_py("x = 1")
        p.write_text("import urllib2\n")
        issues = analyzer.analyze_file(p)
        u2_issues = [i for i in issues if i.issue_type == "removed_module_urllib2"]
        assert len(u2_issues) == 1
        assert u2_issues[0].auto_fixable is True

    def test_detects_queue_module(self, analyzer: StaticAnalyzer, tmp_py) -> None:
        p = tmp_py("x = 1")
        p.write_text("import Queue\n")
        issues = analyzer.analyze_file(p)
        q_issues = [i for i in issues if i.issue_type == "removed_module_Queue"]
        assert len(q_issues) == 1

    def test_detects_from_urllib2(self, analyzer: StaticAnalyzer, tmp_py) -> None:
        p = tmp_py("x = 1")
        p.write_text("from urllib2 import urlopen\n")
        issues = analyzer.analyze_file(p)
        u2_issues = [i for i in issues if i.issue_type == "removed_module_urllib2"]
        assert len(u2_issues) == 1


class TestRemovedModuleCommands:
    def test_detects_commands_import(self, analyzer: StaticAnalyzer, tmp_py) -> None:
        f = tmp_py("""\
            import commands
            commands.getoutput("ls")
        """)
        issues = analyzer.analyze_file(f)
        cmd_issues = [i for i in issues if i.issue_type == "removed_module_commands"]
        assert len(cmd_issues) == 1
        assert cmd_issues[0].auto_fixable is True


class TestPython2ExceptComma:
    def test_detects_except_comma(self, analyzer: StaticAnalyzer, tmp_py) -> None:
        p = tmp_py("x = 1")
        p.write_text("try:\n    pass\nexcept ValueError, e:\n    pass\n")
        issues = analyzer.analyze_file(p)
        ec_issues = [i for i in issues if i.issue_type == "python2_except_comma"]
        assert len(ec_issues) == 1
        assert ec_issues[0].auto_fixable is True

    def test_detects_tuple_except_comma(self, analyzer: StaticAnalyzer, tmp_py) -> None:
        p = tmp_py("x = 1")
        p.write_text("try:\n    pass\nexcept (ValueError, TypeError), e:\n    pass\n")
        issues = analyzer.analyze_file(p)
        ec_issues = [i for i in issues if i.issue_type == "python2_except_comma"]
        assert len(ec_issues) == 1

    def test_ignores_except_as(self, analyzer: StaticAnalyzer, tmp_py) -> None:
        f = tmp_py("try:\n    pass\nexcept ValueError as e:\n    pass\n")
        issues = analyzer.analyze_file(f)
        ec_issues = [i for i in issues if i.issue_type == "python2_except_comma"]
        assert len(ec_issues) == 0

    def test_ignores_comment(self, analyzer: StaticAnalyzer, tmp_py) -> None:
        f = tmp_py("# except ValueError, e:\nx = 1\n")
        issues = analyzer.analyze_file(f)
        ec_issues = [i for i in issues if i.issue_type == "python2_except_comma"]
        assert len(ec_issues) == 0


class TestPython2NeOperator:
    def test_detects_ne_operator(self, analyzer: StaticAnalyzer, tmp_py) -> None:
        p = tmp_py("x = 1")
        p.write_text("if x <> y: pass\n")
        issues = analyzer.analyze_file(p)
        ne_issues = [i for i in issues if i.issue_type == "python2_ne_operator"]
        assert len(ne_issues) == 1
        assert ne_issues[0].auto_fixable is True

    def test_ignores_comment(self, analyzer: StaticAnalyzer, tmp_py) -> None:
        f = tmp_py("# x <> y\nx = 1\n")
        issues = analyzer.analyze_file(f)
        ne_issues = [i for i in issues if i.issue_type == "python2_ne_operator"]
        assert len(ne_issues) == 0


class TestPython2DictMethods:
    def test_detects_iteritems(self, analyzer: StaticAnalyzer, tmp_py) -> None:
        f = tmp_py("for k, v in d.iteritems(): pass\n")
        issues = analyzer.analyze_file(f)
        di_issues = [i for i in issues if i.issue_type == "python2_dict_iteritems"]
        assert len(di_issues) == 1
        assert di_issues[0].auto_fixable is True

    def test_detects_itervalues(self, analyzer: StaticAnalyzer, tmp_py) -> None:
        f = tmp_py("for v in d.itervalues(): pass\n")
        issues = analyzer.analyze_file(f)
        dv_issues = [i for i in issues if i.issue_type == "python2_dict_itervalues"]
        assert len(dv_issues) == 1

    def test_detects_iterkeys(self, analyzer: StaticAnalyzer, tmp_py) -> None:
        f = tmp_py("for k in d.iterkeys(): pass\n")
        issues = analyzer.analyze_file(f)
        dk_issues = [i for i in issues if i.issue_type == "python2_dict_iterkeys"]
        assert len(dk_issues) == 1

    def test_ignores_items(self, analyzer: StaticAnalyzer, tmp_py) -> None:
        f = tmp_py("for k, v in d.items(): pass\n")
        issues = analyzer.analyze_file(f)
        di_issues = [i for i in issues if "python2_dict" in i.issue_type]
        assert len(di_issues) == 0


class TestPython2Basestring:
    def test_detects_basestring(self, analyzer: StaticAnalyzer, tmp_py) -> None:
        p = tmp_py("x = 1")
        p.write_text("isinstance(x, basestring)\n")
        issues = analyzer.analyze_file(p)
        bs_issues = [i for i in issues if i.issue_type == "python2_builtin_basestring"]
        assert len(bs_issues) == 1
        assert bs_issues[0].auto_fixable is True

    def test_ignores_comment(self, analyzer: StaticAnalyzer, tmp_py) -> None:
        f = tmp_py("# isinstance(x, basestring)\nx = 1\n")
        issues = analyzer.analyze_file(f)
        bs_issues = [i for i in issues if i.issue_type == "python2_builtin_basestring"]
        assert len(bs_issues) == 0


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
