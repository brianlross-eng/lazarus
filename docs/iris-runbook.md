# Lazarus Operations Runbook — For Iris

## What Lazarus Does
Lazarus is a PyPI-compatible proxy that automatically fixes Python packages broken by Python 3.14 incompatibilities. It fetches packages from PyPI, analyzes them, applies auto-fixes, rebuilds them, and uploads fixed versions to **lazaruspy.org**.

The pipeline runs continuously on a Hetzner server at **89.167.40.82**.

---

## Daily Status Check

SSH to the server (requires `~/.ssh/id_ed25519` key):
```bash
ssh -i ~/.ssh/id_ed25519 root@89.167.40.82
```

Run the status query:
```bash
/opt/lazarus-venv/bin/python -c "
from lazarus.config import LazarusConfig
from lazarus.db.queue import JobQueue
q = JobQueue(LazarusConfig().db_path)
q.initialize()
print(q.get_status())
q.close()
"
```

Check services and disk:
```bash
systemctl is-active lazarus-processor
systemctl is-active lazarus-watchdog
df -h /dev/sda1 /dev/sdb
```

### Interpreting the Output

| Field | Meaning |
|-------|---------|
| `complete` | Packages processed (fixed or confirmed compatible) |
| `failed` | Packages that couldn't be fixed — **~12% failure rate is normal** |
| `pending` | Waiting to be processed — if > 0, a batch is in progress |
| `in_progress` | Currently being processed |

**Healthy state (between batches):** `pending: 0`, `in_progress: 0`, processor cycling.
**Healthy state (batch running):** `pending` count decreasing over time, processor `active`.
**Unhealthy:** processor `inactive` for more than a few minutes, or same `pending` count for hours.

### Normal Failure Rate
~88% success, ~12% failure — this is expected. Failures are almost always:
- **88%** — package has no source distribution (wheel-only, unfixable)
- **11%** — package requires native compilers/C extensions (unfixable without build agents)
- **~1%** — other

Do NOT alert on failures unless the *success rate drops below 80%*.

---

## Batch Lifecycle

Batches are manually seeded and run to completion (~16-20h for 18k packages).

### Check if a batch is running
```bash
/opt/lazarus-venv/bin/python -c "
from lazarus.config import LazarusConfig
from lazarus.db.queue import JobQueue
q = JobQueue(LazarusConfig().db_path)
q.initialize()
s = q.get_status()
print(f'pending: {s.get(\"pending\", 0)}  in_progress: {s.get(\"in_progress\", 0)}')
q.close()
"
```
- `pending > 0` → batch running, ETA roughly `pending / 18000 * 18h`
- `pending = 0` → batch complete, waiting for next seed

### Coverage Progress
Total PyPI packages: ~765,000
Current queue total ÷ 765,000 = % of PyPI covered
**Target: 100% of PyPI (ongoing)**

---

## Seeding a New Batch

Only seed when `pending = 0` (previous batch complete).

```bash
# 1. Stop processor (frees memory for seed)
systemctl stop lazarus-processor

# 2. Seed 20,000 new packages
cd /opt/lazarus
/opt/lazarus-venv/bin/python -m lazarus admin seed --deep -n 20000

# 3. Restart processor
systemctl start lazarus-processor
systemctl is-active lazarus-processor
```

Expected output: `Added ~18,000-19,000 new packages. Total in queue: XXXXXX`

---

## Post-Batch Procedure

After each batch completes, check if any new fix types are warranted:

```bash
/opt/lazarus-venv/bin/python << 'PYEOF'
import sqlite3, re
conn = sqlite3.connect('/root/.lazarus/queue.db')
rows = conn.execute("SELECT last_error FROM jobs WHERE status='failed'").fetchall()
msgs = [r[0] or '' for r in rows]
no_sdist = sum(1 for m in msgs if any(x in m.lower() for x in ['no sdist','wheel-only','version not found']))
build_dep = sum(1 for m in msgs if 'installing packages in isolated' in m.lower())
other = len(msgs) - no_sdist - build_dep
print(f'no_sdist: {no_sdist} | build_dep: {build_dep} | other: {other}')
conn.close()
PYEOF
```

**If `other` is small (< 500) and matches known patterns → no action needed, seed next batch.**
**If `other` is large or shows new error patterns → escalate to Brian.**

---

## Disk Monitoring

| Volume | Mount | Alert threshold |
|--------|-------|----------------|
| Root (`/dev/sda1`) | `/` | > 85% |
| Data (`/dev/sdb`) | `/var/lib/devpi` | > 85% |

Check: `df -h /dev/sda1 /dev/sdb`

If `/dev/sdb` approaches 85%, alert Brian — volume resize needed on Hetzner (currently 160GB, was doubled once already).

---

## Processor Health Check

If processor is stuck (same `pending` count for 2+ hours):

```bash
# Check recent logs
journalctl -u lazarus-processor -n 20 --no-pager
```

Look for:
- `code=killed, status=9/KILL` → OOM kill. Check if a package is looping:
  ```bash
  journalctl -u lazarus-processor -n 5 --no-pager | grep "Processing"
  ```
  If same package repeats → add it to `SKIP_OOM_PACKAGES` in `/opt/lazarus/src/lazarus/pipeline.py` and alert Brian.
- `Processed 0 package(s)` repeating → queue empty, normal idle behavior.

---

## Services Reference

| Service | Purpose | Should be |
|---------|---------|-----------|
| `lazarus-processor` | Processes queue jobs | `active` (or `activating` when idle-cycling) |
| `lazarus-watchdog` | Monitors for stale jobs, restarts processor | `active` |
| `devpi` | Package index server | `active` |
| `nginx` | Reverse proxy for lazaruspy.org | `active` |

Check all: `systemctl is-active lazarus-processor lazarus-watchdog devpi nginx`

---

## Escalate to Brian When

- Processor OOM-killing on a new package (needs `SKIP_OOM_PACKAGES` update)
- `/dev/sdb` above 85%
- Success rate drops below 80%
- Processor won't restart after watchdog intervention
- New error patterns appear in `other` category (potential new fix types)
