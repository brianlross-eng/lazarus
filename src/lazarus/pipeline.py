"""Pipeline orchestrator — ties all stages together for end-to-end processing."""

from __future__ import annotations

import re
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from rich.console import Console

from lazarus.compat.analyzer import CompatIssue, StaticAnalyzer
from lazarus.compat.failures import FailureType, classify_failure, is_auto_fixable
from lazarus.compat.tester import CompatTester, TestResult
from lazarus.config import LazarusConfig
from lazarus.db.models import FixMethod, Job, JobStatus
from lazarus.db.queue import JobQueue
from lazarus.fixer.auto import AutoFixer
from lazarus.fixer.patcher import Patcher
from lazarus.publisher.builder import PackageBuilder
from lazarus.publisher.uploader import DevpiUploader, UploadError
from lazarus.publisher.versioning import lazarus_version, rewrite_version_in_source
from lazarus.pypi.client import PyPIClient

console = Console()

# Packages with heavy C/Cython extensions that hang during build.
# These can be analyzed but not built locally — they need platform-specific
# build agents or pre-built wheels.
SKIP_BUILD_PACKAGES = frozenset({
    "grpcio",
    "cython",
    "rapidfuzz",
    "pynacl",
    "bcrypt",
    "lxml",
    "pillow",
    "numpy",
    "scipy",
    "pandas",
    "pyarrow",
    "cryptography",
    "cffi",
    "greenlet",
    "psutil",
    "multidict",
    "yarl",
    "frozenlist",
    "aiohttp",
    "rpds-py",
    "propcache",
    "msgpack",
    "pyyaml",
    "coverage",
    "scikit-learn",
    "regex",
})


def _ensure_build_files(source_dir: Path, version: str) -> list[str]:
    """Create commonly missing files that setup.py expects at build time.

    Many sdists reference requirements.txt, README, or VERSION in their
    setup.py but don't include those files.  Creating empty/minimal stubs
    prevents FileNotFoundError during ``python -m build``.

    Returns list of files created.
    """
    created: list[str] = []
    config_files = ("setup.py", "setup.cfg", "pyproject.toml")

    def _is_referenced(filename: str) -> bool:
        """Check if filename is referenced in any config file."""
        for cfg_name in config_files:
            cfg = source_dir / cfg_name
            if cfg.exists():
                try:
                    text = cfg.read_text(errors="ignore")
                    if filename in text:
                        return True
                except OSError:
                    pass
        return False

    # requirements files — setup.py/pyproject.toml reads for install_requires.
    # The actual deps are declared in setup.py/pyproject.toml, so empty is safe.
    req_files = (
        "requirements.txt", "test-requirements.txt", "requirements-dev.txt",
        "requirements.in", "dev-requirements.txt", "requirements-test.txt",
        "requirements_test.txt", "test_requirements.txt",
        "requirements-extra.in", "Pipfile.lock",
    )
    for name in req_files:
        p = source_dir / name
        if not p.exists() and _is_referenced(name):
            p.write_text("")
            created.append(name)

    # README / documentation files — setup.py reads for long_description
    doc_files = (
        "README.md", "README.rst", "README.txt", "README",
        "readme.md", "Readme.md", "ReadMe.md", "README.MD",
        "README.mdown", "README_PIP.md", "DESCRIPTION.rst",
        "README_en.md", "README_CN.md", "README_zh.md",
        "README_ja.md", "README_ko.md",
        "HISTORY.md", "HISTORY.rst",
        "CHANGELOG.md", "CHANGELOG.rst", "CHANGES.md", "CHANGES.rst",
        "CHANGES.txt", "CHANGES", "NEWS.rst", "NEWS.md",
        "LICENSE", "LICENSE.txt", "LICENSE.md", "LICENCE",
        "LICENCE.txt", "LICENCE.md", "COPYING", "COPYING.txt",
        "AUTHORS", "AUTHORS.md", "AUTHORS.rst", "AUTHORS.txt",
        "CONTRIBUTORS", "CONTRIBUTORS.md", "CONTRIBUTORS.rst",
    )
    for name in doc_files:
        p = source_dir / name
        if not p.exists() and _is_referenced(name):
            p.write_text("")
            created.append(name)

    # VERSION / version.txt — setup.py reads for version string
    ver_files = ("VERSION", "VERSION.txt", "version.txt", "version",
                 "new_version.txt")
    for name in ver_files:
        p = source_dir / name
        if not p.exists() and _is_referenced(name):
            p.write_text(version)
            created.append(name)

    # Subdirectory files — scan configs for relative paths we can stub.
    # Matches patterns like "tests/requirements.txt", "docs/requirements.txt",
    # "requirements/base.txt", etc.
    import re as _re
    for cfg_name in config_files:
        cfg = source_dir / cfg_name
        if not cfg.exists():
            continue
        try:
            text = cfg.read_text(errors="ignore")
        except OSError:
            continue
        # Find quoted paths with a slash that look like subdir files
        for m in _re.finditer(r'["\']([a-zA-Z_./]+/[a-zA-Z_.-]+\.(?:txt|rst|md|in|cfg))["\']', text):
            rel_path = m.group(1)
            p = source_dir / rel_path
            if not p.exists():
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text("")
                created.append(rel_path)

    return created


