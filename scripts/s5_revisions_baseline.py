"""Step 5 (Day 1) / Step 8 (Day 2): pull last 7 days of D for all respondents with pull timestamp. Day-2 mode diffs."""
import os, sys, json, pandas as pd
from eia import fetch, ROOT
base = os.path.join(ROOT, "out", "s5_D_7d_day1.parquet")
if len(sys.argv) == 1:  # Day 1
    now = pd.Timestamp.utcnow().floor("h").tz_localize(None); pulled = pd.Timestamp.utcnow().isoformat()
    s, e = (now - pd.Timedelta("7D")).strftime("%Y-%m-%dT%H"), now.strftime("%Y-%m-%dT%H")
    df, log = fetch(["D"], s, e); df["pulled_at_utc"] = pulled; df.attrs = {}
    df.to_parquet(base); json.dump({"window": [s, e], "pulled_at_utc": pulled, "rows": len(df), "requests": len(log)}, open(base + ".meta.json", "w"))
    print(len(df), "rows", s, e, pulled)
else:  # Day 2: python s5_revisions_baseline.py diff
    d1 = pd.read_parquet(base); meta = json.load(open(base + ".meta.json"))
    d2, log = fetch(["D"], *meta["window"]); d2["pulled_at_utc"] = pd.Timestamp.utcnow().isoformat()
    d2.to_parquet(os.path.join(ROOT, "out", "s8_D_7d_day2.parquet"))
    m = d1.merge(d2, on=["respondent", "period", "type"], how="outer", suffixes=("_1", "_2"), indicator=True)
    m["changed"] = (m._merge == "both") & ~((m.value_1 == m.value_2) | (m.value_1.isna() & m.value_2.isna()))
    m["abs_delta"] = (m.value_2 - m.value_1).abs(); m["pct_delta"] = 100 * m.abs_delta / m.value_1.abs()
    m.to_parquet(os.path.join(ROOT, "out", "s8_diff.parquet"))
    by = m[m.changed].groupby("respondent").agg(n_changed=("changed", "size"), max_abs_MW=("abs_delta", "max"), median_abs_MW=("abs_delta", "median"), max_pct=("pct_delta", "max"),
                                               first=("period", "min"), last=("period", "max")).sort_values("n_changed", ascending=False)
    by.to_csv(os.path.join(ROOT, "out", "s8_revisions_by_ba.csv"))
    print({"compared": int((m._merge == "both").sum()), "changed": int(m.changed.sum()), "only_day1": int((m._merge == "left_only").sum()), "only_day2(backfilled)": int((m._merge == "right_only").sum()),
           "null->value": int((m.value_1.isna() & m.value_2.notna()).sum()), "bas_changed": len(by)}); print(by.to_string())
