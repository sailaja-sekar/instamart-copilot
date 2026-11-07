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
# ---------- Task 5: preprocessing without leakage ----------
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

numeric = ["recency", "frequency", "monetary", "avg_discount", "cancellation_rate",
           "avg_delivery", "age", "tenure_days"]
nominal = ["favourite_category", "city", "gender"]

def make_prep():
    return ColumnTransformer([
        ("num", StandardScaler(), numeric),
        ("cat", OneHotEncoder(drop="first", handle_unknown="ignore"), nominal),
    ])

demo = make_prep().fit(X_train)
learned_mean = demo.named_transformers_["num"].mean_[numeric.index("frequency")]
print("\nscaler mean of frequency (train rows only):", round(learned_mean, 4))
print("full-cohort mean of frequency:             ", round(feat["frequency"].mean(), 4))
print("train columns with missing values:", int(X_train.isna().sum().sum()),
      "| test:", int(X_test.isna().sum().sum()))
assert X_train.isna().sum().sum() == 0 and X_test.isna().sum().sum() == 0

# ---------- Task 6: tune and evaluate ----------
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import GridSearchCV
from sklearn.metrics import confusion_matrix, precision_score, recall_score

lr_search = GridSearchCV(
    Pipeline([("prep", make_prep()), ("model", LogisticRegression(max_iter=1000))]),
    {"model__C": [0.01, 0.1, 1, 10, 100]}, cv=5, scoring="f1")
lr_search.fit(X_train, y_train)

rf_search = GridSearchCV(
    Pipeline([("prep", make_prep()),
              ("model", RandomForestClassifier(n_estimators=100, random_state=42))]),
    {"model__max_depth": [3, 5, 8], "model__min_samples_leaf": [5, 10, 20]},
    cv=5, scoring="f1")
rf_search.fit(X_train, y_train)

print("\nLogistic regression best:", lr_search.best_params_,
      "| CV F1:", round(lr_search.best_score_, 3))
print("Random forest best:      ", rf_search.best_params_,
      "| CV F1:", round(rf_search.best_score_, 3))

for name, search in [("Logistic regression", lr_search), ("Random forest", rf_search)]:
    pred = search.predict(X_test)
    test_f1 = f1_score(y_test, pred, zero_division=0)
    print("\n" + name, "on the test set")
    print("confusion matrix [[TN, FP], [FN, TP]]:", confusion_matrix(y_test, pred).tolist())
    print("precision:", round(precision_score(y_test, pred, zero_division=0), 3),
          "| recall:", round(recall_score(y_test, pred, zero_division=0), 3),
          "| F1:", round(test_f1, 3))
    assert test_f1 >= 0.55

print("\nTUNING CHECKS PASSED")
# ---------- Task 7: class-balance experiment (over-sample the training set only) ----------
import os
import joblib
from sklearn.base import clone

best_lr = lr_search.best_estimator_
print("\noriginal training counts:", y_train.value_counts().to_dict())
lapsed_idx = y_train[y_train == 1].index
n_add = int((y_train == 0).sum() - len(lapsed_idx))
extra_idx = pd.Series(lapsed_idx).sample(n=n_add, replace=True, random_state=42)
X_bal = pd.concat([X_train, X_train.loc[extra_idx]])
y_bal = pd.concat([y_train, y_train.loc[extra_idx]])
print("balanced training counts:", y_bal.value_counts().to_dict())

lr_bal = clone(best_lr).fit(X_bal, y_bal)
print("Logistic regression, original vs balanced training (same original test set):")
for label, model in [("original ", best_lr), ("balanced ", lr_bal)]:
    pred = model.predict(X_test)
    print(label, "precision:", round(precision_score(y_test, pred, zero_division=0), 3),
          "| recall:", round(recall_score(y_test, pred, zero_division=0), 3),
          "| F1:", round(f1_score(y_test, pred, zero_division=0), 3))

# ---------- Task 8: interpret, persist, use ----------
rf_pipe = rf_search.best_estimator_
names_out = rf_pipe.named_steps["prep"].get_feature_names_out()
imp = pd.Series(rf_pipe.named_steps["model"].feature_importances_, index=names_out)
print("\nTop 5 random forest features:")
print(imp.sort_values(ascending=False).head(5).round(3).to_string())

coef = pd.Series(best_lr.named_steps["model"].coef_[0],
                 index=best_lr.named_steps["prep"].get_feature_names_out())
print("\nLogistic regression coefficients (positive = higher odds of lapse, other features held constant):")
for f in ["num__recency", "num__frequency", "num__cancellation_rate"]:
    print(f, round(coef[f], 3))

# model selection rule, fixed before looking at the test set: higher cross-validated F1 wins
SELECTED = rf_search if rf_search.best_score_ > lr_search.best_score_ else lr_search
selected_name = "Random forest" if SELECTED is rf_search else "Logistic regression"
print("\nselected model:", selected_name,
      "| CV F1:", round(SELECTED.best_score_, 3),
      "(logistic regression:", round(lr_search.best_score_, 3),
      "| random forest:", round(rf_search.best_score_, 3), ")")
selected_model = SELECTED.best_estimator_

os.makedirs("outputs", exist_ok=True)
joblib.dump(selected_model, "outputs/lapse_model.joblib")
reloaded = joblib.load("outputs/lapse_model.joblib")
assert (reloaded.predict(X_test) == selected_model.predict(X_test)).all()
print("reloaded model reproduces the test predictions exactly")
sel_f1 = f1_score(y_test, selected_model.predict(X_test), zero_division=0)
assert sel_f1 >= 0.55
print("selected model test F1:", round(sel_f1, 3))

segments = pd.read_csv("outputs/customer_segments.csv")
premium_ids = set(segments.loc[segments["is_premium"], "customer_id"])
test_view = pd.DataFrame({
    "customer_id": feat.loc[X_test.index, "customer_id"].values,
    "lapse_probability": selected_model.predict_proba(X_test)[:, 1],
    "actually_lapsed": y_test.values,
})
prem_test = test_view[test_view["customer_id"].isin(premium_ids)]
retention = prem_test.sort_values("lapse_probability", ascending=False).head(10)
assert retention["customer_id"].is_unique
assert retention["lapse_probability"].between(0, 1).all()
retention.round({"lapse_probability": 4}).to_csv("outputs/retention_list.csv", index=False)
print("\npremium customers in the test set:", len(prem_test))
print("retention list rows:", len(retention), "| truly lapsed:", int(retention["actually_lapsed"].sum()))
print("\nBLOCK DONE")