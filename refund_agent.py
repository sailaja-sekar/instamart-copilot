import glob
import json
import os
import sqlite3
import time
from datetime import datetime

import pandas as pd

import mock_llm
from policy_rag import retrieve        # the retrieval built in tasks 1 to 3 is reused here

DB_PATH = os.path.join("data", "instamart.db")
LEDGER = os.path.join("outputs", "refund_ledger.jsonl")
RUNS_FILE = os.path.join("outputs", "agent_runs.jsonl")
DEMOS_FILE = os.path.join("outputs", "agent_demos.jsonl")
CURRENT = {"run_id": ""}               # only used to label ledger lines

class SimulatedCrash(Exception):
    pass

# ---------- Task 5: tools ----------
def get_order(order_id):
    con = sqlite3.connect(DB_PATH)
    try:
        row = con.execute(
            "SELECT order_id, status, order_amount, delivery_minutes FROM orders WHERE order_id = ?",
            (order_id,)).fetchone()
    finally:
        con.close()
    if row is None:
        return {"error": "order not found"}
    return {"order_id": row[0], "status": row[1], "order_amount": row[2], "delivery_minutes": row[3]}

def search_policy(query):
    return {"results": retrieve(query)}

def calculate_refund(order_amount, delivery_minutes):
    if delivery_minutes is not None and float(delivery_minutes) > 45:
        return {"refund_inr": round(float(order_amount), 2)}
    return {"refund_inr": 0.0}

def _write_ledger(tool, order_id, refund_inr):
    os.makedirs("outputs", exist_ok=True)
    if os.path.exists(LEDGER):                       # idempotency: never write the same action twice
        with open(LEDGER, encoding="utf-8") as f:
            for existing in f:
                e = json.loads(existing)
                if (e["run_id"], e["tool"], e["order_id"]) == (CURRENT["run_id"], tool, order_id):
                    return
    line = {"timestamp": datetime.now().isoformat(timespec="seconds"), "tool": tool,
            "order_id": order_id, "refund_inr": refund_inr, "run_id": CURRENT["run_id"]}
    with open(LEDGER, "a", encoding="utf-8") as f:
        f.write(json.dumps(line) + "\n")

def issue_refund(order_id, refund_inr):
    if refund_inr > 1000:
        return {"error": "refunds above INR 1000 must be escalated to a human"}
    _write_ledger("issue_refund", order_id, refund_inr)
    return {"refund_inr": refund_inr}

def escalate_to_human(order_id, refund_inr):
    _write_ledger("escalate_to_human", order_id, refund_inr)
    return {"refund_inr": refund_inr}

TOOLS_SPEC = [
    {"name": "get_order",
     "description": "Look up an order in the database and return its status, amount and delivery time.",
     "parameters": {"type": "object",
                    "properties": {"order_id": {"type": "string", "description": "Order id such as ORD-100001"}},
                    "required": ["order_id"]}},
    {"name": "search_policy",
     "description": "Search the company policy documents and return the three most relevant passages.",
     "parameters": {"type": "object",
                    "properties": {"query": {"type": "string", "description": "What to look up"}},
                    "required": ["query"]}},
    {"name": "calculate_refund",
     "description": "Work out the refund in INR from the order amount and the delivery time in minutes.",
     "parameters": {"type": "object",
                    "properties": {"order_amount": {"type": "number", "description": "Order amount in INR"},
                                   "delivery_minutes": {"type": "number", "description": "Delivery time in minutes"}},
                    "required": ["order_amount", "delivery_minutes"]}},
    {"name": "issue_refund",
     "description": "Issue a refund of up to INR 1000 and record it in the ledger.",
     "parameters": {"type": "object",
                    "properties": {"order_id": {"type": "string"}, "refund_inr": {"type": "number"}},
                    "required": ["order_id", "refund_inr"]}},
    {"name": "escalate_to_human",
     "description": "Send a refund above INR 1000 to a human support lead and record it in the ledger.",
     "parameters": {"type": "object",
                    "properties": {"order_id": {"type": "string"}, "refund_inr": {"type": "number"}},
                    "required": ["order_id", "refund_inr"]}},
]
TOOL_MAP = {"get_order": get_order, "search_policy": search_policy,
            "calculate_refund": calculate_refund, "issue_refund": issue_refund,
            "escalate_to_human": escalate_to_human}

