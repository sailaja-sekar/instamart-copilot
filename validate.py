import sqlite3
import pandas as pd

customers = pd.read_csv("data/clean/customers.csv")
orders = pd.read_csv("data/clean/orders.csv")

# customers
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

# orders
completed = orders["status"] == "completed"
assert len(orders) == 12309
assert orders["order_id"].is_unique
assert completed.sum() == 11110
assert (orders["status"] == "cancelled").sum() == 1199
assert (orders["status"] == "pending").sum() == 0
assert orders["order_amount"].isna().sum() == 0
assert orders.loc[completed, "delivery_minutes"].isna().sum() == 0
assert orders.loc[~completed, "delivery_minutes"].isna().sum() == 1199
assert abs(orders.loc[completed, "order_amount"].sum() - 2998668.80) < 0.01

# database
con = sqlite3.connect("data/instamart.db")
try:
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"customers", "products", "orders"} <= tables
    assert con.execute("SELECT COUNT(*) FROM customers").fetchone()[0] == 1200
    assert con.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 40
    assert con.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 12309
    assert con.execute("SELECT COUNT(DISTINCT order_id) FROM orders").fetchone()[0] == 12309
    db_revenue = con.execute(
        "SELECT SUM(order_amount) FROM orders WHERE status = 'completed'"
    ).fetchone()[0]
    assert abs(db_revenue - 2998668.80) < 0.01
finally:
    con.close()

print("ALL CHECKPOINTS PASSED")