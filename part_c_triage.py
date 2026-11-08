import json
import random
import re
import time

import pandas as pd

import mock_llm

MAX_INPUT_TOKENS = 400
MAX_RETRIES = 3
BASE_DELAY = 0.05
CATEGORIES = ["billing", "delivery", "technical", "fraud"]

# ---------- Task 2: redaction (applied in exactly this order) ----------
PATTERNS = [
    ("email", re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "[EMAIL]"),
    ("phone", re.compile(r"\b[6-9]\d{9}\b"), "[PHONE]"),
    ("order_id", re.compile(r"ORD-\d{6}"), "[ORDER_ID]"),
]

def redact(text, counts=None):
    for name, pattern, placeholder in PATTERNS:
        text, n = pattern.subn(placeholder, text)
        if counts is not None:
            counts[name] += n
    return text

# ---------- Task 3: the two system prompts ----------
ZERO_SHOT = (
    "You are a support ticket triage assistant. CLASSIFY the customer ticket into exactly "
    "one of these categories: billing, delivery, technical, fraud. "
    'Reply with JSON only, in the form {"category": "...", "reason": "..."}, and nothing else.'
)
FEW_SHOT = ZERO_SHOT + (
    "\nEXAMPLES:\n"
    'Ticket: I was charged twice for order [ORDER_ID], please return the extra payment. '
    '-> {"category": "billing", "reason": "double charge"}\n'
    'Ticket: My order [ORDER_ID] never reached me and the rider does not answer. '
    '-> {"category": "delivery", "reason": "order not received"}\n'
    'Ticket: The app freezes and shows an error whenever I open the cart. '
    '-> {"category": "technical", "reason": "app problem"}\n'
    'Ticket: Someone used my card without my permission, I did not place this order. '
    '-> {"category": "fraud", "reason": "unauthorized transaction"}'
)
assert "CLASSIFY" in ZERO_SHOT and "EXAMPLES:" not in ZERO_SHOT
assert "CLASSIFY" in FEW_SHOT and "\nEXAMPLES:\n" in FEW_SHOT and '"fraud"' in FEW_SHOT

tickets = pd.read_csv("data/raw/tickets.csv", keep_default_na=False)
segments = pd.read_csv("outputs/customer_segments.csv").set_index("customer_id")

# ---------- Task 2 report: substitutions over all 164 tickets ----------
counts = {"email": 0, "phone": 0, "order_id": 0}
redacted_all = [redact(t, counts) for t in tickets["text"]]
total = sum(counts.values())
print("redactions:", counts, "| total:", total)
left = sum(len(p.findall(t)) for _, p, _ in PATTERNS for t in redacted_all)
print("matches left after redaction:", left)
assert counts == {"email": 55, "phone": 91, "order_id": 132} and total == 278 and left == 0

# ---------- Task 4: resilient model call ----------
def call_with_retry(ticket_id, messages, stats):
    retries = 0
    while True:
        try:
            return mock_llm.chat(messages)
        except mock_llm.TransientLLMError:
            stats["transient_errors"] += 1
            if retries >= MAX_RETRIES:
                stats["permanent_errors"] += 1
                raise
            wait = BASE_DELAY * 2 ** retries * random.uniform(0.9, 1.15)
            print(f"  retry log: ticket {ticket_id} | retry number {retries} | wait {wait:.4f}s")
            assert BASE_DELAY * 2 ** retries * 0.9 <= wait <= BASE_DELAY * 2 ** retries * 1.15
            time.sleep(wait)
            retries += 1

# ---------- Task 5: validate every answer ----------
def validate(content):
    try:
        obj = json.loads(content)
    except (TypeError, ValueError):
        found = {w for w in re.findall(r"[a-z]+", (content or "").lower()) if w in CATEGORIES}
        if len(found) == 1:
            return "classified_keyword", found.pop()
        return "flagged_invalid_output", ""
    if isinstance(obj, dict) and obj.get("category") in CATEGORIES:
        return "classified_json", obj["category"]
    return "flagged_invalid_output", ""

# ---------- one full pass over the tickets ----------
def run_pipeline(system_prompt, token_budget=None):
    mock_llm.reset()
    random.seed(7)
    stats = {"transient_errors": 0, "permanent_errors": 0}
    running_tokens = 0
    rows = []
    for _, t in tickets.iterrows():
        row = {"ticket_id": t["ticket_id"], "customer_id": t["customer_id"],
               "true_category": t["true_category"], "category": "", "tokens_used": 0}
        text = t["text"]
        if not text.strip():
            row["status"] = "skipped_empty"
        elif mock_llm.est_tokens(text) > MAX_INPUT_TOKENS:
            row["status"] = "flagged_long"
        elif token_budget is not None and running_tokens >= token_budget:
            row["status"] = "budget_exhausted"
        else:
            safe = redact(text)
            messages = [{"role": "system", "content": system_prompt},
                        {"role": "user", "content": safe}]
            for p_name, pattern, _ in PATTERNS:           # nothing personal may reach the model
                assert not any(pattern.search(m["content"]) for m in messages)
            assert messages[-1]["content"] == safe
            response = call_with_retry(t["ticket_id"], messages, stats)
            used = response.usage.total_tokens
            running_tokens += used
            row["tokens_used"] = used
            row["status"], row["category"] = validate(response.choices[0].message.content)
        rows.append(row)
    return pd.DataFrame(rows), stats, running_tokens

