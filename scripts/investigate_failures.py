import sqlite3

conn = sqlite3.connect("/root/.lazarus/queue.db")

# 1. NameError: pkg_resources — sample full errors
print("=== NameError: pkg_resources (sample 5) ===")
rows = conn.execute(
    "SELECT package_name, version, last_error FROM jobs WHERE status='failed' AND last_error LIKE '%NameError%pkg_resources%' LIMIT 5"
).fetchall()
for name, ver, err in rows:
    print(f"\n--- {name}=={ver} ---")
    print(err[-500:] if len(err) > 500 else err)

# 2. NoModule: pip — sample full errors
print("\n\n=== NoModule: pip (sample 5) ===")
rows = conn.execute(
    "SELECT package_name, version, last_error FROM jobs WHERE status='failed' AND last_error LIKE '%No module named%pip%' LIMIT 5"
).fetchall()
for name, ver, err in rows:
    print(f"\n--- {name}=={ver} ---")
    print(err[-500:] if len(err) > 500 else err)

# 3. FileNotFoundError — sample full errors
print("\n\n=== FileNotFoundError (sample 5) ===")
rows = conn.execute(
    "SELECT package_name, version, last_error FROM jobs WHERE status='failed' AND last_error LIKE '%FileNotFoundError%' LIMIT 5"
).fetchall()
for name, ver, err in rows:
    print(f"\n--- {name}=={ver} ---")
    print(err[-500:] if len(err) > 500 else err)

# 4. build:other — what are these?
print("\n\n=== build:other (sample 5) ===")
rows = conn.execute(
    "SELECT package_name, version, last_error FROM jobs WHERE status='failed' AND last_error LIKE 'sdist build failed%' AND last_error NOT LIKE '%SyntaxError%' AND last_error NOT LIKE '%NameError%' AND last_error NOT LIKE '%ModuleNotFoundError%' AND last_error NOT LIKE '%FileNotFoundError%' AND last_error NOT LIKE '%AttributeError%' AND last_error NOT LIKE '%ValueError%' AND last_error NOT LIKE '%ImportError%' AND last_error NOT LIKE '%TypeError%' AND last_error NOT LIKE '%KeyError%' AND last_error NOT LIKE '%InvalidVersion%' AND last_error NOT LIKE '%pkg_resources%' LIMIT 5"
).fetchall()
for name, ver, err in rows:
    print(f"\n--- {name}=={ver} ---")
    print(err[-600:] if len(err) > 600 else err)

# 5. AttributeError — sample
print("\n\n=== AttributeError (sample 5) ===")
rows = conn.execute(
    "SELECT package_name, version, last_error FROM jobs WHERE status='failed' AND last_error LIKE '%AttributeError%' LIMIT 5"
).fetchall()
for name, ver, err in rows:
    print(f"\n--- {name}=={ver} ---")
    print(err[-500:] if len(err) > 500 else err)

conn.close()
