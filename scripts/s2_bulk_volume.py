"""Step 2: download one EIA-930 six-month BALANCE file, measure sizes as CSV/gzip/Parquet."""
import gzip, os, shutil, sys, time, json
import pandas as pd, requests

URL = "https://www.eia.gov/electricity/gridmonitor/sixMonthFiles/EIA930_BALANCE_2026_Jan_Jun.csv"
D = os.path.expanduser("~/grid-spike/data"); os.makedirs(D, exist_ok=True)
csv = os.path.join(D, os.path.basename(URL))
t = time.time()
with requests.get(URL, stream=True, timeout=120, headers={"Accept-Encoding": "gzip"}) as r:
    r.raise_for_status(); wire_enc = r.headers.get("Content-Encoding"); 
    with open(csv, "wb") as f:
        for c in r.iter_content(1 << 20): f.write(c)
dl = time.time() - t
with open(csv, "rb") as a, gzip.open(csv + ".gz", "wb", 6) as b: shutil.copyfileobj(a, b)
df = pd.read_csv(csv, low_memory=False, thousands=",")
res = {"url": URL, "download_s": round(dl, 1), "server_content_encoding": wire_enc,
       "rows": len(df), "cols": len(df.columns), "columns": list(df.columns),
       "n_BAs": df.iloc[:, 0].nunique(),
       "csv_MB": os.path.getsize(csv) / 1e6, "csv_gzip_MB": os.path.getsize(csv + ".gz") / 1e6}
for comp in ["snappy", "zstd"]:
    p = os.path.join(D, f"bulk_{comp}.parquet"); df.to_parquet(p, compression=comp, index=False)
    res[f"parquet_{comp}_MB_wide_as_published"] = os.path.getsize(p) / 1e6
# long format: just the core series (BA, utc ts, series, value) – what a pipeline would store
ts = [c for c in df.columns if "UTC" in c and "Time" in c][0]
core = {c: c for c in df.columns if c in ("Demand (MW)", "Demand Forecast (MW)", "Net Generation (MW)", "Total Interchange (MW)")}
long = df[["Balancing Authority", ts, *core]].melt(id_vars=["Balancing Authority", ts], var_name="series", value_name="mw").dropna()
long[ts] = pd.to_datetime(long[ts]); long["series"] = long["series"].astype("category"); long["Balancing Authority"] = long["Balancing Authority"].astype("category")
p = os.path.join(D, "bulk_long_core.parquet"); long.to_parquet(p, compression="zstd", index=False)
res["long_core_rows"] = len(long); res["parquet_zstd_MB_long_core_D_DF_NG_TI"] = os.path.getsize(p) / 1e6
res["timestamp_col"] = ts; res["ts_min"] = str(df[ts].min()); res["ts_max"] = str(df[ts].max())
print(json.dumps(res, indent=1, default=str))
json.dump(res, open(os.path.expanduser("~/grid-spike/out/s2_bulk_volume.json"), "w"), indent=1, default=str)
