"""Step 2b: HEAD every EIA-930 six-month file 2015-2026 to measure full-history CSV size."""
import requests, json, os
B = "https://www.eia.gov/electricity/gridmonitor/sixMonthFiles/"
rows = []
for kind in ["BALANCE", "INTERCHANGE", "SUBREGION"]:
    for y in range(2015, 2027):
        for h in ["Jan_Jun", "Jul_Dec"]:
            f = f"EIA930_{kind}_{y}_{h}.csv"
            r = requests.head(B + f, timeout=30, headers={"Accept-Encoding": "identity"})
            if r.status_code == 200 and r.headers.get("Last-Modified"):
                rows.append({"file": f, "kind": kind, "MB": int(r.headers.get("Content-Length", 0)) / 1e6, "last_modified": r.headers.get("Last-Modified")})
tot = {}
for r in rows: tot[r["kind"]] = tot.get(r["kind"], 0) + r["MB"]
for r in rows: print(f'{r["file"]:42s} {r["MB"]:7.1f} MB  {r["last_modified"]}')
print("TOTAL CSV MB by kind:", {k: round(v) for k, v in tot.items()}, "files:", len(rows))
json.dump({"files": rows, "total_MB": tot}, open("out/s2b_bulk_inventory.json", "w"), indent=1)
