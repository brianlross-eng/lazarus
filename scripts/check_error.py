import sqlite3
conn = sqlite3.connect("/root/.lazarus/queue.db")
conn.row_factory = sqlite3.Row
row = conn.execute("SELECT last_error FROM jobs WHERE package_name = ? LIMIT 1", ("chronon-ai",)).fetchone()
print(row["last_error"])
conn.close()
