import pandas as pd

# ---------- Task 1: RFM table ----------
orders = pd.read_csv("data/clean/orders.csv", parse_dates=["order_ts"])
done = orders[orders["status"] == "completed"]

snapshot = pd.Timestamp("2025-10-01 00:00:00")

rfm = done.groupby("customer_id").agg(
    last_order=("order_ts", "max"),
    frequency=("order_id", "nunique"),
    monetary=("order_amount", "sum"),
).reset_index()

rfm["recency"] = (snapshot - rfm["last_order"]).dt.days
rfm = rfm[["customer_id", "recency", "frequency", "monetary"]]

print("customers in RFM table:", len(rfm))
print("recency   median:", rfm["recency"].median(),
      "| min:", rfm["recency"].min(), "| max:", rfm["recency"].max())
print("frequency mean:", round(rfm["frequency"].mean(), 2),
      "| max:", rfm["frequency"].max())
print("monetary  mean:", round(rfm["monetary"].mean(), 2),
      "| max:", round(rfm["monetary"].max(), 2))

assert len(rfm) == 1175
assert rfm["recency"].median() == 19
assert rfm["recency"].min() == 0 and rfm["recency"].max() == 180
assert round(rfm["frequency"].mean(), 2) == 9.46 and rfm["frequency"].max() == 33
assert abs(rfm["monetary"].mean() - 2552.06) < 0.01
assert abs(rfm["monetary"].max() - 14766.55) < 0.01
print("\nRFM CHECKS PASSED")
# ---------- Task 2: K-means for K = 2 to 8 ----------
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

features = ["recency", "frequency", "monetary"]
X = StandardScaler().fit_transform(rfm[features])

rows = []
for k in range(2, 9):
    km = KMeans(n_clusters=k, n_init=10, random_state=42).fit(X)
    rows.append({
        "K": k,
        "inertia": km.inertia_,
        "silhouette": silhouette_score(X, km.labels_),
    })
diag = pd.DataFrame(rows)
print("\nK-means diagnostics:")
print(diag.round(3).to_string(index=False))

reference = {
    2: (1820.8, 0.465), 3: (1268.2, 0.445), 4: (743.1, 0.526),
    5: (617.4, 0.481), 6: (503.2, 0.482), 7: (408.5, 0.416),
    8: (366.5, 0.412),
}
for _, r in diag.iterrows():
    ref_inertia, ref_sil = reference[int(r["K"])]
    assert abs(r["inertia"] - ref_inertia) / ref_inertia <= 0.05
    assert abs(r["silhouette"] - ref_sil) <= 0.05
print("\nK-MEANS DIAGNOSTICS MATCH THE BRIEF")
# ---------- Task 3: final K, segment profile, names, PCA ----------
import os
from sklearn.decomposition import PCA

# final choice of K (from 3, 4 or 5); explain your reasoning in the README
FINAL_K = 4
km = KMeans(n_clusters=FINAL_K, n_init=10, random_state=42)
rfm["segment_id"] = km.fit_predict(X)

profile = rfm.groupby("segment_id").agg(
    size=("customer_id", "size"),
    mean_recency=("recency", "mean"),
    mean_frequency=("frequency", "mean"),
    mean_monetary=("monetary", "mean"),
).round(2)
print("\nSegment profile:")
print(profile)

# name each segment from its own numbers (cluster ids are only labels)
premium_id = profile["mean_monetary"].idxmax()
rest = profile.drop(index=premium_id)
loyal_id = rest["mean_frequency"].idxmax()
rest = rest.drop(index=loyal_id)
at_risk_id = rest["mean_recency"].idxmax()
occasional_id = rest.drop(index=at_risk_id).index[0]
names = {
    premium_id: "Premium Big-Ticket",
    loyal_id: "Loyal Regulars",
    at_risk_id: "At-Risk Lapsing",
    occasional_id: "Occasional Low-Spend",
}
rfm["segment_name"] = rfm["segment_id"].map(names)
rfm["is_premium"] = rfm["segment_id"] == premium_id
print("\nNames:", {int(k): v for k, v in names.items()})

prem = profile.loc[premium_id]
assert abs(prem["size"] - 138) <= 10
assert abs(prem["mean_monetary"] - 7130) / 7130 <= 0.05
assert abs(prem["mean_frequency"] - 6.8) <= 0.5
loy = profile.loc[loyal_id]
assert abs(loy["size"] - 419) <= 10
assert abs(loy["mean_frequency"] - 19.4) <= 1.0
assert abs(loy["mean_recency"] - 8.8) <= 1.0

# PCA to 2 components on the scaled RFM matrix
ratio = PCA(n_components=2).fit(X).explained_variance_ratio_
print("\nPCA explained variance ratio:", ratio.round(3), "| total:", round(ratio.sum(), 3))
assert abs(ratio[0] - 0.634) <= 0.02 and abs(ratio[1] - 0.218) <= 0.02

os.makedirs("outputs", exist_ok=True)
out = rfm[["customer_id", "recency", "frequency", "monetary",
           "segment_id", "segment_name", "is_premium"]]
out.to_csv("outputs/customer_segments.csv", index=False)
print("Saved outputs/customer_segments.csv:", len(out), "rows,",
      int(out["is_premium"].sum()), "premium customers")
print("\nSEGMENT CHECKS PASSED")