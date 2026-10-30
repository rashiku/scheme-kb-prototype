"""Step 1: read each scheme document, produce DRAFT field records with evidence.
Run:  python extract.py          (offline rules)
      python extract.py --llm    (Gemini; see llm_extract.py)
NOTE: the default extractor is rule-based (regex + keywords) so it runs offline with no API key.
In production, replace the per-field rules with an LLM call; the record format, evidence,
conflict handling and review gate stay the same.
"""
import json, re, unicodedata, datetime
from pathlib import Path

BASE = Path(__file__).parent
DOCS, LISTINGS, OUT = BASE / "data" / "docs", BASE / "data" / "myscheme", BASE / "output"
TODAY = datetime.date.today().isoformat()


def n(s):  # normalise unicode so Hindi text compares reliably
    return unicodedata.normalize("NFC", s)


def rx(p):
    return re.compile(n(p), re.I)


MONTHS = {n(k): v for k, v in {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7,
    "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "जनवरी": 1, "फरवरी": 2, "फ़रवरी": 2, "मार्च": 3, "अप्रैल": 4, "मई": 5, "जून": 6,
    "जुलाई": 7, "अगस्त": 8, "सितंबर": 9, "सितम्बर": 9, "अक्टूबर": 10,
    "नवंबर": 11, "नवम्बर": 11, "दिसंबर": 12, "दिसम्बर": 12}.items()}

LINK = r"(https?://\S+|\[PLACEHOLDER-LINK:\s*[^\]]+\])"
PAT = {
    "en": dict(
        ref=r"Notification No\.?\s*([^\s,]+)",
        dept=r"^Department of [A-Za-z &]+$",
        name=r"^([A-Za-z ]+?(?:yojana|abhiyan))(?:\s*\(\w+\))?$",
        benefit=r"^Benefits?$", elig=r"^Eligibility$", docs=r"^Documents Required$", apply=r"^How to Apply$",
        deadline=r"^(?:Last date[^:]*|Deadline)\s*:\s*(.+?)\.?$", link=LINK,
        freq=[(r"one[- ]time", "one-time"), (r"per year|annual|yearly", "per year"), (r"per month|monthly", "per month")],
        cash=r"financial assistance|grant|stipend|scholarship"),
    "hi": dict(
        ref=r"अधिसूचना क्रमांक\s*:?\s*([^\s,]+)",
        dept=r"^.*विभाग$",
        name=r"^(.*योजना)$",
        benefit=r"^लाभ$", elig=r"^पात्रता$", docs=r"^आवश्यक दस्तावेज़$", apply=r"^आवेदन कैसे करें$",
        deadline=r"^अंतिम तिथि\s*:\s*(.+?)\.?$", link=LINK,
        freq=[(r"एकमुश्त", "one-time"), (r"प्रति वर्ष|वार्षिक", "per year"), (r"प्रति माह|मासिक", "per month")],
        cash=r"आर्थिक सहायता|अनुदान|छात्रवृत्ति"),
}
AMOUNT = rx(r"(?:Rs\.?|₹|रु\.?)\s*([\dO][\dO,]*)")
FIELDS = ["scheme_name", "department", "benefit_type", "benefit_amount", "benefit_frequency",
          "eligibility", "documents_required", "how_to_apply", "deadline", "official_link"]


def parse_date(s):
    m = re.match(r"(\d{1,2})\s+(\S+)\s+(\d{4})$", n(s).strip())
    if not m or n(m.group(2)).lower() not in MONTHS:
        return None
    try:
        return datetime.date(int(m.group(3)), MONTHS[n(m.group(2)).lower()], int(m.group(1))).isoformat()
    except ValueError:
        return None


