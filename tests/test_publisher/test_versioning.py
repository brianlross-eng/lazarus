"""Tests for PEP 440 version rewriting."""

import pytest

from lazarus.publisher.versioning import (
    is_lazarus_version,
    lazarus_version,
    parse_lazarus_version,
    rewrite_version_in_source,
)


class TestLazarusVersion:
    def test_basic_conversion(self) -> None:
        assert lazarus_version("2.31.0") == "2.31.0.post314"

    def test_with_revision(self) -> None:
        assert lazarus_version("2.31.0", revision=1) == "2.31.0.post3141"
        assert lazarus_version("2.31.0", revision=2) == "2.31.0.post3142"

    def test_different_python_target(self) -> None:
        assert lazarus_version("1.0.0", python_target="313") == "1.0.0.post313"

    def test_invalid_version_raises(self) -> None:
        with pytest.raises(Exception):
            lazarus_version("not-a-version")

    def test_strips_existing_post(self) -> None:
        assert lazarus_version("0.1.8.post2") == "0.1.8.post314"

    def test_strips_existing_dev(self) -> None:
        assert lazarus_version("0.1.0.dev20220129") == "0.1.0.post314"

    def test_preserves_pre_release(self) -> None:
        assert lazarus_version("1.0.0a1") == "1.0.0a1.post314"

    def test_four_segment_release(self) -> None:
        assert lazarus_version("3.46.0.6.post1") == "3.46.0.6.post314"


class TestParseLazarusVersion:
    def test_basic_parse(self) -> None:
        base, target, rev = parse_lazarus_version("2.31.0.post314")
        assert base == "2.31.0"
        assert target == "314"
        assert rev == 0

    def test_parse_with_revision(self) -> None:
        base, target, rev = parse_lazarus_version("2.31.0.post3141")
        assert base == "2.31.0"
        assert target == "314"
        assert rev == 1

    def test_not_lazarus_version_raises(self) -> None:
        with pytest.raises(ValueError):
            parse_lazarus_version("2.31.0")

    def test_roundtrip(self) -> None:
        original = "1.5.3"
        lazarus_ver = lazarus_version(original, revision=2)
        base, target, rev = parse_lazarus_version(lazarus_ver)
        assert base == original
        assert target == "314"
        assert rev == 2


class TestIsLazarusVersion:
    def test_positive(self) -> None:
        assert is_lazarus_version("2.31.0.post314") is True
        assert is_lazarus_version("1.0.0.post3142") is True

    def test_negative(self) -> None:
        assert is_lazarus_version("2.31.0") is False
        assert is_lazarus_version("2.31.0.post1") is False  # Too short for Lazarus
        assert is_lazarus_version("garbage") is False


