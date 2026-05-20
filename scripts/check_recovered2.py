import sqlite3
conn = sqlite3.connect("/root/.lazarus/queue.db")
conn.row_factory = sqlite3.Row
rows = conn.execute(
    "SELECT package_name, version, fix_method, updated_at FROM jobs "
    "WHERE status = 'complete' ORDER BY updated_at DESC LIMIT 50"
).fetchall()
print("=== Recently completed (recovered) packages ===")
count = {"auto": 0, "none": 0, "ai": 0}
for r in rows:
    fm = r["fix_method"]
    count[fm] = count.get(fm, 0) + 1
    print(f"  {fm:6s}  {r['package_name']}=={r['version']}")
print(f"\nBreakdown: {count}")
conn.close()
