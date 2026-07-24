from flask import Flask, request, jsonify
import re

app = Flask(__name__)

def normalize_value(v):
    if isinstance(v, str):
        return re.sub(r"\s+", " ", v).strip()
    if isinstance(v, list):
        return [normalize_value(x) for x in v]
    if isinstance(v, dict):
        items = ((k, normalize_value(val)) for k, val in v.items() if k != "client_ts")
        return {k: val for k, val in sorted(items, key=lambda kv: kv[0])}
    return v

def canonical_step(step):
    return step["tool"], normalize_value(step.get("args", {}))

def is_ab_cycle(canon_steps):
    if len(canon_steps) < 6:
        return False
    last6 = canon_steps[-6:]
    a, b = last6[0], last6[1]
    if a == b:
        return False
    for i in range(6):
        expected = a if i % 2 == 0 else b
        if last6[i] != expected:
            return False
    return True

def decide(payload):
    total_tokens = sum(step.get("tokens_used", 0) for step in payload.get("steps", []))
    budget = payload.get("budget_tokens", 0)

    if total_tokens >= budget:
        return {
            "decision": "halt",
            "reason": f"Cumulative tokens_used ({total_tokens}) has reached the budget ({budget})."
        }

    steps = payload.get("steps", [])
    canon = [canonical_step(step) for step in steps]

    if len(canon) >= 3 and canon[-1] == canon[-2] == canon[-3]:
        tool = canon[-1][0]
        return {
            "decision": "halt",
            "reason": f"Same tool and arguments repeated 3 times in a row ({tool})."
        }

    if is_ab_cycle(canon):
        return {
            "decision": "halt",
            "reason": "Detected a repeating 2-step tool cycle in the trailing steps."
        }

    return {
        "decision": "continue",
        "reason": "Under budget; no loop pattern detected."
    }

@app.route("/run-budget-and-loop-guard", methods=["POST"])
def run_budget_and_loop_guard():
    payload = request.get_json(silent=True)

    if payload is None:
        return jsonify({
            "decision": "halt",
            "reason": "Invalid or missing JSON body."
        }), 400

    result = decide(payload)
    return jsonify(result), 200

if __name__ == "__main__":
    app.run(debug=True)