class TestRewriteVersionInSource:
    def test_rewrites_pkg_info(self, tmp_path) -> None:
        pkg_info = tmp_path / "PKG-INFO"
        pkg_info.write_text(
            "Metadata-Version: 2.4\nName: mypkg\nVersion: 1.2.3\n"
        )
        modified = rewrite_version_in_source(tmp_path, "1.2.3.post314")
        assert str(pkg_info) in modified
        assert "Version: 1.2.3.post314" in pkg_info.read_text()

    def test_rewrites_pyproject_toml(self, tmp_path) -> None:
        pp = tmp_path / "pyproject.toml"
        pp.write_text('[project]\nname = "mypkg"\nversion = "1.2.3"\n')
        modified = rewrite_version_in_source(tmp_path, "1.2.3.post314")
        assert str(pp) in modified
        assert 'version = "1.2.3.post314"' in pp.read_text()

    def test_rewrites_setup_cfg(self, tmp_path) -> None:
        cfg = tmp_path / "setup.cfg"
        cfg.write_text("[metadata]\nname = mypkg\nversion = 1.2.3\n")
        modified = rewrite_version_in_source(tmp_path, "1.2.3.post314")
        assert str(cfg) in modified
        assert "version = 1.2.3.post314" in cfg.read_text()

    def test_rewrites_init_dunder_version(self, tmp_path) -> None:
        # Use a subdir without "test" in the name (skip logic checks path)
        source = tmp_path / "src"
        source.mkdir()
        pkg_dir = source / "mypkg"
        pkg_dir.mkdir()
        init = pkg_dir / "__init__.py"
        init.write_text('__version__ = "1.2.3"\n')
        modified = rewrite_version_in_source(source, "1.2.3.post314")
        assert str(init) in modified
        assert '__version__ = "1.2.3.post314"' in init.read_text()

    def test_skips_dynamic_version_init(self, tmp_path) -> None:
        """Packages like pyparsing compute __version__ dynamically."""
        source = tmp_path / "src"
        source.mkdir()
        pkg_dir = source / "mypkg"
        pkg_dir.mkdir()
        init = pkg_dir / "__init__.py"
        init.write_text(
            "__version_info__ = (3, 3, 2)\n"
            "__version__ = __version_info__.__version__\n"
        )
        # No quoted __version__ = "..." so regex won't match
        modified = rewrite_version_in_source(source, "3.3.2.post314")
        assert str(init) not in modified

    def test_converts_dynamic_version_to_static(self, tmp_path) -> None:
        """Packages with dynamic = ['version'] get it set statically."""
        pp = tmp_path / "pyproject.toml"
        pp.write_text(
            '[project]\n'
            'name = "mypkg"\n'
            'dynamic = ["version", "description"]\n'
        )
        modified = rewrite_version_in_source(tmp_path, "3.3.2.post314")
        assert str(pp) in modified
        content = pp.read_text()
        assert 'version = "3.3.2.post314"' in content
        assert '"version"' not in content  # removed from dynamic
        assert '"description"' in content  # kept other dynamic fields

    def test_converts_version_only_dynamic(self, tmp_path) -> None:
        """When version is the only dynamic field, remove dynamic entirely."""
        pp = tmp_path / "pyproject.toml"
        pp.write_text(
            '[project]\n'
            'name = "mypkg"\n'
            'dynamic = ["version"]\n'
        )
        modified = rewrite_version_in_source(tmp_path, "1.0.0.post314")
        content = pp.read_text()
        assert 'version = "1.0.0.post314"' in content
        assert "dynamic" not in content

    def test_dynamic_version_not_first_item(self, tmp_path) -> None:
        """version as non-first item in dynamic list (urwid-style)."""
        pp = tmp_path / "pyproject.toml"
        pp.write_text(
            '[project]\n'
            'name = "urwid"\n'
            'dynamic = ["classifiers", "version", "dependencies"]\n'
        )
        modified = rewrite_version_in_source(tmp_path, "3.0.5.post314")
        content = pp.read_text()
        assert 'version = "3.0.5.post314"' in content
        assert '"version"' not in content
        assert '"classifiers"' in content
        assert '"dependencies"' in content

    def test_dynamic_version_last_item(self, tmp_path) -> None:
        """version as last item in dynamic list."""
        pp = tmp_path / "pyproject.toml"
        pp.write_text(
            '[project]\n'
            'name = "mypkg"\n'
            'dynamic = ["description", "version"]\n'
        )
        modified = rewrite_version_in_source(tmp_path, "1.0.0.post314")
        content = pp.read_text()
        assert 'version = "1.0.0.post314"' in content
        assert '"version"' not in content
        assert '"description"' in content

    def test_does_not_corrupt_join_version(self, tmp_path) -> None:
        """__version__ = ".".join(...) must not be rewritten."""
        source = tmp_path / "src"
        source.mkdir()
        pkg_dir = source / "mypkg"
        pkg_dir.mkdir()
        init = pkg_dir / "__init__.py"
        init.write_text(
            'version_info = (3, 2, 0)\n'
            '__version__ = ".".join(str(x) for x in version_info)\n'
        )
        modified = rewrite_version_in_source(source, "3.2.0.post314")
        assert str(init) not in modified
        content = init.read_text()
        assert '".".join' in content

    def test_does_not_rewrite_minversion_in_setup_cfg(self, tmp_path) -> None:
        """minversion in setup.cfg must not be rewritten."""
        cfg = tmp_path / "setup.cfg"
        cfg.write_text(
            "[metadata]\n"
            "version = 1.0.0\n"
            "\n"
            "[tool:pytest]\n"
            "minversion = 6.0\n"
        )
        rewrite_version_in_source(tmp_path, "1.0.0.post314")
        content = cfg.read_text()
        assert "version = 1.0.0.post314" in content
        assert "minversion = 6.0" in content

    def test_does_not_rewrite_local_version_in_pyproject(self, tmp_path) -> None:
        """local_version and fallback_version must not be rewritten."""
        pp = tmp_path / "pyproject.toml"
        pp.write_text(
            '[project]\n'
            'name = "mypkg"\n'
            'version = "2.0.0"\n'
            '\n'
            '[tool.setuptools_scm]\n'
            'local_version = "no-local-version"\n'
            'fallback_version = "0.0.0"\n'
        )
        rewrite_version_in_source(tmp_path, "2.0.0.post314")
        content = pp.read_text()
        assert 'version = "2.0.0.post314"' in content
        assert 'local_version = "no-local-version"' in content
        assert 'fallback_version = "0.0.0"' in content
