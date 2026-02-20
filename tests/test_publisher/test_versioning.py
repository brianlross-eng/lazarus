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
        pkg_dir = tmp_path / "mypkg"
        pkg_dir.mkdir()
        init = pkg_dir / "__init__.py"
        init.write_text(
            "__version_info__ = (3, 3, 2)\n"
            "__version__ = __version_info__.__version__\n"
        )
        # No quoted __version__ = "..." so regex won't match
        modified = rewrite_version_in_source(tmp_path, "3.3.2.post314")
        assert str(init) not in modified
