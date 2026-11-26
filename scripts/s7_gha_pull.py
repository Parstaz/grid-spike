"""Step 7: the Actions-side pull: last 2 days D+DF for all respondents + 1 Open-Meteo call -> Parquet."""
import os, sys, time, json, requests, pandas as pd
sys.path.insert(0, os.path.dirname(__file__)); from eia import fetch
os.makedirs("artifact", exist_ok=True); now = pd.Timestamp.utcnow().floor("h").tz_localize(None); rep = {}
t = time.time(); df, log = fetch(["D", "DF"], (now - pd.Timedelta("2D")).strftime("%Y-%m-%dT%H"), (now + pd.Timedelta("2D")).strftime("%Y-%m-%dT%H"))
rep["eia"] = {"rows": len(df), "requests": len(log), "seconds": round(time.time() - t, 2), "non200": [l for l in log if l["status"] != 200]}
df.to_parquet("artifact/eia_D_DF_2d.parquet")
t = time.time()
r = requests.get("https://previous-runs-api.open-meteo.com/v1/forecast", timeout=60, params={"latitude": "42.3601,41.7658,41.8240,43.6591,44.4759",
    "longitude": "-71.0589,-72.6734,-71.4128,-70.2568,-73.2121", "hourly": "temperature_2m_previous_day1", "past_days": 2, "forecast_days": 2, "timezone": "GMT"})
rep["open_meteo"] = {"status": r.status_code, "seconds": round(time.time() - t, 2), "cost_header": r.headers.get("X-RateLimit-Cost"), "body_if_error": r.text[:300] if r.status_code != 200 else None}
if r.status_code == 200:
    w = pd.concat([pd.DataFrame(x["hourly"]).assign(loc=i) for i, x in enumerate(r.json())]); w.to_parquet("artifact/weather.parquet"); rep["open_meteo"]["rows"] = len(w)
json.dump(rep, open("artifact/report.json", "w"), indent=1, default=str); print(json.dumps(rep, indent=1, default=str))