def extract(path):
    raw = n(path.read_text(encoding="utf-8"))
    P = PAT["hi" if re.search(r"[\u0900-\u097F]", raw) else "en"]
    ocr, lines, page = None, [], 1
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("#OCR"):
            ocr = float(re.search(r"engine_conf=([\d.]+)", line).group(1))
            continue
        m = re.fullmatch(r"\[Page (\d+)\]", line)
        if m:
            page = int(m.group(1))
            continue
        lines.append((page, line))

    def find(pattern):
        for pg, ln in lines:
            m = rx(pattern).search(ln)
            if m:
                return pg, ln, m

    def section(pattern):  # heading line + following non-blank lines
        for i, (pg, ln) in enumerate(lines):
            if rx(pattern).search(ln):
                items = []
                for _, l in lines[i + 1:]:
                    if not l:
                        break
                    items.append(l)
                return pg, ln, items

    r = find(P["ref"])
    ref = r[2].group(1).rstrip(".,;") if r else path.name  # no ID -> fall back to source file name
    src, recs = f"synthetic:{path.name}", []

    def add(field, value=None, text=None, pg=None, where=None, conf=0.0, note=""):
        ok = value not in (None, [], "")
        if ok and ocr:
            conf = round(conf * ocr, 2)  # scanned source -> lower trust in everything
        recs.append({
            "scheme_ref": ref, "field": field, "value": value if ok else None,
            "evidence": {"text": text, "location": f"Page {pg}, {where}", "source": src,
                         "captured_at": TODAY} if ok else None,
            "confidence": conf if ok else None,
            "status": "found" if ok else "not found",
            "note": note if (ok or note) else "Not present in the document."})

    r = find(P["name"])
    name = r and (r[2].group(1).strip().title() if r[2].group(1).isupper() else r[2].group(1).strip())
    add("scheme_name", name, r and r[1], r and r[0], "heading", 0.95)
    r = find(P["dept"])
    add("department", r and r[1], r and r[1], r and r[0], "header", 0.95)

    sec = section(P["benefit"])
    if sec:
        pg, head, items = sec
        text, where = " ".join(items), f"section '{head}'"
        a = AMOUNT.search(text)
        amt, note = None, ""
        if a:
            digits = a.group(1)
            if "O" in digits.upper():
                note = f"OCR correction: read '{digits}' as '{digits.upper().replace('O', '0')}'. Check against the scan."
            amt = int(digits.upper().replace("O", "0").replace(",", ""))
        add("benefit_amount", amt, text, pg, where, 0.65 if note else 0.95, note)
        fr = next((v for p, v in P["freq"] if rx(p).search(text)), None)
        add("benefit_frequency", fr, text, pg, where, 0.9)
        add("benefit_type", "cash assistance" if rx(P["cash"]).search(text) else None, text, pg, where, 0.85)
    else:
        for f in ("benefit_amount", "benefit_frequency", "benefit_type"):
            add(f)

    for field, key in (("eligibility", "elig"), ("documents_required", "docs")):
        sec = section(P[key])
        if sec:
            items = [re.sub(r"^\d+[.)]\s*", "", l) for l in sec[2]]
            add(field, items, "\n".join(sec[2]), sec[0], f"section '{sec[1]}'", 0.9)
        else:
            add(field)
    sec = section(P["apply"])
    add("how_to_apply", sec and " ".join(sec[2]), sec and " ".join(sec[2]), sec and sec[0],
        sec and f"section '{sec[1]}'", 0.85)

    r = find(P["deadline"])
    if r and parse_date(r[2].group(1)):
        add("deadline", parse_date(r[2].group(1)), r[1], r[0], "deadline line", 0.95)
    elif r:
        add("deadline", note=f"A deadline line exists on page {r[0]} ('{r[1]}') but could not be read as a date. "
                              "Needs a human to read the scan. Not guessed.")
    else:
        add("deadline")
    r = find(P["link"])
    add("official_link", r and r[2].group(1).strip("[]"), r and r[1], r and r[0], "link line", 0.9,
        "Synthetic placeholder instead of a real URL." if r and "PLACEHOLDER" in r[1] else
        ("" if r else "No official link printed in the document."))
    return ref, path.name, recs


def norm(v):
    if isinstance(v, list):
        return sorted(x.strip().lower() for x in v)
    return v.strip().lower() if isinstance(v, str) else v


def merge_listing(recs, listing):
    """Compare document values with the MyScheme listing. Disagreement => conflict, keep both."""
    for fld, item in listing["fields"].items():
        rec = next(r for r in recs if r["field"] == fld)
        ev = {"text": item["text"], "location": item["section"], "source": listing["source_name"],
              "captured_at": listing["captured_at"]}
        if rec["status"] == "not found":
            rec.update(value=item["value"], evidence=ev, status="found", confidence=0.75,
                       note="Only source is the MyScheme listing; the document does not confirm it.")
        elif norm(rec["value"]) == norm(item["value"]):
            rec["confidence"] = max(rec["confidence"], 0.98)
            rec["note"] = (rec["note"] + " MyScheme listing agrees.").strip()
        else:
            rec.update(value=[rec["value"], item["value"]], evidence=[rec["evidence"], ev],
                       status="conflict", confidence=0.5,
                       note=f"Document says {rec['value']}, MyScheme says {item['value']}. Neither picked; reviewer must choose.")


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", action="store_true", help="use Gemini (needs GEMINI_API_KEY) instead of the offline rules")
    use_llm = ap.parse_args().llm
    if use_llm:
        from llm_extract import extract_llm
    OUT.mkdir(exist_ok=True)
    listings = {json.loads(p.read_text(encoding="utf-8"))["scheme_ref"]: json.loads(p.read_text(encoding="utf-8"))
                for p in LISTINGS.glob("*.json")}
    drafts = {}
    for path in sorted(DOCS.glob("*.txt")):
        ref, fname, recs = extract_llm(path) if use_llm else extract(path)
        if ref in listings:
            merge_listing(recs, listings[ref])
        drafts[ref] = {"review_status": "draft", "source_file": fname, "records": recs}
    (OUT / "drafts.json").write_text(json.dumps(drafts, ensure_ascii=False, indent=2), encoding="utf-8")

    for ref, d in drafts.items():
        print(f"\n== {ref}  ({d['source_file']})  DRAFT - needs human review")
        for r in d["records"]:
            flag = "  <-- CHECK" if r["status"] != "found" or (r["confidence"] or 0) < 0.8 else ""
            v = json.dumps(r["value"], ensure_ascii=False)
            print(f"  {r["field"]:<19}{r['status']:<10}{str(r['confidence']):<6}{v[:60]}{flag}")
    print("\nSaved output/drafts.json")


if __name__ == "__main__":
    main()
