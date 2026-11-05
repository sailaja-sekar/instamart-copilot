import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, f1_score

CUTOFF = pd.Timestamp("2025-09-01")
END = pd.Timestamp("2025-10-01")

orders = pd.read_csv("data/clean/orders.csv", parse_dates=["order_ts"])
customers = pd.read_csv("data/clean/customers.csv", parse_dates=["signup_date"])
products = pd.read_csv("data/clean/products.csv")

# only orders dated before the cutoff may be used for features
before = orders[orders["order_ts"] < CUTOFF]
done_before = before[before["status"] == "completed"]

feat = done_before.groupby("customer_id").agg(
    last_order=("order_ts", "max"),
    frequency=("order_id", "nunique"),
    monetary=("order_amount", "sum"),
    avg_discount=("discount_pct", "mean"),
    avg_delivery=("delivery_minutes", "mean"),
).reset_index()
feat["recency"] = (CUTOFF - feat["last_order"]).dt.days
feat = feat.drop(columns="last_order")

final = before[before["status"].isin(["completed", "cancelled"])]
canc = final.groupby("customer_id")["status"].apply(lambda s: (s == "cancelled").mean())
feat = feat.merge(canc.rename("cancellation_rate"), on="customer_id", how="left")

cat = done_before.merge(products[["product_id", "category"]], on="product_id")
fav = (cat.groupby(["customer_id", "category"]).size().rename("n").reset_index()
          .sort_values(["customer_id", "n", "category"], ascending=[True, False, True])
          .drop_duplicates("customer_id")[["customer_id", "category"]]
          .rename(columns={"category": "favourite_category"}))
feat = feat.merge(fav, on="customer_id", how="left")

feat = feat.merge(customers[["customer_id", "city", "age", "gender", "signup_date"]],
                  on="customer_id", how="left")
feat["tenure_days"] = (CUTOFF - feat["signup_date"]).dt.days
feat = feat.drop(columns="signup_date")

# label: no completed order from 2025-09-01 to 2025-09-30
september = orders[(orders["order_ts"] >= CUTOFF) & (orders["order_ts"] < END)
                   & (orders["status"] == "completed")]
feat["lapsed"] = (~feat["customer_id"].isin(september["customer_id"])).astype(int)

print("cohort:", len(feat), "| lapsed:", int(feat["lapsed"].sum()),
      "| lapse rate:", round(100 * feat["lapsed"].mean(), 2), "%")
features = ["recency", "frequency", "monetary", "avg_discount", "cancellation_rate",
            "avg_delivery", "favourite_category", "city", "age", "gender", "tenure_days"]
X = feat[features]
y = feat["lapsed"]
print("missing values in features:", int(X.isna().sum().sum()))

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, stratify=y, random_state=42)
print("train:", len(X_train), "| test:", len(X_test))

baseline = [0] * len(y_test)
acc = accuracy_score(y_test, baseline)
f1 = f1_score(y_test, baseline, zero_division=0)
print("baseline accuracy:", round(100 * acc, 1), "% | lapsed-class F1:", f1)

assert len(feat) == 1156 and int(feat["lapsed"].sum()) == 443
assert len(X_train) == 924 and len(X_test) == 232
assert round(100 * acc, 1) == 61.6 and f1 == 0
assert X.isna().sum().sum() == 0
print("LAPSE SETUP CHECKS PASSED")