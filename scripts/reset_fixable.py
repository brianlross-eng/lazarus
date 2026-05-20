"""Reset failed packages that should now be fixable with the new pipeline changes."""
import sqlite3

conn = sqlite3.connect("/root/.lazarus/queue.db")
c = conn.cursor()

# 1. FileNotFoundError (requirements.txt, README, VERSION, etc.)
c.execute(
    "SELECT id FROM jobs WHERE status=? AND last_error LIKE ?",
    ("failed", "%FileNotFoundError%"),
)
fnf_ids = [row[0] for row in c.fetchall()]
print(f"FileNotFoundError packages to reset: {len(fnf_ids)}")

# 2. pyproject.toml version validation (version + dynamic conflict)
c.execute(
    "SELECT id FROM jobs WHERE status=? AND last_error LIKE ?",
    ("failed", "%cannot provide a value for%project.version%project.dynamic%"),
)
version_ids = [row[0] for row in c.fetchall()]
print(f"pyproject.toml version conflict packages to reset: {len(version_ids)}")

# 3. Also check for the broader pattern
c.execute(
    "SELECT id FROM jobs WHERE status=? AND last_error LIKE ?",
    ("failed", "%invalid pyproject.toml config%project.version%"),
)
version_ids2 = [row[0] for row in c.fetchall()]
print(f"pyproject.toml project.version validation errors: {len(version_ids2)}")

# Combine and deduplicate
all_ids = list(set(fnf_ids + version_ids + version_ids2))
print(f"\nTotal unique packages to reset: {len(all_ids)}")

# Reset them
if all_ids:
    placeholders = ",".join("?" * len(all_ids))
    c.execute(
        f"UPDATE jobs SET status='pending', attempts=0, last_error=NULL, "
        f"fix_method='none' WHERE id IN ({placeholders})",
        all_ids,
    )
    conn.commit()
    print(f"Reset {c.rowcount} packages to pending")

conn.close()