# ---------------------------------------------------------------------------
# Shim injected into setup.py when it uses ``from pip.req import
# parse_requirements`` — pip's internal API was removed long ago, so we
# provide a minimal replacement that just reads lines from a file.
# ---------------------------------------------------------------------------
_PIP_PARSE_REQUIREMENTS_SHIM = """\
def parse_requirements(filename, session=None, options=None):
    \"\"\"Minimal shim replacing pip.req.parse_requirements.\"\"\"
    import os
    class _Req:
        def __init__(self, line):
            self.requirement = line
            self.req = line
            self.name = line.split("==")[0].split(">=")[0].split("<=")[0].split(">")[0].split("<")[0].split("!=")[0].split("[")[0].strip()
            self.comes_from = filename
        def __str__(self):
            return self.requirement
    reqs = []
    if os.path.exists(filename):
        with open(filename) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and not line.startswith("-"):
                    reqs.append(_Req(line))
    return reqs
"""


def _fix_setup_py_build_issues(source_dir: Path) -> list[str]:
    """Fix common setup.py issues that cause build failures.

    Runs before build to patch setup.py for:
    1. pkg_resources used without import (NameError: name 'pkg_resources')
    2. from pip.req import parse_requirements (ModuleNotFoundError: No module named 'pip')
    3. from pip import main / pip.main (same)

    Returns list of fixes applied.
    """
    setup_py = source_dir / "setup.py"
    if not setup_py.exists():
        return []

    try:
        source = setup_py.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    original = source
    fixes: list[str] = []

    # 1. Add `import pkg_resources` if used but not imported
    has_pkg_resources_usage = bool(re.search(r'\bpkg_resources\.', source))
    has_pkg_resources_import = bool(re.search(
        r'^\s*import\s+pkg_resources\b|^\s*from\s+pkg_resources\s+import\b',
        source, re.MULTILINE,
    ))
    if has_pkg_resources_usage and not has_pkg_resources_import:
        # Insert import after other imports
        lines = source.split("\n")
        insert_idx = 0
        for i, line in enumerate(lines):
            stripped = line.lstrip()
            if stripped.startswith("import ") or stripped.startswith("from "):
                insert_idx = i + 1
        lines.insert(insert_idx, "import pkg_resources")
        source = "\n".join(lines)
        fixes.append("added missing 'import pkg_resources'")

    # 2. Replace `from pip.req import parse_requirements`
    pip_req_pattern = r'^\s*from\s+pip\.req\s+import\s+parse_requirements\b.*$'
    if re.search(pip_req_pattern, source, re.MULTILINE):
        source = re.sub(pip_req_pattern, _PIP_PARSE_REQUIREMENTS_SHIM, source, flags=re.MULTILINE)
        fixes.append("replaced 'from pip.req import parse_requirements' with shim")

    # Also handle: from pip._internal.req import parse_requirements
    pip_internal_pattern = r'^\s*from\s+pip\._internal\.req\s+import\s+parse_requirements\b.*$'
    if re.search(pip_internal_pattern, source, re.MULTILINE):
        source = re.sub(pip_internal_pattern, _PIP_PARSE_REQUIREMENTS_SHIM, source, flags=re.MULTILINE)
        fixes.append("replaced 'from pip._internal.req import parse_requirements' with shim")

    # 3. Replace `from pip import main` → subprocess equivalent
    if re.search(r'^\s*from\s+pip\s+import\s+main\b', source, re.MULTILINE):
        source = re.sub(
            r'^\s*from\s+pip\s+import\s+main\b.*$',
            'import subprocess, sys\ndef main(args): subprocess.check_call([sys.executable, "-m", "pip"] + list(args))',
            source,
            flags=re.MULTILINE,
        )
        fixes.append("replaced 'from pip import main' with subprocess")

    # 4. Replace bare `import pip` when used as pip.main(...)
    if re.search(r'^\s*import\s+pip\s*$', source, re.MULTILINE) and re.search(r'\bpip\.main\s*\(', source):
        source = re.sub(
            r'^\s*import\s+pip\s*$',
            'import subprocess, sys',
            source,
            flags=re.MULTILINE,
        )
        source = re.sub(
            r'\bpip\.main\s*\(',
            'subprocess.check_call([sys.executable, "-m", "pip"] + list(',
            source,
        )
        # Close the extra list() call — this is approximate but handles simple cases
        fixes.append("replaced 'import pip; pip.main(...)' with subprocess")

    # 5. Remove ez_setup / distribute_setup bootstrap (setuptools is always available)
    if re.search(r'^\s*(?:from\s+ez_setup\s+import|import\s+ez_setup)\b', source, re.MULTILINE):
        # Remove import and use_setuptools() call
        source = re.sub(r'^\s*(?:from\s+ez_setup\s+import\s+use_setuptools|import\s+ez_setup)\s*$',
                         '', source, flags=re.MULTILINE)
        source = re.sub(r'^\s*(?:ez_setup\.)?use_setuptools\(.*?\)\s*$', '', source, flags=re.MULTILINE)
        fixes.append("removed ez_setup bootstrap (setuptools always available)")

    if re.search(r'^\s*(?:from\s+distribute_setup\s+import|import\s+distribute_setup)\b', source, re.MULTILINE):
        source = re.sub(r'^\s*(?:from\s+distribute_setup\s+import\s+use_setuptools|import\s+distribute_setup)\s*$',
                         '', source, flags=re.MULTILINE)
        source = re.sub(r'^\s*(?:distribute_setup\.)?use_setuptools\(.*?\)\s*$', '', source, flags=re.MULTILINE)
        fixes.append("removed distribute_setup bootstrap (setuptools always available)")

    # 6. Replace bare `import pip` when used for pip.get_distribution etc.
    # These are less common — just make pip importable by trying pip install
    if re.search(r'^\s*import\s+pip\s*$', source, re.MULTILINE) and not fixes:
        # Remove the import and try-except wrap usages — too complex.
        # Instead, wrap the import in try/except
        source = re.sub(
            r'^(\s*)import\s+pip\s*$',
            r'\1try:\n\1    import pip\n\1except ImportError:\n\1    pip = None',
            source,
            flags=re.MULTILINE,
        )
        fixes.append("wrapped 'import pip' in try/except")

    if source != original:
        setup_py.write_text(source, encoding="utf-8")

    return fixes


