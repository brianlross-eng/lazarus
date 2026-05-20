import sqlite3
conn = sqlite3.connect("/root/.lazarus/queue.db")
conn.row_factory = sqlite3.Row
# Get most recently completed packages
rows = conn.execute(
    "SELECT package_name, version, fix_method, updated_at FROM jobs "
    "WHERE status = 'complete' ORDER BY updated_at DESC LIMIT 10"
).fetchall()
print("=== Recently completed ===")
for r in rows:
    print(f"  {r['package_name']}=={r['version']}  fix={r['fix_method']}  {r['updated_at']}")

# Get recently reviewed
rows = conn.execute(
    "SELECT package_name, version, last_error, updated_at FROM jobs "
    "WHERE status = 'needs_review' ORDER BY updated_at DESC LIMIT 5"
).fetchall()
print("\n=== Recently needs_review ===")
for r in rows:
    err = (r["last_error"] or "")[:200]
    print(f"  {r['package_name']}=={r['version']}  {err}")
conn.close()
