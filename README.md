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
12. `python part_c_triage.py`
13. `python policy_rag.py`
14. `python refund_agent.py`

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

### Input guardrails and redaction (`part_c_triage.py`)

Tickets are processed in the order they appear in `data/raw/tickets.csv`, read with `keep_default_na=False`. A ticket whose text is empty or only whitespace gets status `skipped_empty`, and a ticket whose `est_tokens(text)` is above MAX_INPUT_TOKENS = 400 gets status `flagged_long`. Neither is ever sent to the model. There are 4 empty tickets and 4 long ones (each long ticket estimates to 734 tokens).

Before a ticket goes into a prompt, three regular expressions are applied in this order: email to `[EMAIL]`, phone (`\b[6-9]\d{9}\b`) to `[PHONE]`, order id (`ORD-\d{6}`) to `[ORDER_ID]`. The user message sent to the model is exactly the redacted text and nothing else, and the code asserts that no email, phone or order id appears in any message.

| Type | Substitutions across all 164 tickets |
|---|---|
| Email | 55 |
| Phone | 91 |
| Order id | 132 |
| Total | 278 |

Re-applying the three patterns to the redacted texts finds 0 matches.

### Prompts, retries and validation

Two system prompts were written. Both contain the word CLASSIFY, list the four categories (billing, delivery, technical, fraud) and require a JSON-only reply of the form `{"category": "...", "reason": "..."}`. The zero-shot prompt (46 estimated tokens) has no examples; the few-shot prompt (149 estimated tokens) adds an `EXAMPLES:` line with four labelled examples, one of them fraud.

Every model call goes through a retry function with at most 3 retries per ticket. The wait before retry number n is BASE_DELAY x 2**n x random.uniform(0.9, 1.15) with BASE_DELAY = 0.05 seconds, and one line is logged per retry. `mock_llm.reset()` is called immediately before each full run. With this mock every retry is retry number 0, so each wait lies between 0.045 and 0.0575 seconds. A full run had 19 TransientLLMErrors, all recovered by a retry, and no ticket ended with a permanent error.

Sample of the retry log:

```
retry log: ticket T0002 | retry number 0 | wait 0.0490s
retry log: ticket T0116 | retry number 0 | wait 0.0469s
retry log: ticket T0153 | retry number 0 | wait 0.0531s
```

All three waits lie within the allowed range of 0.045 to 0.0575 seconds.

Every answer is validated. A reply that is valid JSON with a category in the allowed list is `classified_json`. A reply that is not valid JSON is searched with `re.findall(r"[a-z]+", text.lower())` and accepted as `classified_keyword` if exactly one allowed category word is present. Anything else, including valid JSON with a category outside the list, is `flagged_invalid_output` and goes to human review; nothing is guessed.

| Status (one full run over 156 eligible tickets) | Count |
|---|---|
| classified_json | 135 |
| classified_keyword | 12 |
| flagged_invalid_output | 9 |

### Zero-shot against few-shot

| Run | Tickets classified | Accuracy over classified | Total tokens | Tokens per classified ticket |
|---|---|---|---|---|
| Zero-shot | 147 | 85.7% (126 of 147) | 11,584 | 78.8 |
| Few-shot | 147 | 100.0% (147 of 147) | 27,652 | 188.1 |

Confusion table for the zero-shot run (rows are the true category, columns the predicted one):

| True \ predicted | billing | delivery | fraud | technical |
|---|---|---|---|---|
| billing | 38 | 0 | 0 | 0 |
| delivery | 0 | 36 | 0 | 0 |
| fraud | 11 | 0 | 23 | 0 |
| technical | 10 | 0 | 0 | 29 |

Every zero-shot error is a fraud ticket predicted billing (11) or a technical ticket predicted billing (10).

