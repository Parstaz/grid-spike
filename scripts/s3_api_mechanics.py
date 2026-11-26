"""Step 3: time a paginated pull of last 30 days of D+DF for all respondents; verify UTC; BA timezones."""
import os, io, time, json, requests, pandas as pd
from eia import fetch, ROOT, key
now = pd.Timestamp.utcnow().floor("h").tz_localize(None)
start, end = (now - pd.Timedelta("30D")).strftime("%Y-%m-%dT%H"), (now + pd.Timedelta("3D")).strftime("%Y-%m-%dT%H")
t = time.time(); df, log = fetch(["D", "DF"], start, end); el = time.time() - t
df.to_parquet(os.path.join(ROOT, "data", "s3_30d.parquet"))
bad = [l for l in log if l["status"] != 200]
res = {"window_utc": [start, end], "rows": len(df), "respondents": df.respondent.nunique(),
       "http_requests": len(log), "pages": sum(1 for l in log if l["status"] == 200), "total_seconds": round(el, 1),
       "median_req_s": float(pd.Series([l["seconds"] for l in log]).median()), "max_req_s": max(l["seconds"] for l in log),
       "non200": bad, "warnings": [l["warnings"] for l in log if l.get("warnings")][:3],
       "columns": list(df.columns), "period_example": df.period.iloc[0]}
# page size probe: does the API cap length at 5000?
r = requests.get("https://api.eia.gov/v2/electricity/rto/region-data/data/", params={"api_key": key(), "frequency": "hourly", "data[0]": "value", "start": start, "length": 10000}, timeout=60).json()
res["length_10000_probe"] = {"returned": len(r["response"].get("data", [])), "warnings": r["response"].get("warnings")}
# UTC check: same ISNE D, hourly (UTC) vs local-hourly
day = (now - pd.Timedelta("3D")).strftime("%Y-%m-%d")
u, _ = fetch(["D"], f"{day}T00", f"{day}T23", ["ISNE"], "hourly")
lh, _ = fetch(["D"], f"{day}T00", f"{day}T23", ["ISNE"], "local-hourly")
lh["utc_from_local"] = pd.to_datetime(lh.period.str[:13] + ":00" + lh.period.str[13:] + ":00", utc=True).dt.tz_localize(None) if lh.period.str.len().iloc[0] > 13 else None
u["utc"] = pd.to_datetime(u.period)
m = u.merge(lh, left_on="utc", right_on="utc_from_local", suffixes=("_utc", "_local"))
res["utc_check"] = {"hourly_period_sample": u.period.head(2).tolist(), "local_hourly_period_sample": lh.period.head(2).tolist(),
                    "matched_hours": len(m), "values_equal": bool((m.value_utc == m.value_local).all()) if len(m) else None}
# timezone per BA: EIA-930 reference table
x = requests.get("https://www.eia.gov/electricity/930-content/EIA930_Reference_Tables.xlsx", timeout=60).content
ref = pd.read_excel(io.BytesIO(x), sheet_name=None)
res["reference_sheets"] = {k: list(v.columns) for k, v in ref.items()}
ba = list(ref.values())[0]; ba.to_csv(os.path.join(ROOT, "out", "s3_ba_reference_table.csv"), index=False)
print(json.dumps(res, indent=1, default=str)); json.dump(res, open(os.path.join(ROOT, "out", "s3_api_mechanics.json"), "w"), indent=1, default=str)
