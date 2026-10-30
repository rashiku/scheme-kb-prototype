"""Gemini-based extraction. The model PROPOSES values with an exact quote;
this code VERIFIES every quote exists word-for-word in the document before accepting it.
Anything that fails verification is left empty, with the rejected proposal named in the note.
No packages needed (uses urllib). Needs env var GEMINI_API_KEY; model via GEMINI_MODEL.
"""
import json, os, re, sys, time, urllib.request, urllib.error
from extract import n, rx, PAT, parse_date, FIELDS, TODAY

MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")  # alias; override if your key uses another model
FALLBACKS = os.environ.get("GEMINI_FALLBACKS", "gemini-3.1-flash-lite,gemini-flash-lite-latest")
URL = "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent"

PROMPT = """You extract fields from an Indian government scheme document (English or Hindi). Pages are marked like [Page 2].
Return ONLY a JSON object with exactly these keys: scheme_name, department, benefit_type, benefit_amount,
benefit_frequency, eligibility, documents_required, how_to_apply, deadline, official_link.
Each key maps to {"value": ..., "quote": ..., "reason": ...}.
Rules:
- "quote" must be copied EXACTLY, character for character, from the document, in its original language. Never paraphrase or translate it.
- If a field is absent or unreadable, set value and quote to null and say why in "reason". Do NOT guess.
- scheme_name, department: as written in the document; quote = the same text.
- benefit_type: one of "cash assistance", "in-kind", "service", "other". benefit_amount: integer rupees. benefit_frequency: one of "one-time", "per year", "per month", "other".
- eligibility, documents_required: list of strings, each copied exactly from the document without its leading number; quote = null.
- how_to_apply: copied exactly from the document. deadline: ISO date YYYY-MM-DD; quote = the exact text containing the date.
- official_link: the URL or placeholder reference exactly as printed.
"""


def _post(model, body, key):
    req = urllib.request.Request(URL.format(model), data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json", "x-goog-api-key": key})
    with urllib.request.urlopen(req, timeout=90) as resp:
        return json.loads(resp.read())


def call_gemini(doc_text):
    """Retries overloaded/rate-limited errors with growing waits, then tries fallback models."""
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        sys.exit("Set GEMINI_API_KEY first.\n  Windows PowerShell:  $env:GEMINI_API_KEY='your-key'\n  Mac/Linux:           export GEMINI_API_KEY='your-key'")
    body = {"contents": [{"parts": [{"text": PROMPT + "\nDOCUMENT:\n" + doc_text}]}],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json"}}
    models = [MODEL] + [m.strip() for m in FALLBACKS.split(",") if m.strip()]
    last = ""
    for model in models:
        for attempt in range(5):
            try:
                out = _post(model, body, key)
                text = out["candidates"][0]["content"]["parts"][0]["text"]
                return json.loads(re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip())
            except urllib.error.HTTPError as e:
                last = f"{model}: HTTP {e.code} {e.read().decode('utf-8', 'ignore')[:200]}"
                if e.code in (429, 500, 503, 504):  # temporary: wait and retry
                    wait = 2 ** (attempt + 1)
                    print(f"  {model} busy (HTTP {e.code}), retry {attempt + 1}/5 in {wait}s...", flush=True)
                    time.sleep(wait)
                    continue
                print(f"  {model} not usable (HTTP {e.code}), trying next model...", flush=True)
                break  # 400/403/404: retrying this model will not help
            except (urllib.error.URLError, TimeoutError) as e:
                last = f"{model}: network error {e}"
                time.sleep(2 ** (attempt + 1))
        print(f"  giving up on {model}", flush=True)
    sys.exit(f"All models failed. Last error: {last}\nTry again in a few minutes, or set GEMINI_MODEL / GEMINI_FALLBACKS.")


def collapse(s):
    return re.sub(r"\s+", " ", n(s)).strip()


def extract_llm(path, call=call_gemini):
    raw = n(path.read_text(encoding="utf-8"))
    P = PAT["hi" if re.search(r"[\u0900-\u097F]", raw) else "en"]
    ocr, pages, page, body = None, {}, 1, []
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("#OCR"):
            ocr = float(re.search(r"engine_conf=([\d.]+)", line).group(1))
            continue
        m = re.fullmatch(r"\[Page (\d+)\]", line)
        if m:
            page = int(m.group(1))
        else:
            pages[page] = pages.get(page, "") + " " + line
        body.append(line)
    pages = {k: collapse(v) for k, v in pages.items()}
    m = rx(P["ref"]).search(raw)
    ref = m.group(1).rstrip(".,;") if m else path.name
    src = f"synthetic:{path.name}"
    answer = call(raw)
    (path.parent.parent.parent / "output").mkdir(exist_ok=True)
    (path.parent.parent.parent / "output" / f"llm_raw_{path.stem}.json").write_text(
        json.dumps(answer, ensure_ascii=False, indent=2), encoding="utf-8")  # audit trail of what the model said

    def locate(text):  # page where text appears verbatim, or None
        t = collapse(text)
        return next((pg for pg, body_ in pages.items() if t and t in body_), None)

    recs = []

    def record(field, value, quote, pg, where, conf, note=""):
        ok = value not in (None, [], "")
        if ok and ocr:
            conf = round(conf * ocr, 2)
        recs.append({"scheme_ref": ref, "field": field, "value": value if ok else None,
                     "evidence": {"text": quote, "location": f"Page {pg}, {where}", "source": src,
                                  "captured_at": TODAY} if ok else None,
                     "confidence": conf if ok else None, "status": "found" if ok else "not found",
                     "note": note or ("" if ok else "Not present in the document.")})

    for f in FIELDS:
        item = answer.get(f) or {}
        value, quote, why = item.get("value"), item.get("quote"), item.get("reason") or ""
        if value in (None, "", []):
            record(f, None, None, None, None, 0, f"Model found nothing. {why}".strip())
            continue
        reject = lambda msg: record(f, None, None, None, None, 0, f"Model proposed {value!r} but {msg} Rejected; check the source by hand.")
        if f in ("eligibility", "documents_required"):
            bad = [i for i in value if not locate(i)]
            if bad:
                reject(f"these items are not word-for-word in the document: {bad}.")
                continue
            record(f, value, "\n".join(value), locate(value[0]), "section list", 0.9)
            continue
        pg = locate(quote) if quote else None
        if pg is None:
            reject("its quote is not word-for-word in the document.")
            continue
        q, note, conf = collapse(quote), "", 0.9
        if f == "benefit_amount":
            toks = re.findall(r"[\dOo][\dOo,]*", q)
            cleaned = [t.upper().replace("O", "0").replace(",", "") for t in toks]
            if str(value) not in cleaned:
                reject("that number does not appear in its quote.")
                continue
            if any("O" in t.upper() for t in toks if t.upper().replace("O", "0").replace(",", "") == str(value)):
                conf, note = 0.65, "OCR correction applied (letter O read as zero). Check against the scan."
        elif f == "deadline":
            m = re.search(r"(\d{1,2})\s+(\S+)\s+(\d{4})", q)
            if not m or parse_date(m.group(0)) != value:
                reject("the date in its quote cannot be read as that date.")
                continue
        elif f in ("benefit_type", "benefit_frequency"):
            conf, note = 0.8, "Label inferred by the model from the quoted sentence."
        elif f in ("scheme_name", "department", "official_link"):
            if collapse(str(value)).lower() not in q.lower():
                reject("that value is not inside its quote.")
                continue
        record(f, value, quote, pg, "quoted text", conf, note)
    return ref, path.name, recs
