"""Step 2: score drafts against the hand-checked answers in data/gold.json, field by field.
Run:  python evaluate.py
"""
import json
from pathlib import Path
from collections import defaultdict

BASE = Path(__file__).parent
drafts = json.loads((BASE / "output" / "drafts.json").read_text(encoding="utf-8"))
gold = json.loads((BASE / "data" / "gold.json").read_text(encoding="utf-8"))


def norm(v):
    if isinstance(v, list):
        return sorted(str(x).strip().lower() for x in v)
    return v.strip().lower() if isinstance(v, str) else v


stats = defaultdict(lambda: defaultdict(int))
confident_wrong = []
for ref, d in drafts.items():
    for r in d["records"]:
        truth, f = gold[ref][r["field"]], r["field"]
        if r["status"] == "conflict":  # conflict is fine if the true value was kept, not silently lost
            outcome = "correct" if any(norm(v) == norm(truth) for v in r["value"]) else "wrong"
            stats[f]["conflicts_flagged"] += 1
        elif r["status"] == "not found":
            outcome = "correctly_empty" if truth is None else "missed"
        else:
            outcome = "correct" if norm(r["value"]) == norm(truth) else "wrong"
        stats[f][outcome] += 1
        stats[f]["n"] += 1
        if outcome == "wrong" and (r["confidence"] or 0) >= 0.8:
            confident_wrong.append((ref, f))

print(f"{'field':<20}{'n':>3}{'correct':>9}{'wrong':>7}{'missed':>8}{'empty-ok':>10}{'accuracy':>10}")
tot = defaultdict(int)
for f, s in stats.items():
    ok = s["correct"] + s["correctly_empty"]
    print(f"{f:<20}{s['n']:>3}{s['correct']:>9}{s['wrong']:>7}{s['missed']:>8}{s['correctly_empty']:>10}{ok / s['n']:>10.0%}")
    for k in ("n", "correct", "wrong", "missed", "correctly_empty"):
        tot[k] += s[k]
print(f"{'ALL':<20}{tot['n']:>3}{tot['correct']:>9}{tot['wrong']:>7}{tot['missed']:>8}{tot['correctly_empty']:>10}"
      f"{(tot['correct'] + tot['correctly_empty']) / tot['n']:>10.0%}")
print(f"\nConfident-but-wrong (confidence >= 0.8 and wrong): {len(confident_wrong)}  <- the number that must be ~0")
print("Missed = AI left it empty but a value exists (costs reviewer time). Wrong = AI gave a bad value (risks reaching a citizen).")
print("NOTE: 3 schemes / 30 fields only demonstrates the method. It proves nothing about 5,000 schemes.")
