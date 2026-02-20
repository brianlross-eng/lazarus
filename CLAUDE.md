# Lazarus Project — Claude Memory

## What This Project Is
PyPI-compatible proxy repository that automatically resurrects Python packages broken by Python 3.14 incompatibility. Pulls packages from PyPI, detects compatibility issues (AST-based static analysis), fixes them (auto-fix or Claude AI), rebuilds, and republishes with `.post314` version suffixes.

## Version
- **Current**: 1.0.0a1 (Alpha)
- **Versioning**: PEP 440 + SemVer — track changes in `CHANGELOG.md`
- **Tags**: `v1.0.0a1`, etc.

## Repository
- GitHub: https://github.com/brianlross-eng/lazarus
- Branch: `master`
- Python: 3.14 (the target platform)
- Package layout: `src/lazarus/` with `pyproject.toml`

## Key Commands
```bash
# Run all tests (96 tests, should all pass)
python -m pytest -v

# CLI (must use python -m until pip install -e . is done)
python -m lazarus admin status          # Queue stats
python -m lazarus admin errors           # Show common error patterns from failed jobs
python -m lazarus admin reviews         # Show packages needing AI/manual fix
python -m lazarus admin process --auto-only  # Process queue (auto-fixes only)
python -m lazarus admin watchdog        # Supervisor process
python -m lazarus admin seed --count 1000    # Seed queue from top PyPI packages

# Useful direct DB queries
python -c "from lazarus.config import LazarusConfig; from lazarus.db.queue import JobQueue; q = JobQueue(LazarusConfig().db_path); q.initialize(); print(q.get_status()); q.close()"
```

## Architecture
```
src/lazarus/
├── cli.py              # Click CLI with raise/remove/search/list/inspect/pray + admin commands
├── config.py           # LazarusConfig dataclass, paths, API keys
├── pipeline.py         # Orchestrator: fetch → analyze → fix → build (ProcessResult, BatchResult)
├── watchdog.py         # Supervisor: monitors stale jobs, auto-restarts processor
├── db/
│   ├── models.py       # Job, JobStatus enum, FixMethod enum
│   ├── queue.py        # JobQueue: SQLite CRUD, claim_next, status transitions
│   └── migrations.py   # Integer-versioned schema migrations
├── pypi/
│   ├── client.py       # PyPI JSON API, download/extract sdists (httpx)
│   ├── top_packages.py # Fetch top-N from hugovk dataset
│   └── metadata.py     # PackageMetadata, VersionMetadata dataclasses
├── compat/
│   ├── analyzer.py     # AST-based static analysis (11 check types)
│   ├── tester.py       # Run tests in isolated 3.14 venvs
│   └── failures.py     # Failure classification
├── fixer/
│   ├── auto.py         # Mechanical fixes (7 fix types including escape sequences)
│   ├── claude.py       # Claude API for complex fixes
│   └── patcher.py      # Backup/restore for safe patching
├── publisher/
│   ├── versioning.py   # PEP 440 .post314 version rewriting
│   ├── builder.py      # Build sdist/wheel via PEP 517
│   └── uploader.py     # Push to devpi server
└── server/
    ├── config.py       # Generate devpi/nginx configs
    └── deploy.py       # Hetzner setup scripts
```

## Analyzer Checks (11 types in compat/analyzer.py)
1. `removed_ast_node` — ast.Num/Str/Bytes/NameConstant/Ellipsis → ast.Constant ✅ auto-fixable
2. `removed_asyncio_watcher` — child watcher APIs removed ❌ needs AI
3. `removed_pkgutil_loader` — find_loader/get_loader → importlib.util.find_spec ✅ auto-fixable
4. `removed_sqlite3_version` — sqlite3.version → sqlite3.sqlite_version ✅ auto-fixable
5. `removed_urllib_class` — URLopener/FancyURLopener removed ❌ needs AI
6. `removed_importlib_abc` — ResourceReader/Traversable → importlib.resources.abc ✅ auto-fixable
7. `removed_shutil_onerror` — onerror → onexc ✅ auto-fixable
8. `pathlib_extra_args` — multiple args to relative_to/is_relative_to ❌ needs AI
9. `removed_pty_function` — master_open/slave_open → openpty ✅ auto-fixable
10. `deprecated_pkg_resources` — pkg_resources imports ❌ needs AI
11. `invalid_escape_sequence` — \p, \/, \d etc. in non-raw strings ✅ auto-fixable

## Auto-Fixer Handlers (7 types in fixer/auto.py)
Matching the auto-fixable analyzer checks above. The escape sequence fixer uses a character-by-character state machine to double invalid backslashes while preserving valid escapes and raw strings.

