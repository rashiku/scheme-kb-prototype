"""Step 3: the human review gate. Nothing is exported unless a named person approved it.
  python publish.py status
  python publish.py approve AGR/2026/114 --reviewer Asha --resolve benefit_amount=6000 --resolve deadline=2026-12-31
  python publish.py export          # writes output/published.json (approved schemes only)
"""
import argparse, json, datetime
from pathlib import Path

PATH = Path(__file__).parent / "output" / "drafts.json"
OUT = Path(__file__).parent / "output" / "published.json"
drafts = json.loads(PATH.read_text(encoding="utf-8"))
save = lambda: PATH.write_text(json.dumps(drafts, ensure_ascii=False, indent=2), encoding="utf-8")

ap = argparse.ArgumentParser()
ap.add_argument("cmd", choices=["status", "approve", "export"])
ap.add_argument("ref", nargs="?")
ap.add_argument("--reviewer")
ap.add_argument("--resolve", action="append", default=[], help="field=value (must be one of the kept values)")
a = ap.parse_args()

if a.cmd == "status":
    for ref, d in drafts.items():
        open_c = [r["field"] for r in d["records"] if r["status"] == "conflict"]
        print(f"{ref:<24}{d['review_status']:<10}{'unresolved conflicts: ' + ', '.join(open_c) if open_c else ''}")

elif a.cmd == "approve":
    d = drafts[a.ref]
    if not a.reviewer:
        raise SystemExit("A reviewer name is required.")
    for item in a.resolve:
        field, val = item.split("=", 1)
        r = next(x for x in d["records"] if x["field"] == field)
        if r["status"] != "conflict":
            raise SystemExit(f"{field} is not in conflict.")
        i = next((k for k, v in enumerate(r["value"]) if str(v) == val), None)
        if i is None:
            raise SystemExit(f"{val!r} is not one of the kept values {r['value']}.")
        r["note"] += f" | RESOLVED by {a.reviewer}: chose {val}; other value was {r['value'][1 - i]}."
        r.update(value=r["value"][i], evidence=r["evidence"][i], status="found", confidence=1.0)
    left = [r["field"] for r in d["records"] if r["status"] == "conflict"]
    if left:
        raise SystemExit(f"Cannot approve: unresolved conflicts in {left}. Use --resolve field=value.")
    d.update(review_status="approved", reviewer=a.reviewer, approved_at=datetime.datetime.now().isoformat(timespec="seconds"))
    save()
    print(f"{a.ref} approved by {a.reviewer}.")

elif a.cmd == "export":
    live = {ref: d for ref, d in drafts.items() if d["review_status"] == "approved"}
    for ref, d in live.items():  # last safety net: no value without evidence
        for r in d["records"]:
            assert r["status"] != "found" or r["evidence"], f"{ref}/{r['field']} has a value but no evidence"
    OUT.write_text(json.dumps(live, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Exported {len(live)} approved scheme(s); {len(drafts) - len(live)} draft(s) held back.")