Few-shot prompting is worth the extra token cost when accurate ticket routing is important. It uses 188.1 tokens per classified ticket compared with 78.8 for zero-shot, which is about 2.4 times more, but it improved accuracy from 85.7% to 100% and removed all 21 classification errors. This matters especially for fraud tickets, because sending a fraud complaint to billing instead of the security team could delay the response and put the customer at risk. Since fraud cases are expected to be handled within 2 hours, the additional token cost is reasonable when it helps avoid such mistakes. For low-stakes tickets, where a wrong label is cheap to fix, the cheaper zero-shot prompt may be enough.

### Token budget, routing and outputs

A TOKEN_BUDGET check runs before each model call: if the running total of `usage.total_tokens` is already at or above the budget, no call is made and the ticket gets `budget_exhausted` and goes to human review. The check happens before each call, as the brief specifies, so the last call that starts under the budget can push the total slightly past it (6,029 tokens used against a budget of 6,000). The demo run used the zero-shot prompt with TOKEN_BUDGET = 6000; 75 tickets ended `budget_exhausted`, and this count depends on the length of the prompt. The result is saved in `outputs/triage_budget_demo.csv`.

The final `outputs/triage_results.csv` (164 rows) comes from a few-shot run with TOKEN_BUDGET = 100000, and no ticket was budget_exhausted. Routing reads `outputs/customer_segments.csv` from Part B:

| Rule (first match) | Route | Priority |
|---|---|---|
| Status skipped_empty, flagged_long, flagged_invalid_output or budget_exhausted | human_review | NORMAL |
| Category is fraud | security_team | HIGH |
| Customer is Premium | premium_desk | HIGH |
| Anything else | support_queue | NORMAL |

A customer with no row in the segment file counts as not Premium.

| Route | Tickets |
|---|---|
| support_queue | 102 |
| security_team | 34 |
| human_review | 17 |
| premium_desk | 11 |

Rule-validated by code: 147 tickets (135 JSON plus 12 keyword). Sent to humans: 17 tickets (4 empty, 4 too long, 9 invalid output).

## Part D

### Chunking and retrieval (`policy_rag.py`)

The five policy documents are split into chunks of 40 words with an overlap of 10 words (the next chunk starts 30 words later), stopping after the first chunk whose end reaches or passes the last word. The source file name is recorded with every chunk.

| Document | Chunks |
|---|---|
| refund_policy.txt | 4 |
| delivery_policy.txt | 3 |
| escalation_policy.txt | 3 |
| payment_policy.txt | 3 |
| privacy_policy.txt | 2 |
| Total | 15 |

`TfidfVectorizer()` is fitted on the chunk texts, a query is transformed with the same fitted vectorizer, and chunks are ranked by `cosine_similarity`. `retrieve(query, k=3)` returns dictionaries with source, score and text. For the query "refund policy late delivery" the top three chunks all come from `refund_policy.txt` (scores 0.2719, 0.2514 and 0.2454).

TF (Term Frequency) measures how often a word shows up in a specific chunk. IDF (Inverse Document Frequency) looks at how rare that word is across all the chunks, giving more weight to unique words and less weight to common ones. The main limitation here is that TF-IDF only matches exact words, not the actual meaning. So, if a customer types "money back" but the document says "refund", TF-IDF might miss the connection because the words are different, even though they mean the same thing.

### Augmented answers and evaluation

`answer(question)` retrieves three chunks and sends two messages to `mock_llm.chat`: a system message containing POLICY ASSISTANT that tells the model to answer only from the supplied context (or say it could not find the information), and a user message of the form `CONTEXT:`, the three chunks each prefixed with `[source file name]` on its own line, then `QUESTION:` and the question. It returns the model's text and the sources used.

`data/raw/policy_eval.csv` has 14 questions: 12 answerable and 2 not covered by any document.

| Chunking | Chunks | Expected document in top 3 (of 12) | Expected fact in answer (of 12) | Fallback answer on the 2 unanswerable |
|---|---|---|---|---|
| 40 words, overlap 10 | 15 | 12 | 12 | 2 |
| 40 words, overlap 0 | 13 | 12 | 10 | 2 |

