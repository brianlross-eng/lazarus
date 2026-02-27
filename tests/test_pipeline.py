"""Tests for pipeline helper functions."""

from lazarus.pipeline import _ensure_build_files


class TestEnsureBuildFiles:
    def test_creates_requirements_txt_when_referenced(self, tmp_path) -> None:
        setup_py = tmp_path / "setup.py"
        setup_py.write_text(
            "from setuptools import setup\n"
            "reqs = open('requirements.txt').read().splitlines()\n"
            "setup(install_requires=reqs)\n"
        )
        created = _ensure_build_files(tmp_path, "1.0.0")
        assert "requirements.txt" in created
        assert (tmp_path / "requirements.txt").exists()
        assert (tmp_path / "requirements.txt").read_text() == ""

    def test_does_not_create_unreferenced_files(self, tmp_path) -> None:
        setup_py = tmp_path / "setup.py"
        setup_py.write_text("from setuptools import setup\nsetup()\n")
        created = _ensure_build_files(tmp_path, "1.0.0")
        assert created == []
        assert not (tmp_path / "requirements.txt").exists()

    def test_creates_readme_when_referenced(self, tmp_path) -> None:
        setup_py = tmp_path / "setup.py"
        setup_py.write_text(
            "long_desc = open('README.md').read()\n"
            "setup(long_description=long_desc)\n"
        )
        created = _ensure_build_files(tmp_path, "1.0.0")
        assert "README.md" in created
        assert (tmp_path / "README.md").exists()

    def test_creates_version_file_with_version(self, tmp_path) -> None:
        setup_py = tmp_path / "setup.py"
        setup_py.write_text(
            "version = open('VERSION').read().strip()\n"
            "setup(version=version)\n"
        )
        created = _ensure_build_files(tmp_path, "2.0.0.post314")
        assert "VERSION" in created
        assert (tmp_path / "VERSION").read_text() == "2.0.0.post314"

    def test_does_not_overwrite_existing_files(self, tmp_path) -> None:
        setup_py = tmp_path / "setup.py"
        setup_py.write_text("reqs = open('requirements.txt').read()\n")
        reqs = tmp_path / "requirements.txt"
        reqs.write_text("flask>=2.0\n")
        created = _ensure_build_files(tmp_path, "1.0.0")
        assert "requirements.txt" not in created
        assert reqs.read_text() == "flask>=2.0\n"

    def test_creates_subdir_requirements(self, tmp_path) -> None:
        """Handles tests/requirements.txt, docs/requirements.txt, etc."""
        setup_py = tmp_path / "setup.py"
        setup_py.write_text(
            "reqs = open('tests/requirements.txt').read()\n"
        )
        created = _ensure_build_files(tmp_path, "1.0.0")
        assert "tests/requirements.txt" in created
        assert (tmp_path / "tests" / "requirements.txt").exists()

    def test_creates_version_txt(self, tmp_path) -> None:
        setup_py = tmp_path / "setup.py"
        setup_py.write_text(
            "version = open('version.txt').read().strip()\n"
        )
        created = _ensure_build_files(tmp_path, "1.5.0.post314")
        assert "version.txt" in created
        assert (tmp_path / "version.txt").read_text() == "1.5.0.post314"
