"""Tiny shared helper: EIA v2 paginated fetch with request/timing/error log. Key from env or .env."""
import os, time, requests, pandas as pd
ROOT = os.path.expanduser("~/grid-spike") if os.path.isdir(os.path.expanduser("~/grid-spike")) else "."
def key():
    k = os.environ.get("EIA_API_KEY")
    if not k and os.path.exists(os.path.join(ROOT, ".env")):
        for line in open(os.path.join(ROOT, ".env")):
            if line.startswith("EIA_API_KEY="): k = line.split("=", 1)[1].strip().strip('"\'')
    if not k: raise SystemExit("EIA_API_KEY not set")
    return k
URL = "https://api.eia.gov/v2/electricity/rto/region-data/data/"
REGIONS = {"CAL","CAR","CENT","FLA","MIDA","MIDW","NE","NW","NY","SE","SW","TEN","TEX","US48"}

def fetch(types, start, end, respondents=None, freq="hourly", page=5000, log=None):
    """start/end like 2026-11-01T00. Returns (df, log). log = list of per-request dicts."""
    log = [] if log is None else log; rows, off, k = [], 0, key()
    while True:
        p = [("api_key", k), ("frequency", freq), ("data[0]", "value"), ("start", start), ("end", end),
             ("sort[0][column]", "period"), ("sort[0][direction]", "asc"),
             ("sort[1][column]", "respondent"), ("sort[1][direction]", "asc"),
             ("sort[2][column]", "type"), ("sort[2][direction]", "asc"),
             ("offset", off), ("length", page)] + [("facets[type][]", t) for t in types]
        p += [("facets[respondent][]", r) for r in (respondents or [])]
        for attempt in range(6):
            t = time.time()
            try:
                r = requests.get(URL, params=p, timeout=120); st = r.status_code
            except requests.RequestException as e:
                r, st = None, f"EXC {type(e).__name__}"
            el = time.time() - t
            entry = {"offset": off, "attempt": attempt, "status": st, "seconds": round(el, 2)}
            if r is not None and st == 200:
                j = r.json(); resp = j.get("response", {})
                entry.update(total=int(resp.get("total", 0)), n=len(resp.get("data", [])), warnings=j.get("response", {}).get("warnings"))
                log.append(entry); break
            entry["body"] = (r.text[:300] if r is not None else ""); log.append(entry)
            time.sleep(2 ** attempt)
        else:
            raise RuntimeError(f"failed at offset {off}: {log[-1]}")
        rows += resp["data"]; off += len(resp["data"])
        if not resp["data"] or off >= entry["total"]: break
    df = pd.DataFrame(rows)
    if len(df): df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df, log