## Pipeline Behavior
- Full loop: fetch → analyze → fix → build → **upload to devpi** → installable via pip
- `SKIP_BUILD_PACKAGES` frozenset: 26 C-extension packages that hang during build
- `_has_c_extensions()` heuristic: detects .c/.cpp/.pyx files and ext_modules in setup.py
- `needs_review` workflow: packages with unfixed AI issues get flagged instead of silently completed
- Two-tier design: server runs `--auto-only` (no API key), reviews pulled locally for Claude fixing
- Upload requires `--upload` flag or `LAZARUS_UPLOAD=1` + `LAZARUS_DEVPI_PASSWORD`
- DevpiUploader uses native devpi auth: login → base64(user:token) X-Devpi-Auth header
- **Version override strategy** (three layers):
  1. `dynamic = ["version"]` → removed, set static version in pyproject.toml
  2. `SETUPTOOLS_SCM_PRETEND_VERSION` env var for git-tag-based versions
  3. PKG-INFO rewrite as universal sdist fallback
  4. Regex rewrites for setup.py, setup.cfg, __init__.py with `__version__ = "..."`

## Batch Processing Results (Top 1,000 PyPI packages)
- 922 already compatible (92.2%)
- 35 auto-fixed (3.5%)
- 43 failed — mostly no sdist available (NVIDIA, PyTorch, TensorFlow) or C-extension build issues
- 0 needs_review (these top packages are well-maintained)

## Database
- SQLite at `~/.lazarus/lazarus.db`
- WAL mode, 5s busy timeout
- Job statuses: pending, in_progress, complete, failed, needs_review
- Fix methods: none, auto, ai, manual

## Important Gotchas
- Background tasks in Claude conversation sandbox die between turns — use real terminal sessions
- `pip install -e .` hasn't been run yet — user uses `python -m lazarus` instead
- Version rewrite can accidentally affect build dependency version checks (seen with scikit-build-core)
- The `re` import in analyzer.py is currently unused (was imported for escape sequence work but state machine approach was used instead)

## Domain & Infrastructure
- **Domain**: lazaruspy.org (Cloudflare Registrar)
- **Email**: admin@lazaruspy.org (Cloudflare Email Routing → personal email)
- **DNS**: Cloudflare — A record → 89.167.40.82, CNAME www → lazaruspy.org
- **Server**: Hetzner CX33 (4 vCPU, 8 GB RAM, 80 GB SSD) — Helsinki, Ubuntu 24.04
- **Server IP**: 89.167.40.82 (hostname: lazarus-prod)
- **Package index URL**: https://lazaruspy.org/simple/
- **SSL**: Let's Encrypt (auto-renew via certbot)

## Server Stack
- **devpi-server 6.19.1** on port 3141 (localhost only), proxied by nginx
- **devpi user**: `lazarus` (password: `lazarus314prod`)
- **devpi index**: `lazarus/packages` (inherits from `root/pypi`)
- **nginx**: reverse proxy, `/simple/` → devpi `lazarus/packages/+simple/`
- **Python**: 3.14.3 (deadsnakes PPA) at `/opt/lazarus-venv/`
- **Lazarus**: installed from `/opt/lazarus/` (git clone of repo)

## Server Services (systemd)
- `devpi.service` — devpi-server on 127.0.0.1:3141 (enabled, running)
- `lazarus-processor.service` — `admin process --auto-only --upload` (enabled, running)
- `lazarus-watchdog.service` — `admin watchdog` (enabled, running)
- `lazarus-seed.timer` — weekly seed of top 5,000 packages

## Server SSH Access
```bash
ssh -i ~/.ssh/id_ed25519 root@89.167.40.82
```

## Published Packages (on lazaruspy.org)
- `pip-26.0.1.post314` — auto-fixed
- `pyparsing-3.3.2.post314` — auto-fixed (flit dynamic version)
- `zipp-3.23.0.post314` — auto-fixed (setuptools_scm dynamic version)
- Install: `pip install --extra-index-url https://lazaruspy.org/simple/ <package>`

## What's Next (toward 1.0.0a2)
- Seed larger batch (5,000-10,000) to find more packages needing fixes
- Implement `server/config.py` and `server/deploy.py` for reproducible deployment
- Add `/status/<package>` API endpoint for verified compatibility checks
- Add skip/ignore mechanism for acknowledged-but-won't-fix issues
- Set up monitoring/alerting for server health
- Consider Cloudflare proxy (orange cloud) after SSL is stable
