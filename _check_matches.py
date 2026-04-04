import pandas as pd
df = pd.read_excel("התאמות_לקוחות_שרטוטים.xlsx")
matched = df[df["לקוח סופי (גיליון 2)"].notna() & (df["לקוח סופי (גיליון 2)"] != "")]
print(f"Matched rows: {len(matched)}")
print()
for _, r in matched.iterrows():
    c1 = str(r["לקוח סופי (שרטוט)"])
    c2 = str(r["לקוח סופי (גיליון 2)"])
    n = r["כמות שרטוטים"]
    print(f"  {c1:30s} -> {c2:40s} ({n} drawings)")
