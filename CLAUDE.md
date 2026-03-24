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
# Run all tests (255 tests, should all pass)
python -m pytest -v

# CLI (must use python -m until pip install -e . is done)
python -m lazarus admin status          # Queue stats
python -m lazarus admin errors           # Show common error patterns from failed jobs
python -m lazarus admin reviews         # Show packages needing AI/manual fix
python -m lazarus admin process --auto-only  # Process queue (auto-fixes only)
python -m lazarus admin watchdog        # Supervisor process
python -m lazarus admin seed --count 1000    # Seed queue from top PyPI packages
python -m lazarus admin seed --deep -n 5000  # Seed from full PyPI index (long tail)
python -m lazarus admin retry-failures --dry-run  # Preview fixable failed packages
python -m lazarus admin retry-failures --pattern SyntaxError --limit 10  # Retry specific pattern

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
│   ├── analyzer.py     # AST-based static analysis (22 check types)
│   ├── tester.py       # Run tests in isolated 3.14 venvs
│   └── failures.py     # Failure classification
├── fixer/
│   ├── auto.py         # Mechanical fixes (22 fix types including escape sequences)
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

## Analyzer Checks (22 types in compat/analyzer.py)
1. `removed_ast_node` — ast.Num/Str/Bytes/NameConstant/Ellipsis → ast.Constant ✅ auto-fixable
2. `removed_asyncio_watcher` — child watcher APIs removed ❌ needs AI
3. `removed_pkgutil_loader` — find_loader/get_loader → importlib.util.find_spec ✅ auto-fixable
4. `removed_sqlite3_version` — sqlite3.version → sqlite3.sqlite_version ✅ auto-fixable
5. `removed_urllib_class` — URLopener/FancyURLopener removed ❌ needs AI
6. `removed_importlib_abc` — ResourceReader/Traversable → importlib.resources.abc ✅ auto-fixable
7. `removed_shutil_onerror` — onerror → onexc ✅ auto-fixable
8. `pathlib_extra_args` — multiple args to relative_to/is_relative_to ❌ needs AI
9. `removed_pty_function` — master_open/slave_open → openpty ✅ auto-fixable
10. `deprecated_pkg_resources` — pkg_resources imports ✅ auto-fixable (common patterns)
11. `invalid_escape_sequence` — \p, \/, \d etc. in non-raw strings ✅ auto-fixable
12. `python2_builtin_*` — execfile, raw_input, xrange, reload, unicode, long ✅ auto-fixable (text-based)
13. `python2_builtin_basestring` — basestring → str ✅ auto-fixable (text-based)
14. `removed_module_*` — urllib2, Queue, commands → Python 3 equivalents ✅ auto-fixable (text-based)
15. `removed_ast_constant_attr` — ast.Constant.s/.n → .value ✅ auto-fixable (AST-based)
16. `python2_except_comma` — except X, e: → except X as e: ✅ auto-fixable (text-based)
17. `python2_ne_operator` — <> → != ✅ auto-fixable (text-based)
18. `python2_dict_*` — .iteritems()/.itervalues()/.iterkeys() → .items()/.values()/.keys() ✅ auto-fixable (text-based)

## Auto-Fixer Handlers (22 types in fixer/auto.py)
Matching the auto-fixable analyzer checks above. The escape sequence fixer uses a character-by-character state machine to double invalid backslashes while preserving valid escapes and raw strings. The pkg_resources fixer handles get_distribution().version, require(), and resource_filename() patterns via regex replacement. Python 2 builtin/module/syntax fixers use regex-based text replacement (works even on files with SyntaxError).

## Pipeline Behavior
- Full loop: fetch → analyze → fix → build → **upload to devpi** → installable via pip
- **Cache cleanup**: cached sdists are deleted after each job completes (prevents disk exhaustion)
- **Missing build files**: `_ensure_build_files()` creates empty stubs for requirements.txt, README, VERSION etc. referenced in setup.py but missing from sdist (fixes ~260 packages)
- `SKIP_BUILD_PACKAGES` frozenset: 26 C-extension packages that hang during build
- `_has_c_extensions()` heuristic: detects .c/.cpp/.pyx files and ext_modules in setup.py
- `needs_review` workflow: packages with unfixed AI issues get flagged instead of silently completed
- Two-tier design: server runs `--auto-only` (no API key), reviews pulled locally for Claude fixing
- Upload requires `--upload` flag or `LAZARUS_UPLOAD=1` + `LAZARUS_DEVPI_PASSWORD`
- DevpiUploader uses native devpi auth: login → base64(user:token) X-Devpi-Auth header
- **Version override strategy** (four layers):
  1. `dynamic = ["version"]` → removed from list (any position), set static version in pyproject.toml
  2. `SETUPTOOLS_SCM_PRETEND_VERSION` env var for git-tag-based versions
  3. PKG-INFO rewrite as universal sdist fallback
  4. Regex rewrites for setup.py, setup.cfg, __init__.py with `__version__ = "..."`
  5. Version regexes use `(?!\.)` negative lookahead (prevents `".".join()` corruption) and `\b` word boundary (prevents `minversion`/`local_version` matches)
- **Build environment**: `PIP_CONSTRAINT=setuptools<82` ensures pkg_resources remains available in isolated build venvs
- **Build fixes** (`_fix_setup_py_build_issues`): patches setup.py before build — 25 fix types including pkg_resources imports, pip shims, ez_setup/distribute_setup removal, Python 2 print/except/raise/octal/exec syntax, import imp shim (with load_source), removed setuptools commands, pkgutil.ImpImporter, platform.dist(), ConfigParser.readfp, INSTALL_SCHEMES shim, SafeConfigParser→ConfigParser, collections ABCs→collections.abc, inspect.getargspec→getfullargspec, distutils→setuptools shim, DistributionNotFound stub, ast.Str/Num/Bytes/NameConstant→ast.Constant
- **Archive support**: `.tar.gz`, `.tgz`, `.tar.bz2`, `.tar.xz`, `.zip` — with `_safe_tar_filter()` that silently skips symlinks

