"""Write a SYNTHETIC stint file shaped like the detention records.

Every facility, person and number here is invented. It exists so the
pipeline and the page can be exercised before a real file is in data/raw/.
"""
import numpy as np
import pandas as pd
from pathlib import Path

rng = np.random.default_rng(7)
FAC = [  # code, name, state, hub weight
    ("SAMPA", "Sample Facility A", "CA", 1), ("SAMPB", "Sample Facility B", "CA", 1),
    ("SAMPC", "Sample Facility C", "AZ", 3), ("SAMPD", "Sample Facility D", "TX", 6),
    ("SAMPE", "Sample Facility E", "TX", 4), ("SAMPF", "Sample Facility F", "LA", 8),
    ("SAMPG", "Sample Facility G", "LA", 5), ("SAMPH", "Sample Facility H", "GA", 3),
    ("SAMPI", "Sample Facility I", "NJ", 1), ("SAMPJ", "Sample Facility J", "WA", 1),
    ("SAMPK", "Sample Hold Room K", "IL", 1), ("SAMPL", "Sample Facility L", "MS", 3),
]
codes = [f[0] for f in FAC]
w = np.array([f[3] for f in FAC], float)

rows = []
start = pd.Timestamp("2025-03-01")
for pid in range(9000):
    t = start + pd.Timedelta(hours=float(rng.uniform(0, 365 * 24)))
    cur = rng.choice(codes)
    for stint in range(1, int(rng.choice([1, 2, 3, 4], p=[.45, .3, .17, .08])) + 1):
        stay = float(rng.gamma(2.0, 9.0)) * 24  # hours
        out = t + pd.Timedelta(hours=stay)
        rows.append((f"P{pid:06d}", stint, cur, t, out))
        p = w.copy(); p[codes.index(cur)] = 0; p /= p.sum()
        cur = rng.choice(codes, p=p)
        t = out + pd.Timedelta(hours=float(rng.uniform(1, 14)))

df = pd.DataFrame(rows, columns=["person", "n", "detention_facility_code", "book_in_date_time", "book_out_date_time"])
df["stay_ID"] = df["person"]                       # one stay per invented person
last = df.groupby("person")["n"].transform("max") == df["n"]
df["detention_release_reason"] = np.where(last, rng.choice(["Removed", "Paroled"], len(df), p=[.7, .3]), "Transferred")
df["duplicate_drop_row"] = False
names = {c: (n, s) for c, n, s, _ in FAC}
df["detention_facility"] = df["detention_facility_code"].map(lambda c: names[c][0])
df["city"] = "Sampletown"; df["state"] = df["detention_facility_code"].map(lambda c: names[c][1])
df = df.drop(columns=["person", "n"])
# deliberately dirty rows, like the real records have
df.loc[df.sample(40, random_state=1).index, "duplicate_drop_row"] = True
out = Path(__file__).parent.parent / "data" / "sample"
out.mkdir(parents=True, exist_ok=True)
df.to_csv(out / "stints_sample.csv", index=False)
pd.DataFrame([(c, n, "Sampletown", s, "1 Sample Rd", "Sample office") for c, n, s, _ in FAC], columns=["detention_facility_code", "name", "city", "state", "address_full", "field_office"]).to_csv(out / "facilities_sample.csv", index=False)
print(len(df), "synthetic stints written")
