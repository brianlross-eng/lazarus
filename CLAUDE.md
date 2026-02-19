# Lazarus Project — Claude Memory

## What This Project Is
PyPI-compatible proxy repository that automatically resurrects Python packages broken by Python 3.14 incompatibility. Pulls packages from PyPI, detects compatibility issues (AST-based static analysis), fixes them (auto-fix or Claude AI), rebuilds, and republishes with `.post314` version suffixes.

## Repository
- GitHub: https://github.com/brianlross-eng/lazarus
- Branch: `master`
- Python: 3.14 (the target platform)
- Package layout: `src/lazarus/` with `pyproject.toml`

## Key Commands
```bash
# Run all tests (76 tests, should all pass)
python -m pytest -v

# CLI (must use python -m until pip install -e . is done)
python -m lazarus admin status          # Queue stats
python -m lazarus admin failures 20     # Show failed jobs
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
- `SKIP_BUILD_PACKAGES` frozenset: 26 C-extension packages that hang during build
- `_has_c_extensions()` heuristic: detects .c/.cpp/.pyx files and ext_modules in setup.py
- `needs_review` workflow: packages with unfixed AI issues get flagged instead of silently completed
- Two-tier design: server runs `--auto-only` (no API key), reviews pulled locally for Claude fixing

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

## What's Next
- **Hetzner server setup** — purchase, deploy devpi + nginx, configure for unattended operation
- Server deployment files needed: `deploy/devpi/docker-compose.yml`, nginx.conf, setup scripts
- `server/config.py` and `server/deploy.py` need implementation
- Consider seeding larger batch (5,000-10,000) to find more packages needing fixes
- `publisher/uploader.py` needs implementation for pushing to devpi
