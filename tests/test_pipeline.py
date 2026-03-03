"""Tests for pipeline helper functions."""

from lazarus.pipeline import _ensure_build_files, _fix_setup_py_build_issues


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

    def test_creates_readme_en_when_referenced(self, tmp_path) -> None:
        setup_py = tmp_path / "setup.py"
        setup_py.write_text(
            "long_desc = open('README_en.md').read()\n"
        )
        created = _ensure_build_files(tmp_path, "1.0.0")
        assert "README_en.md" in created
        assert (tmp_path / "README_en.md").exists()

    def test_creates_changes_when_referenced(self, tmp_path) -> None:
        setup_py = tmp_path / "setup.py"
        setup_py.write_text(
            "history = open('CHANGES.rst').read()\n"
        )
        created = _ensure_build_files(tmp_path, "1.0.0")
        assert "CHANGES.rst" in created

    def test_creates_authors_when_referenced(self, tmp_path) -> None:
        setup_py = tmp_path / "setup.py"
        setup_py.write_text(
            "authors = open('AUTHORS').read()\n"
        )
        created = _ensure_build_files(tmp_path, "1.0.0")
        assert "AUTHORS" in created


class TestFixSetupPyBuildIssues:
    def test_adds_missing_pkg_resources_import(self, tmp_path) -> None:
        setup_py = tmp_path / "setup.py"
        setup_py.write_text(
            "from setuptools import setup\n"
            "version = pkg_resources.get_distribution('foo').version\n"
            "setup(version=version)\n"
        )
        fixes = _fix_setup_py_build_issues(tmp_path)
        assert any("import pkg_resources" in f for f in fixes)
        content = setup_py.read_text()
        assert "import pkg_resources" in content

    def test_does_not_add_if_already_imported(self, tmp_path) -> None:
        setup_py = tmp_path / "setup.py"
        setup_py.write_text(
            "import pkg_resources\n"
            "from setuptools import setup\n"
            "version = pkg_resources.get_distribution('foo').version\n"
            "setup(version=version)\n"
        )
        fixes = _fix_setup_py_build_issues(tmp_path)
        assert not any("import pkg_resources" in f for f in fixes)

    def test_does_not_add_if_from_imported(self, tmp_path) -> None:
        setup_py = tmp_path / "setup.py"
        setup_py.write_text(
            "from pkg_resources import get_distribution\n"
            "version = get_distribution('foo').version\n"
        )
        fixes = _fix_setup_py_build_issues(tmp_path)
        assert not any("import pkg_resources" in f for f in fixes)

    def test_replaces_pip_req_parse_requirements(self, tmp_path) -> None:
        setup_py = tmp_path / "setup.py"
        setup_py.write_text(
            "from pip.req import parse_requirements\n"
            "reqs = parse_requirements('requirements.txt')\n"
            "setup(install_requires=[str(r.req) for r in reqs])\n"
        )
        fixes = _fix_setup_py_build_issues(tmp_path)
        assert any("pip.req" in f for f in fixes)
        content = setup_py.read_text()
        assert "from pip.req import" not in content
        assert "def parse_requirements" in content

    def test_replaces_pip_internal_parse_requirements(self, tmp_path) -> None:
        setup_py = tmp_path / "setup.py"
        setup_py.write_text(
            "from pip._internal.req import parse_requirements\n"
            "reqs = parse_requirements('requirements.txt')\n"
        )
        fixes = _fix_setup_py_build_issues(tmp_path)
        assert any("pip._internal" in f for f in fixes)
        content = setup_py.read_text()
        assert "pip._internal" not in content
        assert "def parse_requirements" in content

    def test_replaces_from_pip_import_main(self, tmp_path) -> None:
        setup_py = tmp_path / "setup.py"
        setup_py.write_text(
            "from pip import main\n"
            "main(['install', 'foo'])\n"
        )
        fixes = _fix_setup_py_build_issues(tmp_path)
        assert any("pip import main" in f for f in fixes)
        content = setup_py.read_text()
        assert "from pip import main" not in content
        assert "subprocess" in content

    def test_replaces_pip_main_call(self, tmp_path) -> None:
        setup_py = tmp_path / "setup.py"
        setup_py.write_text(
            "import pip\n"
            "pip.main(['install', 'foo'])\n"
        )
        fixes = _fix_setup_py_build_issues(tmp_path)
        assert any("pip.main" in f for f in fixes)
        content = setup_py.read_text()
        assert "import pip" not in content
        assert "subprocess" in content

    def test_wraps_bare_import_pip(self, tmp_path) -> None:
        setup_py = tmp_path / "setup.py"
        setup_py.write_text(
            "import pip\n"
            "version = pip.__version__\n"
        )
        fixes = _fix_setup_py_build_issues(tmp_path)
        assert any("try/except" in f for f in fixes)
        content = setup_py.read_text()
        assert "try:" in content
        assert "except ImportError" in content

    def test_no_setup_py(self, tmp_path) -> None:
        fixes = _fix_setup_py_build_issues(tmp_path)
        assert fixes == []

    def test_no_issues(self, tmp_path) -> None:
        setup_py = tmp_path / "setup.py"
        setup_py.write_text(
            "from setuptools import setup\n"
            "setup(name='foo')\n"
        )
        fixes = _fix_setup_py_build_issues(tmp_path)
        assert fixes == []