# ---------- Tasks 6 to 8: the ReAct loop, stop-safely limits and checkpoints ----------
SYSTEM_PROMPT = (
    "You are a refund AGENT for Instamart support. Decide the refund request by calling the tools "
    "one at a time: get_order, search_policy, calculate_refund, issue_refund, escalate_to_human. "
    "When you are done, reply with one line that starts with REFUND:, ESCALATE:, DENIED: or NOT_FOUND:."
)

def _save_checkpoint(state):
    os.makedirs("state", exist_ok=True)
    state["step"] = len(state["steps"])
    with open(os.path.join("state", f"{state['run_id']}.json"), "w", encoding="utf-8") as f:
        json.dump(state, f)

def _refund_of(state):
    for step in reversed(state["steps"]):
        if step["tool"] in ("issue_refund", "escalate_to_human") and "refund_inr" in step["observation"]:
            return float(step["observation"]["refund_inr"])
    return 0.0

def _result(state, status, final_answer):
    return {"run_id": state["run_id"], "scenario_id": state["scenario_id"], "status": status,
            "final_answer": final_answer, "steps": state["steps"], "llm_calls": state["llm_calls"],
            "tokens_used": state["tokens_used"], "refund_inr": _refund_of(state)}

def _fallback(kind, state):
    tools = " -> ".join(s["tool"] for s in state["steps"]) or "none"
    summary = (f"Handing over to a human agent: stopped with {kind} after {state['llm_calls']} model "
               f"calls and {len(state['steps'])} tool steps ({tools}). Please review this request manually.")
    return _result(state, kind, summary)

def _loop(state, max_iterations, token_limit, time_limit_seconds, crash_after_tools):
    start = time.monotonic()
    while True:
        if time.monotonic() - start >= time_limit_seconds:
            return _fallback("FALLBACK_TIMEOUT", state)
        if state["llm_calls"] >= max_iterations:
            return _fallback("FALLBACK_MAX_ITERATIONS", state)
        response = mock_llm.chat(state["messages"], tools=TOOLS_SPEC)
        state["llm_calls"] += 1
        state["tokens_used"] += response.usage.total_tokens
        if state["tokens_used"] > token_limit:               # stop before running the requested tool
            return _fallback("FALLBACK_TOKEN_LIMIT", state)
        message = response.choices[0].message
        if not message.tool_calls:
            final = message.content
            return _result(state, final.split(":")[0].strip(), final)
        call = message.tool_calls[0]
        state["messages"].append({"role": "assistant", "content": None,
                                  "tool_calls": [{"id": call.id, "name": call.name,
                                                  "arguments": call.arguments}]})
        observation = TOOL_MAP[call.name](**call.arguments)
        state["messages"].append({"role": "tool", "tool_call_id": call.id, "name": call.name,
                                  "content": json.dumps(observation)})
        state["steps"].append({"tool": call.name, "arguments": call.arguments,
                               "observation": observation})
        state["executed_tools"].append(call.name)
        _save_checkpoint(state)
        if crash_after_tools is not None and len(state["executed_tools"]) == crash_after_tools:
            raise SimulatedCrash(f"simulated crash after tool {crash_after_tools}")

def _record(result, path):
    os.makedirs("outputs", exist_ok=True)
    line = {"scenario_id": result["scenario_id"], "run_id": result["run_id"],
            "status": result["status"], "final_answer": result["final_answer"],
            "llm_calls": result["llm_calls"], "tokens_used": result["tokens_used"],
            "refund_inr": result["refund_inr"], "steps": result["steps"]}
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(line) + "\n")

def run_agent(user_message, scenario_id, max_iterations=6, token_limit=6000,
              time_limit_seconds=10, run_id=None, crash_after_tools=None, log_file=RUNS_FILE):
    state = {"run_id": run_id or scenario_id, "scenario_id": scenario_id,
             "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                          {"role": "user", "content": user_message}],
             "tokens_used": 0, "llm_calls": 0, "steps": [], "executed_tools": [], "step": 0}
    CURRENT["run_id"] = state["run_id"]
    result = _loop(state, max_iterations, token_limit, time_limit_seconds, crash_after_tools)
    _record(result, log_file)
    return result

