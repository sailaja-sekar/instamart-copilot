import pandas as pd

RAW = "data/raw/"

# =====================================================
# CUSTOMERS CLEANING
# =====================================================
customers = pd.read_csv(RAW + "customers.csv")

# (a) City: remove spaces at the ends, then Title Case
customers["city"] = customers["city"].str.strip().str.title()

# (b) Gender: map every spelling to male, female or unknown
gender_map = {"male": "male", "m": "male", "female": "female", "f": "female"}
customers["gender"] = (
    customers["gender"]
    .fillna("")
    .str.strip()
    .str.lower()
    .map(gender_map)
    .fillna("unknown")
)

# (c) Age: values outside 10-100 become missing, then fill with the city median
bad_age = (customers["age"] < 10) | (customers["age"] > 100)
print("ages set to missing as impossible:", int(bad_age.sum()))
customers["age"] = customers["age"].mask(bad_age)
city_median = customers.groupby("city")["age"].transform("median")
customers["age"] = customers["age"].fillna(city_median)

# (d) signup_date becomes a real date
customers["signup_date"] = pd.to_datetime(customers["signup_date"], errors="raise")

# ---- Show the results ----
print("\nCities:")
print(customers["city"].value_counts())
print("\nGenders:")
print(customers["gender"].value_counts())
print("\nmissing ages:", int(customers["age"].isna().sum()))
print("age min / max:", customers["age"].min(), customers["age"].max())
print("signup_date type:", customers["signup_date"].dtype)

# ---- Checks against the brief ----
assert len(customers) == 1200
assert customers["city"].value_counts().to_dict() == {
    "Pune": 227, "Delhi": 210, "Bengaluru": 197,
    "Chennai": 191, "Hyderabad": 191, "Mumbai": 184,
}
assert customers["gender"].value_counts().to_dict() == {
    "female": 610, "male": 560, "unknown": 30,
}
assert customers["age"].isna().sum() == 0
assert customers["age"].between(18, 60).all()
print("\nCUSTOMER CHECKS PASSED")

# =====================================================
# ORDERS CLEANING
# =====================================================
products = pd.read_csv(RAW + "products.csv")
orders = pd.read_csv(RAW + "orders.csv")
print("\n\nraw order rows:", len(orders))

# Rule 1: order_ts becomes a real date-time
orders["order_ts"] = pd.to_datetime(orders["order_ts"])

# Rule 2: remove exact duplicate rows
before = len(orders)
orders = orders.drop_duplicates()
print("exact duplicates removed:", before - len(orders))

# Rule 3: for each order_id keep only the record with the latest order_ts
before = len(orders)
orders = orders.sort_values("order_ts").drop_duplicates(subset="order_id", keep="last")
print("older pending records removed:", before - len(orders))

# Rule 4: order_amount to numbers; fill missing ones from the product price
orders = orders.merge(products[["product_id", "category", "price_inr"]], on="product_id", how="left")
orders["order_amount"] = pd.to_numeric(orders["order_amount"], errors="coerce")
amount_missing = int(orders["order_amount"].isna().sum())
calculated = pd.Series(
    [round(p * q * (1 - d / 100), 2)
     for p, q, d in zip(orders["price_inr"], orders["quantity"], orders["discount_pct"])],
    index=orders.index,
)
orders["order_amount"] = orders["order_amount"].fillna(calculated)
print("order_amount values filled from price:", amount_missing)

# Rule 5: delivery_minutes
neg = orders["delivery_minutes"] < 0
print("negative delivery times set to missing:", int(neg.sum()))
orders["delivery_minutes"] = orders["delivery_minutes"].mask(neg)

completed = orders["status"] == "completed"
cat_median = orders[completed].groupby("category")["delivery_minutes"].transform("median")
filled_before = int(orders.loc[completed, "delivery_minutes"].isna().sum())
orders.loc[completed, "delivery_minutes"] = orders.loc[completed, "delivery_minutes"].fillna(cat_median)
print("completed delivery times filled with category median:", filled_before)
# cancelled orders are left missing on purpose

# ---- Checks against the brief ----
print("\nrows:", len(orders))
print(orders["status"].value_counts())
print("missing order_amount:", int(orders["order_amount"].isna().sum()))
print("missing delivery (completed):", int(orders.loc[completed, "delivery_minutes"].isna().sum()))
print("missing delivery (cancelled):", int(orders.loc[~completed, "delivery_minutes"].isna().sum()))
total = orders.loc[completed, "order_amount"].sum()
print("completed revenue:", round(total, 2))

assert len(orders) == 12309
assert orders["order_id"].is_unique
assert (orders["status"] == "completed").sum() == 11110
assert (orders["status"] == "cancelled").sum() == 1199
assert (orders["status"] == "pending").sum() == 0
assert orders["order_amount"].isna().sum() == 0
assert orders.loc[completed, "delivery_minutes"].isna().sum() == 0
assert orders.loc[~completed, "delivery_minutes"].isna().sum() == 1199
assert abs(total - 2998668.80) < 0.01
print("\nORDER CHECKS PASSED")

# keep the original 9 columns only (drop the helper columns used for filling)
orders = orders.drop(columns=["category", "price_inr"])
# =====================================================
# SAVE CLEAN TABLES (CSV + SQLITE)
# =====================================================
import os
import sqlite3

os.makedirs("data/clean", exist_ok=True)

# dates are stored as text in the required formats
customers_out = customers.copy()
customers_out["signup_date"] = customers_out["signup_date"].dt.strftime("%Y-%m-%d")

orders_out = orders.copy()
orders_out["order_ts"] = orders_out["order_ts"].dt.strftime("%Y-%m-%d %H:%M:%S")
orders_out = orders_out.sort_values("order_id")

customers_out.to_csv("data/clean/customers.csv", index=False)
products.to_csv("data/clean/products.csv", index=False)
orders_out.to_csv("data/clean/orders.csv", index=False)

# start from a fresh database every run so the result is reproducible
db_path = "data/instamart.db"
if os.path.exists(db_path):
    os.remove(db_path)

con = sqlite3.connect(db_path)
customers_out.to_sql("customers", con, index=False)
products.to_sql("products", con, index=False)
orders_out.to_sql("orders", con, index=False)
con.close()

print("\nSaved: data/clean/customers.csv, products.csv, orders.csv and data/instamart.db")