With no overlap two questions break: "What delivery time makes a completed order eligible for a full refund?" and "How soon is money returned when a payment fails but is deducted?". In both cases the right document is still retrieved, but the answer is missing.

Without overlap, a single sentence containing the full answer can get cut in half between two chunks, so when the system retrieves one of those chunks it only gets part of the answer. For instance, the 45-minute delivery threshold for a full refund or the 48-hour return period for a failed payment ends up split at the boundary. A 10-word overlap repeats the end of one chunk at the start of the next, which keeps these facts together so they are not lost.

### Tools and the ReAct loop (`refund_agent.py`)

Refund rules implemented by the tools: only completed orders can be refunded; a completed order delivered in more than 45 minutes is refunded 100% of its order_amount; delivered in 45 minutes or less the refund is 0; a refund above INR 1000 is escalated to a human and not issued automatically.

| Tool | What it does |
|---|---|
| get_order(order_id) | Reads `data/instamart.db` and returns order_id, status, order_amount and delivery_minutes, or an "order not found" error |
| search_policy(query) | Returns the retrieval results (the same `retrieve` as above) under the key results |
| calculate_refund(order_amount, delivery_minutes) | Returns the refund in INR following the rules above |
| issue_refund(order_id, refund_inr) | Appends a line to `outputs/refund_ledger.jsonl` and returns the amount (refuses amounts above INR 1000) |
| escalate_to_human(order_id, refund_inr) | Appends a line to `outputs/refund_ledger.jsonl` and returns the amount |

Each tool has a name, a one-sentence description and a parameter specification in `TOOLS_SPEC`, and `TOOL_MAP` maps each name to its function. `run_agent(user_message, scenario_id, max_iterations=6, token_limit=6000, time_limit_seconds=10)` starts with a system message containing AGENT and the user message. In each iteration it calls the model; a reply without tool calls is the final answer, otherwise it appends the assistant tool call, runs the tool through `TOOL_MAP` and appends the tool observation as JSON. Results for the seven scenarios in `data/raw/agent_scenarios.csv`:

| Scenario | Status | Refund (INR) | Model calls | Tokens used |
|---|---|---|---|---|
| S1 | REFUND | 128.25 | 5 | 1,102 |
| S2 | REFUND | 135.00 | 5 | 1,102 |
| S3 | ESCALATE | 1,999.00 | 5 | 1,089 |
| S4 | DENIED | 0.00 | 4 | 769 |
| S5 | DENIED | 0.00 | 3 | 460 |
| S6 | NOT_FOUND | 0.00 | 2 | 154 |
| S7 | FALLBACK_MAX_ITERATIONS | 0.00 | 6 | 3,246 |

