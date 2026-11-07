# Instamart Customer Intelligence & Support Copilot

## Overview

Synthetic data only — nothing here is real. All money in INR.

Four parts:
- **Part A** — clean analytical DB (audit, cleaning, SQL, pandas)
- **Part B** — segments + lapse model
- **Part C** — support ticket triage
- **Part D** — policy assistant + refund agent

## Reproduce

From repo root. Commands are for Windows PowerShell; on Mac/Linux swap step 2 for `source venv/bin/activate`.

1. `python -m venv venv`
2. `venv\Scripts\Activate.ps1`
3. `python -m pip install -r requirements.txt`
4. `python generate_data.py`
5. `python part_a_audit.py`
6. `python part_a_clean.py`
7. `python validate.py`
8. `python run_queries.py`
9. `python part_a_explore.py`
10. `python part_b_segments.py`
11. `python part_b_lapse.py`

Parts B–D commands will get added as I build them.

## Part A

### Audit (`part_a_audit.py`)

Raw data was messy. Quick summary:

**Shape, data types and missing values (raw files)**

| Table | Shape | Columns and types | Missing values |
|---|---|---|---|
| customers | 1,200 x 5 | customer_id, city, signup_date, gender (text); age (float) | age 61 (5.08%), gender 30 (2.50%); all other columns 0 (0.00%) |
| products | 40 x 4 | product_id, product_name, category (text); price_inr (integer) | none (0.00% in every column) |
| orders | 13,084 x 9 | order_id, customer_id, product_id, order_ts, status, order_amount (text); quantity, discount_pct (integer); delivery_minutes (float) | order_amount 53 (0.41%), delivery_minutes 2,541 (19.42%); all other columns 0 (0.00%) |

The 53 missing order_amount values are the entries written as N/A, which pandas reads as blank. The other 67 of the 120 non-numeric amounts are the text "error". This is why order_amount is stored as text in the raw file.

| Check | Count |
|---|---|
| Raw order rows | 13,084 |
| Exact dupes | 119 |
| Pending rows | 656 |
| Distinct order_id | 12,309 |
| Non-numeric order_amount | 120 |
| Negative delivery_minutes | 106 |
| Blank delivery_minutes | 2,541 |
| Blank age | 61 |
| Age outside 10–100 | 6 |
| Raw city spellings | 24 |
| Raw gender spellings | 10 |
| Blank gender | 30 |

### Cleaning (`part_a_clean.py`)

**Customers:**
- City: strip + title case → 24 spellings collapse to 6 cities
- Gender: map everything to male/female/unknown → 10 spellings + 30 blanks become 3 values
- Age: set values outside 10–100 to missing (6 values), then fill missing with the median age of that customer's city (67 values total — 61 blanks + 6 impossible)
- signup_date → datetime (all 1,200 rows)

**Orders** (order matters here):
- order_ts → datetime
- Drop exact duplicate rows (119)
- Keep only the latest order_ts per order_id (drops 656 older pending records that had a later final record)
- order_amount → numeric; fill missing with price × quantity × (1 − discount/100), round to 2dp (112 values)
- Negative delivery_minutes → missing (105 values)
- Fill missing delivery_minutes on completed orders with the median of that product category (774 values)
- Cancelled orders stay missing (1,199 left null — a cancelled order was never delivered)

Note on the counts: the audit numbers (106 negative, 120 bad amounts) are higher than what got fixed because some of those bad values were sitting in duplicate/older pending rows that had already been dropped by earlier rules.

**After cleaning:** 12,309 orders (11,110 completed, 1,199 cancelled), no pending, no missing order_amount, completed revenue = INR 2,998,668.80. Cities: Pune 227, Delhi 210, Bengaluru 197, Chennai 191, Hyderabad 191, Mumbai 184. Genders: F 610, M 560, unknown 30. Ages all between 18 and 60.

### Storage + validation

Clean tables → `data/clean/customers.csv`, `products.csv`, `orders.csv` and `data/instamart.db` (SQLite, tables customers/products/orders, order_ts stored as text). `validate.py` checks all the numbers above plus the DB contents and prints `ALL CHECKPOINTS PASSED`.