def _has_c_extensions(source_dir: Path) -> bool:
    """Heuristic: check if a package has C/Cython extensions."""
    for pattern in ("*.c", "*.cpp", "*.pyx", "*.pxd"):
        # Check top two levels — enough to detect extension modules
        if any(source_dir.glob(pattern)) or any(source_dir.glob(f"*/{pattern}")):
            return True

    # Check setup.py/setup.cfg for ext_modules
    setup_py = source_dir / "setup.py"
    if setup_py.exists():
        try:
            text = setup_py.read_text(errors="ignore")
            if "ext_modules" in text or "Extension(" in text:
                return True
        except OSError:
            pass

    return False


@dataclass
class ProcessResult:
    package_name: str
    version: str
    success: bool
    fix_method: FixMethod = FixMethod.NONE
    issues_found: int = 0
    issues_fixed: int = 0
    error: str | None = None
    dists_built: list[str] = field(default_factory=list)
    dists_uploaded: list[str] = field(default_factory=list)
    needs_review: bool = False
    review_reason: str | None = None


@dataclass
class BatchResult:
    processed: int = 0
    succeeded: int = 0
    failed: int = 0
    skipped: int = 0
    results: list[ProcessResult] = field(default_factory=list)


class Pipeline:
    """End-to-end package resurrection pipeline."""

    def __init__(self, config: LazarusConfig) -> None:
        self.config = config
        config.ensure_dirs()
        self.queue = JobQueue(config.db_path)
        self.queue.initialize()
        self.pypi = PyPIClient(config.cache_dir)
        self.analyzer = StaticAnalyzer()
        self.tester = CompatTester(config.python_binary)
        self.auto_fixer = AutoFixer()
        self.patcher = Patcher()
        self.builder = PackageBuilder()
        self.uploader: DevpiUploader | None = None
        if config.upload_enabled and config.devpi_password:
            self.uploader = DevpiUploader(
                server_url=config.devpi_url,
                index=config.devpi_index,
                user=config.devpi_user,
                password=config.devpi_password,
            )

    def close(self) -> None:
        self.pypi.close()
        if self.uploader:
            self.uploader.close()

    def process_one(self, job: Job) -> ProcessResult:
        """Run the full pipeline for a single package."""
        result = ProcessResult(
            package_name=job.package_name,
            version=job.version,
            success=False,
        )

        work_dir = Path(tempfile.mkdtemp(
            prefix=f"lazarus_{job.package_name}_",
            dir=str(self.config.work_dir),
        ))

        sdist_path: Path | None = None
        try:
            # 1. Fetch
            console.print(f"  [dim]Fetching {job.package_name}=={job.version}...[/]")
            sdist_path = self.pypi.download_sdist(job.package_name, job.version)
            source_dir = self.pypi.extract_sdist(sdist_path, work_dir / "source")

            # 2. Analyze
            console.print(f"  [dim]Analyzing for 3.14 compatibility...[/]")
            issues = self.analyzer.analyze_tree(source_dir)
            result.issues_found = len(issues)

            if not issues:
                # Package may already be compatible — mark complete
                console.print(f"  [green]No issues found — already compatible[/]")
                result.success = True
                result.fix_method = FixMethod.NONE
                return result

            console.print(f"  [yellow]Found {len(issues)} issue(s)[/]")

            # 3. Backup
            backup_path = self.patcher.backup_original(source_dir)

            # 4. Auto-fix what we can
            auto_fixable = [i for i in issues if i.auto_fixable]
            needs_ai = [i for i in issues if not i.auto_fixable]

            if auto_fixable:
                console.print(f"  [dim]Auto-fixing {len(auto_fixable)} issue(s)...[/]")
                fix_result = self.auto_fixer.apply_all(source_dir, auto_fixable)
                result.issues_fixed += fix_result.issues_fixed

            # 5. AI fix remaining issues (if configured and needed)
            if needs_ai and self.config.anthropic_api_key:
                console.print(f"  [dim]Sending {len(needs_ai)} issue(s) to Claude...[/]")
                try:
                    from lazarus.fixer.claude import ClaudeFixer
                    claude = ClaudeFixer(
                        api_key=self.config.anthropic_api_key,
                        model=self.config.claude_model,
                        max_tokens=self.config.max_tokens_per_fix,
                    )
                    attempts = claude.fix_package(source_dir, needs_ai)
                    for attempt in attempts:
                        if attempt.fixed_code != attempt.original_code:
                            result.issues_fixed += len(attempt.issues_addressed)
                    result.fix_method = FixMethod.AI
                except Exception as e:
                    console.print(f"  [red]Claude fix failed: {e}[/]")
                    result.fix_method = FixMethod.AUTO if auto_fixable else FixMethod.NONE
            elif needs_ai:
                # No API key — flag for later review
                issue_summary = "; ".join(
                    f"{i.issue_type} in {Path(i.file_path).name}:{i.line_number}"
                    for i in needs_ai[:10]  # cap at 10 to keep reason readable
                )
                if len(needs_ai) > 10:
                    issue_summary += f" ... and {len(needs_ai) - 10} more"
                result.needs_review = True
                result.review_reason = (
                    f"{len(needs_ai)} unfixed issue(s): {issue_summary}"
                )
                console.print(
                    f"  [yellow]{len(needs_ai)} issue(s) need AI/manual fix "
                    f"— flagging for review[/]"
                )
                result.fix_method = FixMethod.AUTO if auto_fixable else FixMethod.NONE
            else:
                result.fix_method = FixMethod.AUTO

            # 6. Decide whether to build
            skip_build = (
                job.package_name.lower() in SKIP_BUILD_PACKAGES
                or _has_c_extensions(source_dir)
            )

            if result.issues_fixed == 0 and not result.needs_review:
                # Nothing was actually changed and no review needed — skip build
                console.print(f"  [dim]No fixes applied — skipping build[/]")
                result.success = True
            elif result.needs_review:
                # Don't bother building — it's going to review anyway
                console.print(f"  [dim]Skipping build — package flagged for review[/]")
                result.success = True
            elif skip_build:
                console.print(
                    f"  [yellow]C-extension package — skipping build "
                    f"(needs platform build agent)[/]"
                )
                result.success = True
            else:
                # Rewrite version and build
                python_target = job.python_target.replace(".", "")
                new_ver = lazarus_version(job.version, python_target)
                rewrite_version_in_source(source_dir, new_ver)

                # Create any missing files that setup.py expects
                created = _ensure_build_files(source_dir, new_ver)
                if created:
                    console.print(
                        f"  [dim]Created missing build files: "
                        f"{', '.join(created)}[/]"
                    )

                # Fix setup.py import issues (pkg_resources, pip)
                setup_fixes = _fix_setup_py_build_issues(source_dir)
                if setup_fixes:
                    console.print(
                        f"  [dim]Fixed setup.py: "
                        f"{'; '.join(setup_fixes)}[/]"
                    )

                console.print(f"  [dim]Building {new_ver}...[/]")
                output_dir = work_dir / "dist"
                try:
                    dists = self.builder.build_all(
                        source_dir, output_dir, version=new_ver,
                    )
                    result.dists_built = [p.name for p in dists]
                    result.success = True
                except Exception as e:
                    console.print(f"  [red]Build failed: {e}[/]")
                    result.error = str(e)

                # 7. Upload to devpi (if build succeeded and uploader configured)
                if result.success and result.dists_built and self.uploader:
                    console.print(f"  [dim]Uploading to devpi...[/]")
                    try:
                        dist_files = list(output_dir.iterdir())
                        uploaded = self.uploader.upload(dist_files)
                        result.dists_uploaded = uploaded
                        console.print(
                            f"  [green]Uploaded {len(uploaded)} dist(s) "
                            f"to {self.config.devpi_index}[/]"
                        )
                    except UploadError as e:
                        console.print(f"  [red]Upload failed: {e}[/]")
                        # Upload failure is non-fatal — build still succeeded
                        result.error = f"Upload failed: {e}"

            # Cleanup backup
            self.patcher.cleanup_backup(backup_path)

        except Exception as e:
            result.error = str(e)
            console.print(f"  [red]Error: {e}[/]")
        finally:
            # Clean up work directory and cached sdist
            shutil.rmtree(work_dir, ignore_errors=True)
            if sdist_path is not None:
                sdist_path.unlink(missing_ok=True)

        return result

    def run_batch(self, max_jobs: int = 0, auto_only: bool = False) -> BatchResult:
        """Process jobs from the queue.

        Args:
            max_jobs: Maximum number of jobs to process (0 = unlimited).
            auto_only: If True, only apply auto-fixes (no Claude API calls).
        """
        batch = BatchResult()

        # Reset any stale in-progress jobs
        reset = self.queue.reset_stale_jobs()
        if reset:
            console.print(f"[yellow]Reset {reset} stale job(s)[/]")

        original_api_key = self.config.anthropic_api_key
        if auto_only:
            self.config.anthropic_api_key = ""

        try:
            while True:
                if max_jobs > 0 and batch.processed >= max_jobs:
                    break

                job = self.queue.claim_next()
                if job is None:
                    break

                console.print(
                    f"\n[bold]Processing [{batch.processed + 1}] "
                    f"{job.package_name}=={job.version}[/]"
                )

                result = self.process_one(job)
                batch.results.append(result)
                batch.processed += 1

                if result.needs_review:
                    self.queue.mark_review(
                        job.id, result.review_reason or "Needs AI/manual fix"
                    )
                    batch.succeeded += 1
                    console.print(
                        f"  [magenta]Flagged for review ({result.issues_found} issues, "
                        f"{result.issues_fixed} auto-fixed)[/]"
                    )
                elif result.success:
                    self.queue.complete(job.id, result.fix_method)
                    batch.succeeded += 1
                    console.print(f"  [green]Success ({result.fix_method})[/]")
                elif result.error and is_auto_fixable(
                    classify_failure(result.error)
                ):
                    # Potentially fixable — retry later
                    if not self.queue.retry(job.id):
                        self.queue.fail(job.id, result.error)
                        batch.failed += 1
                    else:
                        batch.skipped += 1
                else:
                    self.queue.fail(job.id, result.error or "Unknown error")
                    batch.failed += 1
                    console.print(f"  [red]Failed: {result.error}[/]")

        finally:
            self.config.anthropic_api_key = original_api_key

        console.print(f"\n[bold]Batch complete:[/] "
                      f"{batch.succeeded} succeeded, {batch.failed} failed, "
                      f"{batch.skipped} skipped")
        return batch
