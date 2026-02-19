"""Tests for PEP 440 version rewriting."""

import pytest

from lazarus.publisher.versioning import (
    is_lazarus_version,
    lazarus_version,
    parse_lazarus_version,
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