### SQL (`sql/queries.sql`, run via `run_queries.py`)

| Query | Result |
|---|---|
| Q1 (WHERE + HAVING) | 30 customers |
| Q2 (3-table join) | 30 rows, total INR 2,998,668.80, biggest cell Bengaluru/Electronics at INR 233,909.45 |
| Q3 (scalar subquery) | 11 products above avg price |
| Q4 (LEFT JOIN) | 25 customers with no completed order |
| Q5 (CTEs) | 550 customers above avg spend (INR 2,552.06) |
| Q6 (window fns) | top per city: Bengaluru C0082 (12,856.20), Chennai C0930 (10,151.40), Delhi C0291 (13,742.60), Hyderabad C0743 (12,730.05), Mumbai C0693 (14,766.55), Pune C0426 (10,377.10); 8 rows where RANK ≠ ROW_NUMBER |
| Q7 (running total) | 183 daily rows, cumulative ends at INR 2,998,668.80 |

RANK and ROW_NUMBER disagree on 8 rows because tied spend gets the same RANK but ROW_NUMBER still increments.

### pandas cross-check (`part_a_explore.py`)

Pivot with margins gives grand total INR 2,998,668.80 — matches SQL.

| City | Sum (INR) | Mean (INR) | Count |
|---|---|---|---|
| Bengaluru | 523,643.40 | 276.47 | 1,894 |
| Chennai | 463,629.15 | 272.72 | 1,700 |
| Delhi | 502,829.80 | 243.62 | 2,064 |
| Hyderabad | 528,589.90 | 284.95 | 1,855 |
| Mumbai | 479,058.50 | 297.00 | 1,613 |
| Pune | 500,918.05 | 252.48 | 1,984 |

Completed order_amount: mean 269.91, median 135.00, skew ~4.61, first quartile 64.80, third quartile 297.00, upper fence 645.30 → 897 outliers above, none below. The largest correlation in absolute value is order_amount vs discount_pct at −0.095; order_amount vs quantity is +0.087.
Correlation matrix (completed orders):

| | order_amount | discount_pct | quantity | delivery_minutes |
|---|---|---|---|---|
| order_amount | 1.000 | -0.095 | 0.087 | -0.003 |
| discount_pct | -0.095 | 1.000 | -0.000 | -0.010 |
| quantity | 0.087 | -0.000 | 1.000 | -0.013 |
| delivery_minutes | -0.003 | -0.010 | -0.013 | 1.000 |

### What the data looks like

1,200 customers across 6 Indian cities, ordering grocery/dairy/snacks/personal care/electronics. Completed order amounts are heavily right-skewed — mean 269.91 vs median 135.00, skewness ~4.61. A few big orders drag the mean up.

The first and third quartiles are 64.80 and 297.00. Upper fence 645.30, 897 orders above it, nothing below the lower fence (−283.50). Raw data had all the usual problems — dupes, pending rows, impossible ages, negative delivery times, unparseable amounts — all handled during cleaning.

The largest correlation in absolute value is order_amount vs discount_pct at about −0.095. That's basically nothing. It's a weak negative linear relationship at best, and definitely not evidence that discounts cause order amounts to change.

## Part B

### RFM table (`part_b_segments.py`)

Built from completed orders only, as of the snapshot 2025-10-01 00:00:00. Recency is whole days since the last completed order, frequency is the number of distinct completed orders, and monetary is the total of order_amount in INR.

| Measure | Result |
|---|---|
| Customers with at least one completed order | 1,175 |
| Recency | median 19, minimum 0, maximum 180 |
| Frequency | mean 9.46, maximum 33 |
| Monetary (INR) | mean 2,552.06, maximum 14,766.55 |

### K-means (RFM scaled with StandardScaler, n_init=10, random_state=42)

| K | Inertia | Silhouette |
|---|---|---|
| 2 | 1820.761 | 0.465 |
| 3 | 1268.235 | 0.445 |
| 4 | 743.071 | 0.526 |
| 5 | 617.367 | 0.480 |
| 6 | 503.171 | 0.482 |
| 7 | 408.460 | 0.416 |
| 8 | 366.503 | 0.412 |

