"""Tests for PyPI client — archive extraction."""

import os
import tarfile
import zipfile

import pytest

from lazarus.pypi.client import PyPIClient, PyPIError


@pytest.fixture
def client(tmp_path):
    cache_dir = tmp_path / "cache"
    return PyPIClient(cache_dir=cache_dir)


def _make_tar(archive_path, mode, files, *, symlink=None):
    """Create a tar archive with the given files and optional symlink."""
    with tarfile.open(archive_path, mode) as tar:
        for name, content in files.items():
            import io

            data = content.encode()
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        if symlink:
            link_name, target = symlink
            info = tarfile.TarInfo(name=link_name)
            info.type = tarfile.SYMTYPE
            info.linkname = target
            tar.addfile(info)


class TestExtractSdist:
    def test_extracts_tar_gz(self, client, tmp_path):
        archive = tmp_path / "pkg-1.0.tar.gz"
        _make_tar(archive, "w:gz", {"pkg-1.0/setup.py": "setup()"})
        dest = tmp_path / "out"
        result = client.extract_sdist(archive, dest)
        assert (result / "setup.py").exists()
        assert (result / "setup.py").read_text() == "setup()"

    def test_extracts_tar_bz2(self, client, tmp_path):
        archive = tmp_path / "pkg-1.0.tar.bz2"
        _make_tar(archive, "w:bz2", {"pkg-1.0/setup.py": "setup()"})
        dest = tmp_path / "out"
        result = client.extract_sdist(archive, dest)
        assert (result / "setup.py").exists()
        assert (result / "setup.py").read_text() == "setup()"

    def test_extracts_tar_xz(self, client, tmp_path):
        archive = tmp_path / "pkg-1.0.tar.xz"
        _make_tar(archive, "w:xz", {"pkg-1.0/setup.py": "setup()"})
        dest = tmp_path / "out"
        result = client.extract_sdist(archive, dest)
        assert (result / "setup.py").exists()
        assert (result / "setup.py").read_text() == "setup()"

    def test_extracts_zip(self, client, tmp_path):
        archive = tmp_path / "pkg-1.0.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("pkg-1.0/setup.py", "setup()")
        dest = tmp_path / "out"
        result = client.extract_sdist(archive, dest)
        assert (result / "setup.py").exists()

    def test_unknown_format_raises(self, client, tmp_path):
        archive = tmp_path / "pkg-1.0.rar"
        archive.write_bytes(b"not a real archive")
        dest = tmp_path / "out"
        with pytest.raises(PyPIError, match="Unknown archive format"):
            client.extract_sdist(archive, dest)

    def test_symlinks_skipped_tar_gz(self, client, tmp_path):
        archive = tmp_path / "pkg-1.0.tar.gz"
        _make_tar(
            archive,
            "w:gz",
            {"pkg-1.0/real.py": "print('hello')"},
            symlink=("pkg-1.0/link.py", "/etc/passwd"),
        )
        dest = tmp_path / "out"
        result = client.extract_sdist(archive, dest)
        # Real file extracted
        assert (result / "real.py").exists()
        # Symlink silently skipped
        assert not (result / "link.py").exists()

    def test_symlinks_skipped_tar_bz2(self, client, tmp_path):
        archive = tmp_path / "pkg-1.0.tar.bz2"
        _make_tar(
            archive,
            "w:bz2",
            {"pkg-1.0/real.py": "print('hello')"},
            symlink=("pkg-1.0/link.py", "/usr/bin/python"),
        )
        dest = tmp_path / "out"
        result = client.extract_sdist(archive, dest)
        assert (result / "real.py").exists()
        assert not (result / "link.py").exists()

    def test_returns_single_subdir(self, client, tmp_path):
        """When archive has a single top-level dir, return that dir."""
        archive = tmp_path / "pkg-1.0.tar.gz"
        _make_tar(archive, "w:gz", {"pkg-1.0/setup.py": "setup()"})
        dest = tmp_path / "out"
        result = client.extract_sdist(archive, dest)
        assert result.name == "pkg-1.0"

    def test_returns_dest_for_multiple_subdirs(self, client, tmp_path):
        """When archive has multiple top-level dirs, return dest."""
        archive = tmp_path / "weird.tar.gz"
        _make_tar(
            archive,
            "w:gz",
            {"dir1/a.py": "a", "dir2/b.py": "b"},
        )
        dest = tmp_path / "out"
        result = client.extract_sdist(archive, dest)
        assert result == dest
