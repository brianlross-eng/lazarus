"""Analyze failures from the most recent reprocessing batch."""
import sqlite3
import re
from collections import Counter

conn = sqlite3.connect("/root/.lazarus/queue.db")
c = conn.cursor()

c.execute(
    "SELECT last_error FROM jobs WHERE status=? AND updated_at > ? AND last_error IS NOT NULL",
    ("failed", "2026-02-26T06:20:00"),
)
rows = c.fetchall()
print(f"=== New failures since deploy ({len(rows)}) ===")
cats = Counter()
for (err,) in rows:
    if "FileNotFoundError" in err:
        m = re.search(r"No such file or directory: '([^']+)'", err)
        if m:
            fname = m.group(1).split("/")[-1]
            cats[f"FileNotFoundError: {fname}"] += 1
        else:
            cats["FileNotFoundError: other"] += 1
    elif "ModuleNotFoundError" in err:
        m = re.search(r"No module named '([^']+)'", err)
        mod = m.group(1) if m else "?"
        cats[f"ModuleNotFoundError: {mod}"] += 1
    elif "Backend subprocess" in err:
        if "pkg_resources" in err:
            cats["Build: pkg_resources"] += 1
        elif "FileNotFoundError" in err:
            cats["Build: FileNotFoundError"] += 1
        elif "SyntaxError" in err:
            cats["Build: SyntaxError"] += 1
        elif "version" in err.lower():
            cats["Build: version issue"] += 1
        else:
            cats["Build: other"] += 1
    elif "InvalidVersion" in err:
        cats["InvalidVersion"] += 1
    elif "SyntaxError" in err:
        cats["SyntaxError"] += 1
    elif "ImportError" in err:
        cats["ImportError"] += 1
    elif "NameError" in err:
        cats["NameError"] += 1
    elif "No sdist" in err:
        cats["No sdist"] += 1
    elif "OOM" in err:
        cats["OOM"] += 1
    else:
        cats["other"] += 1

for cat, count in cats.most_common(25):
    print(f"  {cat}: {count}")

conn.close()
