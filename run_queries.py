import sqlite3
import pandas as pd

# read the SQL file and split it into the seven queries
sql_text = open("sql/queries.sql", encoding="utf-8").read()
queries = [q.strip() for q in sql_text.split(";") if q.strip()]
assert len(queries) == 7, "expected 7 queries"

con = sqlite3.connect("data/instamart.db")
try:
    q = [pd.read_sql_query(text, con) for text in queries]
finally:
    con.close()

def close(a, b, tol=0.01):
    return abs(a - b) < tol

# Q1
print("Q1 customers:", len(q[0]))
assert len(q[0]) == 30

# Q2
print("Q2 rows:", len(q[1]), "| total:", round(q[1]["revenue"].sum(), 2))
top = q[1].iloc[0]
print("   largest cell:", top["city"], "/", top["category"], top["revenue"])
assert len(q[1]) == 30
assert close(q[1]["revenue"].sum(), 2998668.80)
assert top["city"] == "Bengaluru" and top["category"] == "Electronics"
assert close(top["revenue"], 233909.45)

# Q3
print("Q3 products:", len(q[2]))
assert len(q[2]) == 11

# Q4
print("Q4 customers with no completed order:", len(q[3]))
assert len(q[3]) == 25

# Q5
print("Q5 customers above average:", len(q[4]), "| average:", q[4]["avg_total"].iloc[0])
assert len(q[4]) == 550
assert close(q[4]["avg_total"].iloc[0], 2552.06)

# Q6
top_per_city = q[5][q[5]["row_num"] == 1].set_index("city")
print("Q6 top customer per city:")
print(top_per_city[["customer_id", "total_spend"]])
expected = {
    "Bengaluru": ("C0082", 12856.20), "Chennai": ("C0930", 10151.40),
    "Delhi": ("C0291", 13742.60), "Hyderabad": ("C0743", 12730.05),
    "Mumbai": ("C0693", 14766.55), "Pune": ("C0426", 10377.10),
}
for city, (cid, amt) in expected.items():
    assert top_per_city.loc[city, "customer_id"] == cid
    assert close(top_per_city.loc[city, "total_spend"], amt)
differ = int((q[5]["rnk"] != q[5]["row_num"]).sum())
print("   rows where RANK differs from ROW_NUMBER:", differ)
assert differ == 8

# Q7
print("Q7 daily rows:", len(q[6]), "| last cumulative:", q[6]["cumulative_revenue"].iloc[-1])
assert len(q[6]) == 183
assert close(q[6]["cumulative_revenue"].iloc[-1], 2998668.80)

print("\nALL 7 QUERIES MATCH THE BRIEF")