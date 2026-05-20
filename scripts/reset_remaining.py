"""Reset remaining fixable failures for second pass."""
import sqlite3

conn = sqlite3.connect("/root/.lazarus/queue.db")
c = conn.cursor()

# Reset FileNotFoundError failures that just failed in the last batch
c.execute(
    "SELECT id, package_name FROM jobs WHERE status=? AND last_error LIKE ? AND updated_at > ?",
    ("failed", "%FileNotFoundError%", "2026-02-26T06:20:00"),
)
rows = c.fetchall()
print(f"Recent FileNotFoundError failures to reset: {len(rows)}")

# Also reset pkg_resources build failures (maybe constraint file wasn't cached)
c.execute(
    "SELECT id, package_name FROM jobs WHERE status=? AND last_error LIKE ? AND updated_at > ?",
    ("failed", "%No module named%pkg_resources%", "2026-02-26T06:20:00"),
)
pkg_rows = c.fetchall()
print(f"Recent pkg_resources failures to reset: {len(pkg_rows)}")

all_ids = list(set([r[0] for r in rows] + [r[0] for r in pkg_rows]))
print(f"Total unique to reset: {len(all_ids)}")

if all_ids:
    placeholders = ",".join("?" * len(all_ids))
    c.execute(
        f"UPDATE jobs SET status='pending', attempts=0, last_error=NULL, "
        f"fix_method='none' WHERE id IN ({placeholders})",
        all_ids,
    )
    conn.commit()
    print(f"Reset {c.rowcount} packages")

conn.close()
