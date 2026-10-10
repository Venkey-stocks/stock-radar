import csv
import json
import os

FILES = {"ultra": "data/ultra_short.csv", "short": "data/short_term.csv"}
KEEP = 40  # చివరి 40 రోజుల ఫైళ్ళు మాత్రమే ఉంచుతుంది
HIST = "data/history"
IDX = HIST + "/index.json"

os.makedirs(HIST, exist_ok=True)
try:
    with open(IDX, encoding="utf-8") as f:
        idx = json.load(f)
except Exception:
    idx = {}

for scan, path in FILES.items():
    if not os.path.exists(path):
        print(scan, ": file not found, skipped")
        continue
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    dates = [r.get("Date", "") for r in rows if r.get("Date")]
    if not dates:
        print(scan, ": no rows or no Date, skipped")
        continue
    d = max(dates)
    keep = [r for r in rows if r.get("Date") == d]
    out = HIST + "/" + scan + "_" + d + ".csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Symbol", "Status", "Score", "Band"])
        for r in keep:
            w.writerow([r.get("Symbol", ""), r.get("Status", ""), r.get("Score", ""), r.get("Band", "")])
    lst = sorted(set(idx.get(scan, []) + [d]))
    for old in lst[:-KEEP]:
        p = HIST + "/" + scan + "_" + old + ".csv"
        if os.path.exists(p):
            os.remove(p)
    idx[scan] = lst[-KEEP:]
    print(scan, ":", len(keep), "stocks saved for", d)

with open(IDX, "w", encoding="utf-8") as f:
    json.dump(idx, f)
