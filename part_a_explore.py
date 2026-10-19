import numpy as np
import pandas as pd

customers = pd.read_csv("data/clean/customers.csv")
products = pd.read_csv("data/clean/products.csv")
orders = pd.read_csv("data/clean/orders.csv")

# only completed orders count as revenue
done = orders[orders["status"] == "completed"].copy()
df = (
    done.merge(customers[["customer_id", "city"]], on="customer_id")
        .merge(products[["product_id", "category"]], on="product_id")
)

# ---------- (a) pivot table cross-check of SQL Q2 ----------
pivot = pd.pivot_table(
    df, values="order_amount", index="city", columns="category",
    aggfunc="sum", margins=True, margins_name="Total",
)
print("Revenue by city and category (INR):")
print(pivot.round(2).to_string())
grand_total = pivot.loc["Total", "Total"]
print("\nPivot grand total:", round(grand_total, 2), "| SQL total: 2998668.80")
assert abs(grand_total - 2998668.80) < 0.01

# per-city sum, mean and count with named aggregation
by_city = df.groupby("city").agg(
    total_amount=("order_amount", "sum"),
    mean_amount=("order_amount", "mean"),
    order_count=("order_amount", "count"),
).round(2)
print("\nPer city:")
print(by_city.to_string())
assert by_city.loc["Bengaluru", "total_amount"] == 523643.40
assert by_city.loc["Bengaluru", "mean_amount"] == 276.47
assert by_city.loc["Bengaluru", "order_count"] == 1894
assert by_city.loc["Mumbai", "total_amount"] == 479058.50
assert by_city.loc["Mumbai", "mean_amount"] == 297.00
assert by_city.loc["Mumbai", "order_count"] == 1613

# ---------- (b) distribution of completed order_amount ----------
amt = done["order_amount"]
mean, median, skew = amt.mean(), amt.median(), amt.skew()
q1, q3 = amt.quantile(0.25), amt.quantile(0.75)
iqr = q3 - q1
lower_fence, upper_fence = q1 - 1.5 * iqr, q3 + 1.5 * iqr
n_above = int((amt > upper_fence).sum())
n_below = int((amt < lower_fence).sum())

print("\nmean:", round(mean, 2), "| median:", round(median, 2), "| skewness:", round(skew, 2))
print("Q1:", round(q1, 2), "| Q3:", round(q3, 2), "| IQR:", round(iqr, 2))
print("lower fence:", round(lower_fence, 2), "| upper fence:", round(upper_fence, 2))
print("outliers above upper fence:", n_above, "| below lower fence:", n_below)

assert round(mean, 2) == 269.91
assert round(median, 2) == 135.00
assert abs(skew - 4.61) < 0.05
assert round(q1, 2) == 64.80 and round(q3, 2) == 297.00
assert round(upper_fence, 2) == 645.30
assert n_above == 897 and n_below == 0

# ---------- correlations ----------
cols = ["order_amount", "discount_pct", "quantity", "delivery_minutes"]
corr = done[cols].corr()
print("\nCorrelation matrix:")
print(corr.round(3).to_string())

pairs = corr.where(np.triu(np.ones(corr.shape, dtype=bool), k=1)).stack()
top_pair = pairs.abs().idxmax()
print("\nlargest |correlation|:", top_pair, round(pairs[top_pair], 3))
assert set(top_pair) == {"order_amount", "discount_pct"}
assert abs(pairs[top_pair] - (-0.095)) < 0.01

print("\nPANDAS CHECKS PASSED")