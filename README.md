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
| Mumbai | 479,058.50 | 297.00 | 1,613 |

Completed order_amount: mean 269.91, median 135.00, skew ~4.61, first quartile 64.80, third quartile 297.00, upper fence 645.30 → 897 outliers above, none below. The largest correlation in absolute value is order_amount vs discount_pct at −0.095; order_amount vs quantity is +0.087.

### What the data looks like

1,200 customers across 6 Indian cities, ordering grocery/dairy/snacks/personal care/electronics. Completed order amounts are heavily right-skewed — mean 269.91 vs median 135.00, skewness ~4.61. A few big orders drag the mean up.

The first and third quartiles are 64.80 and 297.00. Upper fence 645.30, 897 orders above it, nothing below the lower fence (−283.50). Raw data had all the usual problems — dupes, pending rows, impossible ages, negative delivery times, unparseable amounts — all handled during cleaning.

The largest correlation in absolute value is order_amount vs discount_pct at about −0.095. That's basically nothing. It's a weak negative linear relationship at best, and definitely not evidence that discounts cause order amounts to change.

## Part B

TBD

## Part C

TBD

## Part D

TBD

## Limitations and Next Steps

TBD