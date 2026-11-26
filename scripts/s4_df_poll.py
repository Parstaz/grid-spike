"""Step 4: snapshot DF for ISNE + 3 large BAs, UTC window yesterday..+3 days. Stdlib only (fast on Actions).
Writes <outdir>/df_<pulledUTC>.csv with pulled_at_utc on every row, plus a per-request log line."""
import os, sys, csv, json, time, urllib.request, urllib.parse, datetime as dt
BAS = ["ISNE", "PJM", "MISO", "ERCO"]
k = os.environ.get("EIA_API_KEY") or [l.split("=", 1)[1].strip() for l in open(os.path.expanduser("~/grid-spike/.env")) if l.startswith("EIA_API_KEY=")][0]
outdir = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/grid-spike/out/df_poll"); os.makedirs(outdir, exist_ok=True)
now = dt.datetime.now(dt.timezone.utc); pulled = now.strftime("%Y-%m-%dT%H:%M:%SZ")
s = (now - dt.timedelta(days=1)).strftime("%Y-%m-%dT00"); e = (now + dt.timedelta(days=4)).strftime("%Y-%m-%dT00")
q = [("api_key", k), ("frequency", "hourly"), ("data[0]", "value"), ("facets[type][]", "DF"), ("start", s), ("end", e), ("length", 5000)] + [("facets[respondent][]", b) for b in BAS]
t = time.time(); err = None
for i in range(4):
    try:
        j = json.load(urllib.request.urlopen("https://api.eia.gov/v2/electricity/rto/region-data/data/?" + urllib.parse.urlencode(q), timeout=90)); break
    except Exception as ex:
        err = repr(ex)[:200].replace(k, "***"); time.sleep(10 * 2 ** i)
else:  # record the outage as a data point, don't crash: gaps in the poll are themselves a measurement
    with open(os.path.join(outdir, "poll_log.jsonl"), "a") as f:
        f.write(json.dumps({"pulled_at_utc": pulled, "rows": 0, "seconds": round(time.time() - t, 2), "FAILED": err}) + "\n")
    print(pulled, "FAILED", err); raise SystemExit(0)
rows = j["response"]["data"]
with open(os.path.join(outdir, f"df_{now:%Y%m%dT%H%M%S}Z.csv"), "w", newline="") as f:
    w = csv.writer(f); w.writerow(["pulled_at_utc", "respondent", "period_utc", "value"])
    for r in rows: w.writerow([pulled, r["respondent"], r["period"], r["value"]])
with open(os.path.join(outdir, "poll_log.jsonl"), "a") as f:
    f.write(json.dumps({"pulled_at_utc": pulled, "rows": len(rows), "seconds": round(time.time() - t, 2), "retried_error": err,
                        "max_period_by_ba": {b: max([r["period"] for r in rows if r["respondent"] == b], default=None) for b in BAS}}) + "\n")
print(pulled, len(rows), "rows")
