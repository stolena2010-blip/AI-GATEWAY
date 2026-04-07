"""Generate customer-email matching Excel from automation logs + contacts."""
import json
import pandas as pd
from collections import defaultdict

# 1. Load contacts
contacts = pd.read_excel("BOM/אנשי קשר.xlsx", sheet_name=0)
contacts.columns = ["company", "email"]
contacts["email"] = contacts["email"].str.strip().str.lower()
contacts = contacts.dropna(subset=["email"])

# Build email -> company map
email_to_company = {}
for _, row in contacts.iterrows():
    em = row["email"]
    if em and em not in email_to_company:
        email_to_company[em] = row["company"]

# Build domain -> most common company
domain_companies = defaultdict(lambda: defaultdict(int))
for _, row in contacts.iterrows():
    em = row["email"]
    comp = row["company"]
    if em and "@" in em and comp:
        domain = em.split("@")[1]
        domain_companies[domain][comp] += 1

domain_to_company = {}
for domain, comps in domain_companies.items():
    domain_to_company[domain] = max(comps, key=comps.get)

print(f"Contacts: {len(contacts)} rows, {len(email_to_company)} unique emails, {len(domain_to_company)} domains")

# 1b. Load end-customer names from sheet 2
df_end = pd.read_excel("BOM/אנשי קשר.xlsx", sheet_name=1, header=None)
end_customer_names_raw = [str(v).strip() for v in df_end[0].dropna().tolist() if str(v).strip()]
# Remove " (Subscriber)" suffix and build clean list
end_customer_names = []
for name in end_customer_names_raw:
    clean = name.replace("(Subscriber)", "").strip()
    end_customer_names.append(clean)
print(f"End customers (sheet 2): {len(end_customer_names)}")

# Build keyword lookup for fuzzy matching — use SPECIFIC words only
_end_customer_keywords = {}
_generic_words = {
    "the", "ltd", "ltd.", "group", "aerospace", "company", "corporation",
    "industries", "engineering", "aircraft", "systems", "subscriber",
}
for name in end_customer_names:
    words = name.lower().split()
    for w in words:
        if len(w) > 2 and w not in _generic_words:
            _end_customer_keywords[w] = name

# Manual aliases for known short names
_manual_aliases = {
    "iai": "Israel Aerospace Industries",
    "israel aircraft industries": "Israel Aerospace Industries",
    "boeing": "The Boeing Company",
    "mcdonnell douglas": "The Boeing Company",
    "sikorsky": "Sikorsky Aircraft",
    "lockheed": "Lockheed Martin Corporation",
    "lockheed martin": "Lockheed Martin Corporation",
    "honeywell": "Honeywell Aerospace",
    "collins": "Collins Aerospace (Goodrich)",
    "goodrich": "Collins Aerospace (Goodrich)",
    "hamilton sundstrand": "Collins Aerospace (Hamilton Sundstrand)",
    "parker": "Parker Aerospace Group",
    "eaton": "Eaton Aerospace",
    "gkn": "GKN Aerospace Filton",
    "st engineering": "ST Engineering Aerospace Ltd",
}


def match_end_customer(drawing_customer: str) -> str:
    """Try to match a drawing customer name to an end-customer from sheet 2."""
    if not drawing_customer:
        return ""
    dc_lower = drawing_customer.strip().lower()
    # 1. Manual alias (exact or substring)
    for alias, name in _manual_aliases.items():
        if alias == dc_lower or alias in dc_lower or dc_lower in alias:
            return name
    # 2. Direct substring match against end customer names
    for name in end_customer_names:
        nl = name.lower()
        if nl in dc_lower or dc_lower in nl:
            return name
        # First significant word of end customer
        for w in nl.split():
            if len(w) > 3 and w not in _generic_words and w in dc_lower:
                return name
    # 3. Specific keyword match (non-generic words only)
    for w in dc_lower.split():
        if w in _end_customer_keywords and w not in _generic_words:
            return _end_customer_keywords[w]
    return ""

# 2. Load automation log
log_entries = []
for log_file in ["automation_log.jsonl", "automation_log_20260330.jsonl"]:
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entry = json.loads(line)
                        if entry.get("event") in (None, "processed"):
                            log_entries.append(entry)
                    except Exception:
                        pass
    except Exception:
        pass

print(f"Log entries: {len(log_entries)}")

# 3. Build sender statistics
sender_stats = defaultdict(lambda: {
    "mails": 0, "items": 0, "customers": defaultdict(int),
    "high": 0, "medium": 0, "low": 0, "cost_usd": 0.0
})

for e in log_entries:
    sender = (e.get("sender") or "").strip().lower()
    if not sender:
        continue

    s = sender_stats[sender]
    s["mails"] += 1
    items = e.get("items_count", 0) or e.get("files_processed", 0) or 0
    s["items"] += items
    s["cost_usd"] += float(e.get("cost_usd", 0) or 0)

    acc = e.get("accuracy_data", {})
    s["high"] += (acc.get("full", 0) or 0) + (acc.get("high", 0) or 0)
    s["medium"] += acc.get("medium", 0) or 0
    s["low"] += acc.get("low", 0) or 0

    for c in e.get("customers", []):
        c = c.strip()
        if c:
            s["customers"][c] += 1

print(f"Unique senders with stats: {len(sender_stats)}")

# 4. Match and build output
rows = []
for sender, stats in sorted(sender_stats.items(), key=lambda x: -x[1]["items"]):
    customers = dict(stats["customers"])
    main_customer = max(customers, key=customers.get) if customers else ""
    all_customers = ", ".join(
        f"{c} ({n})" for c, n in sorted(customers.items(), key=lambda x: -x[1])
    )

    # Match to contacts
    contact_company = email_to_company.get(sender, "")
    if not contact_company and "@" in sender:
        domain = sender.split("@")[1]
        contact_company = domain_to_company.get(domain, "")

    if sender in email_to_company:
        match_type = "מייל מדויק"
    elif contact_company:
        match_type = "דומיין"
    else:
        match_type = "לא נמצא"

    # Match main_customer to end-customer list (sheet 2)
    end_customer = match_end_customer(main_customer)

    rows.append({
        "לקוח סופי (שרטוט)": main_customer,
        "חברה/איש קשר": contact_company,
        "מייל שולח": sender,
        "כמות שרטוטים": stats["items"],
        "לקוח סופי (גיליון 2)": end_customer,
    })

df_out = pd.DataFrame(rows)
output_path = "התאמות_לקוחות_שרטוטים.xlsx"

with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
    df_out.to_excel(writer, sheet_name="התאמות", index=False)

print(f"\nSaved: {output_path}")
print(f"Total rows: {len(df_out)}")
matched_end = sum(1 for r in rows if r["לקוח סופי (גיליון 2)"])
print(f"Matched to end-customer (sheet 2): {matched_end}/{len(rows)}")
