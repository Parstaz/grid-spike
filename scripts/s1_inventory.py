"""Step 1: BA inventory. BA list + names from API facets; per-BA stats from ALL EIA-930 BALANCE bulk files
(API history only starts 2019-01, and paging it for history is what we're avoiding). Last timestamps are
also checked against the live API (30-day pull from step 3, if present)."""
import os, io, json, requests, pandas as pd, numpy as np
from eia import key, REGIONS, ROOT
B = "https://www.eia.gov/electricity/gridmonitor/sixMonthFiles/"
D = os.path.join(ROOT, "data", "bulk"); os.makedirs(D, exist_ok=True)
files = [f"EIA930_BALANCE_{y}_{h}.csv" for y in range(2015, 2027) for h in ("Jan_Jun", "Jul_Dec")][1:]
COLS = {"Demand (MW)": "D", "Demand Forecast (MW)": "DF", "Net Generation (MW)": "NG", "Total Interchange (MW)": "TI", "Demand (MW) (Adjusted)": "D_adj"}
parts = []
for f in files:
    p = os.path.join(D, f.replace(".csv", ".parquet"))
    if not os.path.exists(p):
        r = requests.get(B + f, timeout=300); r.raise_for_status()
        df = pd.read_csv(io.BytesIO(r.content), low_memory=False, thousands=",")
        keep = ["Balancing Authority", "UTC Time at End of Hour"] + [c for c in COLS if c in df.columns]
        df = df[keep].rename(columns={"Balancing Authority": "ba", "UTC Time at End of Hour": "utc", **COLS})
        df["utc"] = pd.to_datetime(df["utc"], format="%m/%d/%Y %I:%M:%S %p")
        for c in COLS.values():
            if c in df: df[c] = pd.to_numeric(df[c], errors="coerce")
        df.to_parquet(p); print("got", f, len(df))
    parts.append(pd.read_parquet(p))
h = pd.concat(parts, ignore_index=True).drop_duplicates(["ba", "utc"], keep="last")
h.to_parquet(os.path.join(ROOT, "data", "bulk_balance_all.parquet"))
now = pd.Timestamp.utcnow().tz_localize(None)
fac = requests.get("https://api.eia.gov/v2/electricity/rto/region-data/facet/respondent", params={"api_key": key()}, timeout=60).json()["response"]["facets"]
names = {f["id"]: f["name"] for f in fac}
live = {}
lp = os.path.join(ROOT, "data", "s3_30d.parquet")
if os.path.exists(lp):
    l = pd.read_parquet(lp); l = l[l.value.notna()]
    live = l.groupby(["respondent", "type"]).period.max().unstack().to_dict("index")
out = []
for ba in sorted(set(names) | set(h.ba)):
    g = h[h.ba == ba].sort_values("utc"); row = {"ba": ba, "name": names.get(ba, ""), "is_region": ba in REGIONS,
        "in_api": ba in names, "in_bulk": len(g) > 0}
    for s in ["D", "DF", "NG", "TI"]:
        v = g[["utc", s]].dropna() if s in g else g.iloc[0:0]
        row[f"has_{s}"] = len(v) > 0
        row[f"{s}_first_utc"] = v.utc.min() if len(v) else pd.NaT
        row[f"{s}_last_utc"] = v.utc.max() if len(v) else pd.NaT
        row[f"{s}_last_utc_api30d"] = (live.get(ba) or {}).get(s)
        if len(v):  # missing hours within the series' own active span
            span = int((v.utc.max() - v.utc.min()) / pd.Timedelta("1h")) + 1
            row[f"{s}_pct_missing_hours"] = round(100 * (1 - len(v) / span), 2)
    d = g["D"].dropna() if "D" in g else pd.Series(dtype=float)
    if len(d):
        row["D_pct_zero_or_neg"] = round(100 * (d <= 0).mean(), 3)
        ref = g["D_adj"].max() if "D_adj" in g and g["D_adj"].notna().any() else np.nan
        row["D_hist_max_ref_MW(adjusted series max)"] = ref
        row["D_raw_max_MW"] = d.max()
        row["D_count_gt_1.5x_hist_max"] = int((d > 1.5 * ref).sum()) if pd.notna(ref) else None
        row["D_pct_missing_last_365d"] = round(100 * (1 - g[(g.utc > now - pd.Timedelta("365D"))]["D"].notna().sum() / 8760), 2)
        if len(v := g[["utc", "DF"]].dropna()):
            row["DF_pct_missing_last_365d"] = round(100 * (1 - len(v[v.utc > now - pd.Timedelta("365D")]) / 8760), 2)
    last = max([x for x in [row.get("D_last_utc"), row.get("NG_last_utc")] if pd.notna(x)], default=pd.NaT)
    flags = []
    if pd.notna(last) and last < now - pd.Timedelta("30D"): flags.append("STOPPED_REPORTING")
    if not row.get("has_D"): flags.append("NO_DEMAND")
    if not row.get("has_DF"): flags.append("NO_DF")
    if row["in_api"] and not row["in_bulk"]: flags.append("API_ONLY")
    if row["in_bulk"] and not row["in_api"]: flags.append("BULK_ONLY")
    row["flags"] = ";".join(flags); out.append(row)
t = pd.DataFrame(out); t.to_csv(os.path.join(ROOT, "out", "s1_ba_inventory.csv"), index=False)
print(t[["ba", "is_region", "has_D", "has_DF", "D_first_utc", "D_last_utc", "D_pct_missing_hours", "D_pct_zero_or_neg", "D_count_gt_1.5x_hist_max", "flags"]].to_string())
