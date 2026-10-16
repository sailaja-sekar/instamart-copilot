import pandas as pd

RAW = "data/raw/"

customers = pd.read_csv(RAW + "customers.csv")
products = pd.read_csv(RAW + "products.csv")
orders = pd.read_csv(RAW + "orders.csv")

# ---- Part 1: shape, data types, missing values for each table ----
for name, df in [("customers", customers), ("products", products), ("orders", orders)]:
    print("\n" + "=" * 70)
    print(f"{name.upper()} | shape: {df.shape}")
    print("\nData types:")
    print(df.dtypes)
    missing = pd.DataFrame({
        "missing_count": df.isna().sum(),
        "missing_pct": (df.isna().mean() * 100).round(2),
    })
    print("\nMissing values:")
    print(missing.to_string())

# ---- Part 2: the 12 audit figures ----
amount_num = pd.to_numeric(orders["order_amount"], errors="coerce")

audit = {
    "raw order rows": (len(orders), 13084),
    "exact duplicate rows": (int(orders.duplicated().sum()), 119),
    "pending rows": (int((orders["status"] == "pending").sum()), 656),
    "distinct order_id": (int(orders["order_id"].nunique()), 12309),
    "non-numeric amounts": (int(amount_num.isna().sum()), 120),
    "negative delivery_minutes": (int((orders["delivery_minutes"] < 0).sum()), 106),
    "blank delivery_minutes": (int(orders["delivery_minutes"].isna().sum()), 2541),
    "blank age": (int(customers["age"].isna().sum()), 61),
    "age outside 10-100": (int(((customers["age"] < 10) | (customers["age"] > 100)).sum()), 6),
    "raw city spellings": (int(customers["city"].nunique()), 24),
    "raw gender spellings": (int(customers["gender"].dropna().nunique()), 10),
    "blank gender": (int(customers["gender"].isna().sum()), 30),
}

print("\n" + "=" * 70)
print(f"{'check':30} {'mine':>8} {'reference':>10}  result")
all_ok = True
for label, (mine, ref) in audit.items():
    ok = mine == ref
    all_ok = all_ok and ok
    print(f"{label:30} {mine:>8} {ref:>10}  {'OK' if ok else 'DIFFERENT'}")

print("\nAll 12 checks match." if all_ok else "\nSome checks differ: investigate before Day 2.")