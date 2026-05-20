import sqlite3
conn = sqlite3.connect("/root/.lazarus/queue.db")
conn.row_factory = sqlite3.Row
rows = conn.execute(
    "SELECT package_name, version, fix_method, updated_at FROM jobs "
    "WHERE status = 'complete' ORDER BY updated_at DESC LIMIT 25"
).fetchall()
print("=== Recently completed (recovered) packages ===")
for r in rows:
    print(f"  {r['fix_method']:6s}  {r['package_name']}=={r['version']}  {r['updated_at'][:19]}")
conn.close()