**Final K = 4.**

I chose K=4 because it gives the best balance between how tight the clusters are and how well they are separated. If we look at the inertia, it drops a lot from K=3 (1,268) to K=4 (743), but the drop slows down at K=5 (617). This "elbow" tells us that adding a 5th cluster doesn't help much. Also, K=4 has the highest silhouette score (0.526) out of all the options. Finally, from a business side, four distinct groups are easy to understand and target with specific marketing.

Inertia will always go down as we add more clusters, because the data points are just getting grouped into smaller, tighter spaces. So, K=8 will naturally have a lower inertia than K=2. That's why we can't rely on inertia alone; we have to look at the silhouette score and make sure the segments actually make sense practically.

### Segment profile

| Segment id | Name | Customers | Mean recency (days) | Mean frequency | Mean monetary (INR) |
|---|---|---|---|---|---|
| 0 | Occasional Low-Spend | 436 | 28.86 | 3.77 | 1,057.62 |
| 1 | Premium Big-Ticket | 138 | 24.12 | 6.77 | 7,129.70 |
| 2 | Loyal Regulars | 419 | 8.77 | 19.40 | 3,410.02 |
| 3 | At-Risk Lapsing | 182 | 109.04 | 2.20 | 685.99 |

The segment ids are only labels produced by K-means and have no ordering. Premium is the segment with the highest mean monetary value.

- **Occasional Low-Spend:** Try to increase their buying frequency by offering affordable bundles, personalized product suggestions, and small discounts.
- **Premium Big-Ticket:** Focus on keeping these high-value customers happy with exclusive VIP offers, premium product recommendations, and a personalized experience.
- **Loyal Regulars:** Reward their loyalty with a points system, special repeat-purchase benefits, and early access to new sales.
- **At-Risk Lapsing:** Try to win them back before they leave completely by sending personalized "we miss you" emails and comeback discount codes.

The names follow each segment's profile: Premium Big-Ticket has by far the highest mean spend (INR 7,129.70); Loyal Regulars order the most often (19.40 orders) and most recently (8.77 days); At-Risk Lapsing has gone longest since its last order (109.04 days); Occasional Low-Spend orders rarely (3.77 orders) and spends little (INR 1,057.62).

### PCA

PCA with 2 components on the scaled RFM matrix explains 0.634 and 0.218 of the variance (total 0.852). In plain words, the first two components keep about 85% of the information in the three RFM columns, so a two-dimensional view summarises the customers well. `outputs/customer_segments.csv` holds customer_id, recency, frequency, monetary, segment_id, segment_name and is_premium for all 1,175 customers (138 are Premium).

### Lapse problem (`part_b_lapse.py`)

Cutoff 2025-09-01. The cohort is every customer with at least one completed order before the cutoff. The label `lapsed` is 1 if the customer has no completed order dated 2025-09-01 through 2025-09-30, otherwise 0.

| Measure | Result |
|---|---|
| Customers in the cohort | 1,156 |
| Lapsed | 443 (38.32%) |
| Training / test rows (`train_test_split`, test_size=0.2, stratify, random_state=42) | 924 / 232 |
| Baseline "always not lapsed", test accuracy | 61.6% |
| Baseline lapsed-class F1 | 0 |

Features: recency (days from the cutoff to the last completed order), frequency, monetary, average discount_pct of completed orders, cancellation rate (cancelled orders divided by all orders with a final status, before the cutoff), average delivery_minutes of completed orders, favourite product category, city, age, gender and tenure in days (cutoff minus signup_date).

No order dated on or after 2025-09-01 entered the features, and the segment labels from Part B task 3 were not used as features, because both would leak the answer. No encoder, scaler or resampler saw test rows.

### Preprocessing

Nominal columns (city, gender, favourite category) are one-hot encoded with k-1 columns each (`OneHotEncoder(drop="first")`) and numeric columns are standardised with `StandardScaler`, all inside a scikit-learn Pipeline that is fitted on the training rows only. No feature column contains a missing value in the training or test rows.

| | Mean of frequency |
|---|---|
| Learned by the scaler (training rows only) | 8.1147 |
| Full cohort | 8.0285 |

