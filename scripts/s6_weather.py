"""Step 6: Open-Meteo Previous Runs API (day-ahead = *_previous_day1) for 5 ISO-NE cities, vs Historical API."""
import requests, time, json, datetime as dt, pandas as pd
CITIES = {"Boston": (42.3601, -71.0589), "Hartford": (41.7658, -72.6734), "Providence": (41.8240, -71.4128),
          "Portland ME": (43.6591, -70.2568), "Burlington VT": (44.4759, -73.2121)}
lat = ",".join(str(v[0]) for v in CITIES.values()); lon = ",".join(str(v[1]) for v in CITIES.values())
today = dt.date.today().isoformat(); out = {}
def weight(n_loc, n_vars, n_days):  # Open-Meteo documented fractional call counting
    return n_loc * max(1, n_vars / 10) * max(1, n_days / 14)

def call(url, params, label):
    t = time.time(); r = requests.get(url, params=params, timeout=300); el = time.time() - t
    print(label, r.status_code, f"{el:.1f}s", {k: v for k, v in r.headers.items() if "limit" in k.lower() or "usage" in k.lower()})
    if r.status_code != 200: print(r.text[:500]); return None, el
    j = r.json(); j = j if isinstance(j, list) else [j]; return j, el

# A) one multi-location call, previous_day1 + day0 for comparison, 2024-01-01..today
p = {"latitude": lat, "longitude": lon, "hourly": "temperature_2m,temperature_2m_previous_day1",
     "start_date": "2024-01-01", "end_date": today, "timezone": "GMT"}
j, el = call("https://previous-runs-api.open-meteo.com/v1/forecast", p, "previous-runs multi")
ndays = (dt.date.today() - dt.date(2024, 1, 1)).days + 1
res = {"previous_runs": {"seconds": round(el, 1), "http_requests": 1, "n_days": ndays,
       "counted_calls_per_docs": weight(5, 2, ndays), "cities": {}}}
for name, loc in zip(CITIES, j):
    h = pd.DataFrame(loc["hourly"]); h["time"] = pd.to_datetime(h["time"])
    d1 = h.dropna(subset=["temperature_2m_previous_day1"])
    res["previous_runs"]["cities"][name] = {"rows": len(h), "day1_nonnull": len(d1),
        "day1_first": str(d1.time.min()), "day1_last": str(d1.time.max()),
        "day1_null_pct": round(100 * (1 - len(d1) / len(h)), 2),
        "mae_day1_vs_day0_C": round((h.temperature_2m_previous_day1 - h.temperature_2m).abs().mean(), 2),
        "grid_lat": loc["latitude"], "grid_lon": loc["longitude"]}
    h.assign(city=name).to_parquet(f"data/s6_prevruns_{name.replace(' ', '_')}.parquet")
# B) Historical Weather API, last 3 available days (archive lags ~5 days)
s, e = (dt.date.today() - dt.timedelta(days=8)).isoformat(), (dt.date.today() - dt.timedelta(days=6)).isoformat()
p2 = {"latitude": lat, "longitude": lon, "hourly": "temperature_2m", "start_date": s, "end_date": e, "timezone": "GMT"}
j2, el2 = call("https://archive-api.open-meteo.com/v1/archive", p2, "archive multi")
res["historical_3d"] = {"seconds": round(el2, 1), "http_requests": 1, "range": [s, e], "counted_calls_per_docs": weight(5, 1, 3),
    "rows_total": sum(len(x["hourly"]["time"]) for x in j2), "nulls": sum(pd.Series(x["hourly"]["temperature_2m"]).isna().sum() for x in j2)}
# C) same 3 days from previous-runs for apples-to-apples speed + error
p3 = dict(p, start_date=s, end_date=e)
j3, el3 = call("https://previous-runs-api.open-meteo.com/v1/forecast", p3, "previous-runs 3d")
res["previous_runs_3d"] = {"seconds": round(el3, 1), "counted_calls_per_docs": weight(5, 2, 3)}
err = []
for a, b in zip(j2, j3):
    err.append((pd.Series(b["hourly"]["temperature_2m_previous_day1"]) - pd.Series(a["hourly"]["temperature_2m"])).abs().mean())
res["previous_runs_3d"]["mae_day1_forecast_vs_archive_C"] = [round(x, 2) for x in err]
print(json.dumps(res, indent=1, default=str)); json.dump(res, open("out/s6_weather.json", "w"), indent=1, default=str)