def summarise(label, df, stats, total_tokens):
    classified = df[df["status"].isin(["classified_json", "classified_keyword"])]
    acc = (classified["category"] == classified["true_category"]).mean()
    print(f"\n{label}")
    print("status counts:", df["status"].value_counts().to_dict())
    print("transient errors:", stats["transient_errors"], "| permanent errors:", stats["permanent_errors"])
    print("classified:", len(classified), "| accuracy:", round(100 * acc, 1), "%",
          f"({int((classified['category'] == classified['true_category']).sum())} of {len(classified)})")
    print("total tokens:", total_tokens, "| tokens per classified ticket:",
          round(total_tokens / len(classified), 1))
    return classified, acc

# ---------- Task 6: zero-shot vs few-shot ----------
print("\nzero-shot prompt tokens:", mock_llm.est_tokens(ZERO_SHOT),
      "| few-shot prompt tokens:", mock_llm.est_tokens(FEW_SHOT))
zero_df, zero_stats, zero_tokens = run_pipeline(ZERO_SHOT)
zero_cls, zero_acc = summarise("ZERO-SHOT (no budget)", zero_df, zero_stats, zero_tokens)
print("\nconfusion table (rows = true category, columns = predicted):")
print(pd.crosstab(zero_cls["true_category"], zero_cls["category"]).to_string())

few_df, few_stats, few_tokens = run_pipeline(FEW_SHOT)
few_cls, few_acc = summarise("FEW-SHOT (no budget)", few_df, few_stats, few_tokens)

for df, stats in [(zero_df, zero_stats), (few_df, few_stats)]:
    vc = df["status"].value_counts().to_dict()
    assert vc.get("classified_json") == 135 and vc.get("classified_keyword") == 12
    assert vc.get("flagged_invalid_output") == 9
    assert vc.get("skipped_empty") == 4 and vc.get("flagged_long") == 4
    assert stats["transient_errors"] == 19 and stats["permanent_errors"] == 0
assert abs(100 * zero_acc - 85.7) <= 0.5 and abs(100 * few_acc - 100) <= 0.5

# ---------- Task 7: budget demo, routing and outputs ----------
def route(row):
    if row["status"] in ("skipped_empty", "flagged_long", "flagged_invalid_output", "budget_exhausted"):
        return "human_review", "NORMAL"
    if row["category"] == "fraud":
        return "security_team", "HIGH"
    if row["is_premium"]:
        return "premium_desk", "HIGH"
    return "support_queue", "NORMAL"

def finish(df):
    df = df.copy()
    df["segment_name"] = df["customer_id"].map(segments["segment_name"]).fillna("")
    df["is_premium"] = df["customer_id"].map(segments["is_premium"]).fillna(False).astype(bool)
    df[["route", "priority"]] = df.apply(lambda r: pd.Series(route(r)), axis=1)
    cols = ["ticket_id", "customer_id", "status", "category", "segment_name",
            "priority", "route", "tokens_used"]
    return df[cols]

DEMO_BUDGET = 6000
demo_df, demo_stats, demo_tokens = run_pipeline(ZERO_SHOT, token_budget=DEMO_BUDGET)
n_exhausted = int((demo_df["status"] == "budget_exhausted").sum())
print(f"\nBUDGET DEMO (zero-shot, TOKEN_BUDGET={DEMO_BUDGET}): budget_exhausted tickets =", n_exhausted,
      "| tokens used:", demo_tokens)
assert n_exhausted >= 1
finish(demo_df).to_csv("outputs/triage_budget_demo.csv", index=False)

final_df, final_stats, final_tokens = run_pipeline(FEW_SHOT, token_budget=100000)
final = finish(final_df)
final.to_csv("outputs/triage_results.csv", index=False)
print("\nFINAL few-shot run, TOKEN_BUDGET=100000:", final["status"].value_counts().to_dict())
print("routes:", final["route"].value_counts().to_dict())
print("priorities:", final["priority"].value_counts().to_dict())

assert len(final) == 164
assert (final["status"] == "budget_exhausted").sum() == 0
human = final["status"].isin(["skipped_empty", "flagged_long", "flagged_invalid_output", "budget_exhausted"])
assert (final.loc[human, "route"] == "human_review").all()
assert (final.loc[final["category"] == "fraud", "route"] == "security_team").all()
assert (final.loc[final["route"] == "premium_desk", "segment_name"] == "Premium Big-Ticket").all()
print("\nTRIAGE CHECKS PASSED")