The two means differ slightly because the scaler only learns from the 80% training split, while the full cohort includes all training and test customers.

### Tuning and test results

| Model | Grid | Best parameters | Best CV F1 |
|---|---|---|---|
| Logistic regression | C in 0.01, 0.1, 1, 10, 100 | C = 100 | 0.651 |
| Random forest (100 trees, random_state=42) | max_depth 3, 5, 8; min_samples_leaf 5, 10, 20 | depth 8, leaf 10 | 0.687 |

Both searches use cv=5 and scoring="f1". Test set, lapsed class:

| Model | Confusion matrix [[TN, FP], [FN, TP]] | Precision | Recall | F1 |
|---|---|---|---|---|
| Logistic regression | [[111, 32], [31, 58]] | 0.644 | 0.652 | 0.648 |
| Random forest | [[111, 32], [32, 57]] | 0.640 | 0.640 | 0.640 |

**Selected model: random forest.** I selected it because its cross-validated F1 (0.687) was higher than that of logistic regression (0.651). The two models are almost identical on the test set and catch about the same share of lapsing customers, so the cost argument does not separate them and cross-validation, a rule fixed before the test set was used, decides. From a business side, missing a customer who is about to lapse means losing their future revenue completely, while wrongly targeting a loyal customer only costs a small discount they did not need. Both models are well above the required test F1 of 0.55 (the forest scores 0.640). Because missing a lapsing customer is the more expensive mistake, recall matters more than precision for the retention team.

### Class-balance experiment

The lapsed rows of the training set were over-sampled with replacement (random_state=42), keeping every original row, until both classes had 570 rows (the original training counts were 570 not lapsed and 354 lapsed). The best logistic regression was refitted on that balanced data and scored on the original, unchanged test set.

| Training data | Precision | Recall | F1 |
|---|---|---|---|
| Original | 0.644 | 0.652 | 0.648 |
| Balanced | 0.589 | 0.854 | 0.697 |

Recall moved the most, jumping from 0.652 to 0.854, while precision fell from 0.644 to 0.589. This means the retention team will catch many more customers who are about to lapse, but the trade-off is that they will also contact more customers who would have stayed anyway.

### Feature importance and coefficients

Top five features of the random forest (importance shows how much a feature helps the model, not in which direction):

| Feature | Importance |
|---|---|
| monetary | 0.278 |
| frequency | 0.277 |
| recency | 0.111 |
| avg_delivery | 0.062 |
| avg_discount | 0.053 |

Logistic regression coefficients on standardised features (positive means higher odds of lapsing, other features held constant):

| Feature | Coefficient |
|---|---|
| recency | 0.040 |
| frequency | -1.698 |
| cancellation rate | -0.124 |

- **Monetary:** how much a customer spends is a strong indicator of whether they will stick around.
- **Frequency:** how often they order is heavily tied to their likelihood of lapsing.
- **Recency:** the time since their last order helps spot customers who are drifting away.
- **Average delivery:** their delivery experience adds useful context to the prediction.
- **Average discount:** how they use discounts also helps the model make its guesses.
- **Recency coefficient (0.040):** as the days since the last order increase, the odds of lapsing go up slightly.
- **Frequency coefficient (-1.698):** customers who order very often are much less likely to lapse.
- **Cancellation rate coefficient (-0.124):** holding other features constant, a higher cancellation rate is linked to slightly lower lapse odds in this model, but the coefficient is small, so it should not be over-read.

### Saved model and retention list

The selected model (the full pipeline) is saved with `joblib.dump` to `outputs/lapse_model.joblib`. Reloading it with `joblib.load` reproduces the original test predictions exactly.

`outputs/retention_list.csv` lists the Premium customers in the test set (40 customers) ranked by predicted lapse probability, top 10, with customer_id, lapse_probability and actually_lapsed. Of these 10, 1 truly lapsed.

The Premium flag comes from the whole-window RFM, which includes the September window that defines the lapse label, so this retention list is illustrative and not a strictly leakage-free evaluation, even though the model's own input features use only orders before the cutoff.

## Part C

TBD

## Part D

TBD

## Limitations and Next Steps

TBD