## Batch Processing Results
### Batch 1+2: 158,654 packages — COMPLETE
- 140,978 complete (88.9%), ~15,500 auto-fixed
- 17,676 failed (~16,400 no sdist, ~1,300 other)
- Retry passes recovered 310 packages via expanded fixers and infrastructure fixes

### Batch 3: 57,461 packages — COMPLETE
- 50,016 completed (87.0%)
- 7,445 failed
- Running total: 216,115 queued, 191,022 complete (88.4%)
### Batch 4: 57,313 packages — COMPLETE
- 49,067 completed (85.6%)
- 8,246 failed
- Running total: 273,428 queued, 240,089 complete (87.8%), 31,214 failed
- sqlml-parser OOM crash blocked processing for ~24h — added SKIP_OOM_PACKAGES
- Post-batch retry: ~2,350 packages retried with expanded pre-build fixes

### Batch 5: 19,047 packages — COMPLETE
- 16,702 completed, 2,345 failed
- Post-batch retry: 200 packages retried with 6 new fix types, 33 recovered
- Running total: 292,475 queued, 258,023 complete (88.2%), 34,452 failed, 47,633 auto-fixed

### Batch 6: ~18,930 packages — COMPLETE
- Running total: 311,405 queued (40.8% of PyPI's 764k)

### Batch 7: ~18,939 packages — COMPLETE
- Running total: 330,344 queued (43.2% of PyPI's 765k)
- 291,212 processed / 56,143 modified / 39,132 couldn't modify

### Batch 8: ~36,876 packages — IN PROGRESS
- Seeded 2026-03-23, ETA ~24-30h
- Running total: ~367,220 queued (48.0% of PyPI's 765k)
- ~15k more to reach 50% launch target

## Database
- SQLite at `~/.lazarus/queue.db`
- WAL mode, 5s busy timeout
- Job statuses: pending, in_progress, complete, failed, needs_review
- Fix methods: none, auto, ai, manual

## Important Gotchas
- Background tasks in Claude conversation sandbox die between turns — use real terminal sessions
- Server was running old 0.1.0 package until 2026-02-25 — now 1.0.0a1 via `pip install -e .`
- Version rewrite can accidentally affect build dependency version checks (seen with scikit-build-core)
- **Disk space**: devpi store grows ~1.2MB per fixed package (34GB for 27k packages); work dir cleaned by watchdog
- `SKIP_OOM_PACKAGES` frozenset: cosmowap, sqlml-parser (cause OOM kills during analysis)

## Domain & Infrastructure
- **Domain**: lazaruspy.org (Cloudflare Registrar)
- **Email**: admin@lazaruspy.org (Cloudflare Email Routing → personal email)
- **DNS**: Cloudflare — A record → 89.167.40.82, CNAME www → lazaruspy.org
- **Server**: Hetzner CX33 (4 vCPU, 8 GB RAM, 80 GB SSD) — Helsinki, Ubuntu 24.04
- **Storage volume**: 160GB ext4 (`/dev/sdb`) mounted at `/var/lib/devpi` ($8/mo)
- **Server IP**: 89.167.40.82 (hostname: lazarus-prod)
- **Package index URL**: https://lazaruspy.org/simple/
- **SSL**: Let's Encrypt (auto-renew via certbot)

## Server Stack
- **devpi-server 6.19.1** on port 3141 (localhost only), proxied by nginx
- **devpi user**: `lazarus` (password: `lazarus314prod`)
- **devpi index**: `lazarus/packages` (inherits from `root/pypi`)
- **nginx**: reverse proxy, `/simple/` → devpi `lazarus/packages/+simple/`
- **Python**: 3.14.3 (deadsnakes PPA) at `/opt/lazarus-venv/`
- **Lazarus**: 1.0.0a1 installed from `/opt/lazarus/` (git clone, `pip install -e .`)

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
- ~~Seed larger batch~~ Done: 216k packages across 3 batches
- ~~Add pkg_resources auto-fixer~~ Done: 8th fix type
- ~~Cache cleanup~~ Done: sdists deleted after processing, prevents disk fill
- ~~Add .tar.bz2/.tar.xz support~~ Done: recovered ~150 packages
- ~~Symlink-safe extraction~~ Done: _safe_tar_filter skips symlinks
- ~~ez_setup/distribute_setup removal~~ Done: strips obsolete bootstrap
- ~~Version rewrite corruption fix~~ Done: lookbehind prevents string matches
- ~~Upgrade server disk~~ Done: 80GB ext4 volume at /var/lib/devpi ($4/mo)
- ~~Expand pre-build setup.py patching~~ Done: 22 fix types (was 6), targets Python 2 syntax, removed APIs, moved ABCs
- ~~Fix Aliyun mirror in server pip.conf~~ Done: was causing setuptools constraint failures
- ~~Fix deep seed OOM~~ Done: streaming PyPI index parse replaces regex-on-full-HTML
- **Soft launch at 50% of PyPI** (~382k packages) — blog post, HN/Reddit, landing page
- Implement `server/config.py` and `server/deploy.py` for reproducible deployment
- Add `/status/<package>` API endpoint for verified compatibility checks
- Set up monitoring/alerting for server health
- Reduce processor idle churn (currently restarts every 60s even when queue empty)
- Prepare landing page for lazaruspy.org with install instructions
- **After first pass**: revisit C-extension packages (numpy, pandas, etc.) — analyze failure reasons, consider build agent with compilers or sourcing pre-built 3.14 wheels