S7 is the looping scenario: the model keeps asking for the policy search, so the run stops after the sixth model call and hands the case to a human. The one line per run is saved in `outputs/agent_runs.jsonl` (scenario_id, status, final_answer, llm_calls, tokens_used and every step's tool, arguments and observation).

### Stopping safely

The loop stops with a human hand-over message, and returns the steps completed so far, when any of three limits is reached: more than max_iterations model calls (status FALLBACK_MAX_ITERATIONS), total tokens above token_limit, checked right after each model call and before the requested tool is run (FALLBACK_TOKEN_LIMIT), or elapsed wall-clock time of time_limit_seconds or more, checked at the top of each iteration (FALLBACK_TIMEOUT).

| Demonstration | Status |
|---|---|
| S1 with token_limit=200 | FALLBACK_TOKEN_LIMIT (stopped after 3 model calls and 2 tools) |
| S1 with time_limit_seconds=0 | FALLBACK_TIMEOUT (stopped before the first model call) |

### Resumable runs

After every tool observation a checkpoint is written to `state/<run id>.json` with the run id, scenario id, the full message list, tokens used, the step number and the list of tools already executed. `resume_agent(run_id)` loads the checkpoint and continues. For the demonstration S1 was run with a simulated crash right after the second tool and its checkpoint, then resumed. The tools executed across the crash and the resume, in order:

1. get_order
2. search_policy
3. calculate_refund
4. issue_refund

That is four executions with none repeated, and the final result is REFUND of INR 128.25.

The tools write to the ledger before the checkpoint is saved, so a crash between the two could repeat an action on resume. To prevent a duplicate ledger line, the ledger write skips an action whose run id, tool and order already appear in the ledger. This check is per run, so two different runs on the same order would each record a refund; a production system would check the order itself.

Output files: `outputs/agent_runs.jsonl` (7 scenario runs), `outputs/agent_demos.jsonl` (the token-limit, timeout and crash-and-resume runs), `outputs/refund_ledger.jsonl` (4 lines: S1, S2, S3 and the S1 crash-and-resume demo) and `state/` (9 checkpoints).

### ReAct against plan-and-execute

ReAct works step-by-step. It calls the model, looks at the result from the tool, and then decides what to do next. In our test, S1 took 5 model calls and 1,102 tokens, S5 took 3 calls and 460 tokens, and S6 took 2 calls and 154 tokens. A plan-and-execute design could save calls and tokens for normal requests, because it asks the model to map out the entire plan just once and then follows it, whereas ReAct sends the growing message history again on every call.

However, if something unexpected happens, such as a NOT_FOUND error or a cancelled order, the original plan might not work anymore. ReAct handled both cases cheaply: it saw the observation and stopped after 2 calls (S6) and 3 calls (S5) without running the remaining steps. A plan-and-execute design would have to run steps that are no longer needed or pause and call the model again to make a new plan. For this refund workflow, I would choose ReAct. Refund decisions require checking order status, delivery times and policies before doing anything that involves money. It may use a few more model calls, but deciding step by step gives better control and helps prevent giving someone the wrong refund.

## Limitations and Next Steps

**Limitations**

- **Synthetic data and a mock model.** All data is generated by a script, and every language-model call goes through the supplied offline `mock_llm.py`, which classifies by keyword rules. The accuracy figures (85.7% zero-shot, 100% few-shot) describe this mock, not a real model, and would not carry over to real customer tickets.
- **The Premium flag is a post-hoc label.** The Premium segment comes from the whole-window RFM table, which includes the September window that defines the lapse label, so the retention list is illustrative and not a leakage-free evaluation. The model's own features use only orders before 2025-09-01.
- **Small test set.** The lapse model is evaluated on 232 customers, so one or two customers move the F1 score noticeably; the random forest and logistic regression are essentially tied on the test set.
- **Imputed delivery times feed the refund rule.** In Part A, 774 completed orders with a missing delivery time were filled with the median of their product category, which is well under 45 minutes. The refund agent reads that value, so an order that was really delivered late but had no recorded time would be treated as on time and denied.
- **Keyword-style retrieval.** TF-IDF matches words, not meaning, so two phrasings with the same meaning but different words can miss each other, and answers split across a chunk boundary can be lost (shown by the zero-overlap run).
- **Crash safety is partial.** Checkpoints are saved after each tool and the ledger write is skipped if the same run, tool and order is already recorded, which covers a crash between a tool and its checkpoint. A crash during the ledger write itself, or two different runs on the same order, are not covered.
- **Token budget.** The budget is checked before each call, so the last call that starts under the budget can push the total slightly past it.

**Next steps**

- Run the ticket-triage prompts on a real language model and compare its accuracy, token use and answer quality with the mock-model results.
- Rebuild the Premium flag from data before the lapse cutoff only, so the retention list can be tested fairly without using future information.
- Check an order's refund history before issuing money, so the same order can never be refunded twice, even across different runs.