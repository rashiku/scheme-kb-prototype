# Scheme Knowledge Base: prototype

## Run it (VS Code terminal, Python 3.8+, no installs needed)
```
python extract.py     # offline rules. reads data/docs/*.txt -> output/drafts.json (everything is a DRAFT)
# Gemini version (key stays in your terminal, never in a file):
#   Windows PowerShell:  $env:GEMINI_API_KEY='your-key'     Mac/Linux: export GEMINI_API_KEY='your-key'
#   optional: set GEMINI_MODEL if the default alias 'gemini-flash-latest' is not available to your key
python extract.py --llm
python evaluate.py    # field-by-field accuracy vs data/gold.json
python publish.py status
python publish.py approve AGR/2026/114 --reviewer Asha --resolve benefit_amount=6000 --resolve deadline=2026-12-31
python publish.py export   # output/published.json: approved schemes only
```

## What is in the folder
| File | Purpose |
|---|---|
| data/docs/sample_en.txt | English notification. Disagrees with the MyScheme listing (amount and deadline). |
| data/docs/sample_hi.txt | Hindi notification. No official link printed, so that field must stay empty. |
| data/docs/sample_scan_ocr.txt | Stand-in for a scanned page: noisy OCR text ("1,20,OOO", unreadable date). |
| data/myscheme/myscheme_mksy.json | Synthetic MyScheme listing used to create the conflict. |
| data/gold.json | Answers a person checked by hand (30 fields). Used only for scoring. |
| extract.py / evaluate.py / publish.py | Extraction with evidence, scoring, review gate. |

## Assumptions (and why)
1. **Two extractors, same output format.** Default is offline rules (a fallback you can always demo). `--llm` uses Gemini: the model proposes a value plus an exact quote, and `llm_extract.py` checks the quote appears word-for-word in the document, and that amounts and dates really match their quote. Anything unverifiable is left empty, with the rejected proposal named in the note. The model's raw answer is saved in output/llm_raw_*.json.
2. **The "scan" is simulated OCR text**, with a header line giving engine confidence. Reason: real OCR needs Tesseract plus Hindi language packs installed. In production, OCR runs first and its confidence feeds the same cap used here (field confidence is multiplied by OCR confidence).
3. **Documents have page markers and headings** (`[Page 2]`, "Benefit", "Eligibility"). Reason: keeps evidence locations exact. Real PDFs need a layout-aware parser to produce the same structure.
4. **scheme_ref = notification number**, or the file name when there is none (the scan case). This follows the brief's "ID or source document".
5. **All links are placeholders** (`PLACEHOLDER-LINK: ...`). The brief says not to invent official URLs.
6. **Conflict rule:** any difference between document and MyScheme listing becomes `status: conflict`, with both values and both evidences kept, confidence 0.5. The tool never picks one.
7. **Not found:** value and evidence stay empty and the note says why. Example: the scan's deadline line exists but is unreadable, so it is not guessed.
8. **Gold set** (hand-checked answers) uses the document's value as the truth in the conflict cases, on the assumption that the document is the official source. A programme team may decide otherwise.

## Review gate (requirement 1)
`extract.py` only writes `review_status: draft`. `publish.py approve` needs a named reviewer, refuses while any conflict is unresolved, and a resolution must be one of the kept values (typos are rejected). `export` includes approved schemes only and asserts that every found value has evidence (requirement 2).

## What "field-level accuracy" means (programme-team words)
For each field (benefit amount, deadline, documents list...), out of all schemes: how often did the AI's draft match what a careful person would enter? Counted per field, not per scheme, because a scheme with 9 right fields and a wrong deadline is still unsafe. We report four outcomes: **correct**, **wrong** (a bad value, the dangerous one), **missed** (left empty though the source has it, which only costs reviewer time) and **correctly empty** (nothing to find, and it said so). A wrong amount and a missed amount are not equally bad, so they are never blended into one score.

## How to decide it is good enough before 5,000 schemes
1. Draw a random sample of about 200 schemes, stratified by language, scanned vs digital, and central vs state. Two researchers fill them in by hand; disagreements are settled by a third. That is the gold set.
2. Score per field as above, with a confidence interval, and by stratum (Hindi scans will behave differently from English PDFs).
3. Proposed bar (a starting point for your team to agree, not a standard): **0 confident-but-wrong values on money, deadline and eligibility in the sample; wrong-rate under 2% on every field; missed-rate low enough that review is clearly faster than typing**, measured by timing reviewers on 20 schemes with and without the draft.
4. Fields that miss the bar still go through, but with mandatory review and no auto-approve. Re-run the same score after every prompt or model change.

## A senior researcher says the AI got an amount wrong, but it matches the PDF. What next?
1. Do not defend the AI or dismiss the researcher. Ask where their number came from and open both sources side by side.
2. Find which of four things happened: (a) the researcher is reading a newer or different document (amendment, corrigendum, state vs central version); (b) the PDF itself is wrong or outdated versus the department website or MyScheme (then it should have been a conflict, so check why it was not flagged); (c) the amount is context-dependent (per instalment vs total, per year vs one-time) and the field definition is ambiguous; (d) the AI really is wrong and the match was luck.
3. Record the outcome in the gold set as a new test case, with the source for each side.
4. Fix the cause: a missed-conflict detection rule, a clearer field definition, or a note on the record. Re-run the accuracy score to confirm nothing else regressed.
5. Tell the researcher what was found. If the PDF was stale, the evidence trail is what exposed it.

## Honest limits
- 3 schemes and 30 fields demonstrate the method. The 97% figure means nothing about 5,000 schemes.
- The rules fit these synthetic layouts; real government PDFs are messier. That is why the evaluation step exists.

- The Gemini path was tested only against a mock model (it correctly rejected a paraphrased quote, a number not in its quote, and a guessed date from an unreadable scan). It has not been run against the live Gemini API from where I built it, so run `--llm` once before recording and fix the model name if needed.
- Quote verification proves the text exists in the source. It does not prove the model read the right sentence.