def resume_agent(run_id, max_iterations=6, token_limit=6000, time_limit_seconds=10,
                 log_file=DEMOS_FILE):
    with open(os.path.join("state", f"{run_id}.json"), encoding="utf-8") as f:
        state = json.load(f)
    CURRENT["run_id"] = run_id
    result = _loop(state, max_iterations, token_limit, time_limit_seconds, None)
    _record(result, log_file)
    return result

if __name__ == "__main__":
    for path in [LEDGER, RUNS_FILE, DEMOS_FILE] + glob.glob(os.path.join("state", "*.json")):
        if os.path.exists(path):
            os.remove(path)

    scenarios = pd.read_csv("data/raw/agent_scenarios.csv", keep_default_na=False)
    results = {}
    print(f"{'scenario':9}{'status':26}{'refund INR':>11}{'calls':>7}{'tokens':>8}")
    for _, s in scenarios.iterrows():
        r = run_agent(s["message"], s["scenario_id"])
        results[s["scenario_id"]] = r
        print(f"{s['scenario_id']:9}{r['status']:26}{r['refund_inr']:>11.2f}{r['llm_calls']:>7}{r['tokens_used']:>8}")
        expected = s["expected_outcome"]
        if expected == "FALLBACK":
            assert r["status"] == "FALLBACK_MAX_ITERATIONS"
        else:
            assert r["status"] == expected, (s["scenario_id"], r["status"], expected)
        assert abs(r["refund_inr"] - float(s["expected_refund_inr"])) <= 0.01
    assert results["S1"]["llm_calls"] == 5
    assert results["S7"]["llm_calls"] == 6 and results["S7"]["tokens_used"] <= 6000
    print("\nALL SEVEN SCENARIOS MATCH THE EXPECTED OUTCOMES")

    s1_message = scenarios.loc[scenarios["scenario_id"] == "S1", "message"].iloc[0]

    tok = run_agent(s1_message, "S1", token_limit=200, run_id="S1_token_limit_demo", log_file=DEMOS_FILE)
    print("\ndemo token_limit=200   ->", tok["status"], "| model calls:", tok["llm_calls"],
          "| tools run:", len(tok["steps"]))
    assert tok["status"] == "FALLBACK_TOKEN_LIMIT"

    tim = run_agent(s1_message, "S1", time_limit_seconds=0, run_id="S1_timeout_demo", log_file=DEMOS_FILE)
    print("demo time_limit_seconds=0 ->", tim["status"], "| model calls:", tim["llm_calls"])
    assert tim["status"] == "FALLBACK_TIMEOUT" and tim["llm_calls"] == 0

    try:
        run_agent(s1_message, "S1", run_id="S1_crash_demo", crash_after_tools=2, log_file=DEMOS_FILE)
    except SimulatedCrash as crash:
        print("\ncrash demo:", crash)
    resumed = resume_agent("S1_crash_demo")
    executed = [step["tool"] for step in resumed["steps"]]
    print("tools executed across the crash and the resume:", executed)
    print("resumed result:", resumed["status"], resumed["refund_inr"])
    assert executed == ["get_order", "search_policy", "calculate_refund", "issue_refund"]
    assert resumed["status"] == "REFUND" and abs(resumed["refund_inr"] - 128.25) <= 0.01

    # idempotency check: repeating an action of the same run must not add a second ledger line
    before = sum(1 for _ in open(LEDGER, encoding="utf-8"))
    CURRENT["run_id"] = "S1_crash_demo"
    issue_refund("ORD-100048", 128.25)
    after = sum(1 for _ in open(LEDGER, encoding="utf-8"))
    print("\nidempotency check: ledger lines before and after repeating issue_refund:", before, after)
    assert before == after

    n_ledger = sum(1 for _ in open(LEDGER, encoding="utf-8"))
    print("\nledger lines:", n_ledger, "| scenario runs logged:",
          sum(1 for _ in open(RUNS_FILE, encoding="utf-8")),
          "| checkpoint files:", len(glob.glob(os.path.join("state", "*.json"))))
    print("AGENT CHECKS PASSED")