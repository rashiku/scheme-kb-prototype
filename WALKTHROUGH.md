# 10-minute walkthrough: talking points
Speak from these, don't read them. Record your screen: VS Code terminal plus `output/drafts.json`.
Before recording: run `python extract.py --llm` once to confirm Gemini works, then `python evaluate.py`.

## 0:00-1:00  The problem and the approach
- 5,000 schemes, researchers retyping from PDFs. Risk: a wrong amount or expired deadline reaches a citizen.
- Two rules drive everything: a person approves before anything goes live, and every fact points to its source or stays empty.
- Flow: AI drafts -> every value is checked against the source text -> a person reviews -> only approved schemes are exported.

## 1:00-4:30  Live demo
1. `python extract.py --llm`. Show the table: status, confidence, `<-- CHECK` flags.
2. Open `output/drafts.json`, one record: value, exact quote, page, source, date captured.
3. English scheme: benefit amount and deadline show `conflict` (6,000 vs 5,000). Both values and both sources are kept. Nothing was picked.
4. Hindi scheme: extracted in Hindi, quote in Hindi. Official link is empty with the reason "no link printed".
5. Scan: unreadable deadline left empty, not guessed. OCR-fixed amount ("1,20,OOO") has low confidence and a note.
6. Gate: `python publish.py approve AGR/2026/114 --reviewer Asha` is refused (unresolved conflicts). Then approve with `--resolve ...`, run `export`, show only the approved scheme came out.
7. `python evaluate.py`: show the per-field table.

## 4:30-5:30  1. One decision, and the option I decided against
- Decision: the AI must give an exact quote for every value, and my code checks the quote exists word-for-word in the document. If not, the value is rejected and the field stays empty.
- Decided against: asking the model how confident it is and trusting that number. Model self-reported confidence is not reliable, and a made-up quote looks just as convincing as a real one. A string match is cheap and cannot be argued with.
- Cost I accepted: it will sometimes reject a correct value because the model paraphrased the quote. That shows up as "missed" (reviewer types it in) instead of "wrong" (a bad value reaches a citizen). I chose the safe failure.
- Show the mock-test result if asked: paraphrased quote rejected, number not in its quote rejected, guessed date from unreadable scan rejected.

## 5:30-7:00  2. Where it falls short, and how someone would notice
- Only 3 schemes I wrote myself. The accuracy table proves the method, not performance on 5,000.
- Quote check proves the text exists, not that the model read the right sentence. Example: the right sentence but the wrong amount, such as an income limit instead of a benefit.
- The scan is simulated OCR text, not a real image. Real scans will fail in messier ways.
- Conflicts are only caught when a second source exists. A document that is simply out of date, with no one disagreeing, passes silently.
- How it would be noticed: reviewers' correction rate per field, the confident-but-wrong count on the hand-checked sample, the "missed" rate creeping up (the checker is rejecting too much), and rerunning evaluate after every prompt or model change.

## 7:00-8:00  3. Main assumptions, and why
- Documents have page markers and headings. Reason: keeps evidence locations exact. Real PDFs need layout parsing first.
- scheme_ref = notification number, or the file name when there is none. Matches the brief ("ID or source document").
- Document is treated as the official source in the gold set when it disagrees with MyScheme; the programme team may decide otherwise.
- All links are placeholders. The brief says not to invent real official URLs.
- Gemini used with temperature 0 and JSON output. Model name is configurable.

## 8:00-9:00  4. The "how you work" question
Senior researcher says the amount is wrong, but it matches the PDF. What I do:
1. Don't defend the AI and don't dismiss the researcher. Ask where their number comes from; put both sources side by side.
2. Find the cause: (a) they're looking at a newer or different document (amendment, state vs central version); (b) the PDF is stale versus the website or MyScheme, in which case it should have been flagged as a conflict, so find out why it wasn't; (c) the field is ambiguous (per instalment vs total, per year vs one-time); (d) the AI really was wrong and the match was luck.
3. Add the case to the hand-checked set, with the source for each side.
4. Fix the cause (conflict rule, clearer field definition, or note), re-run the score to check nothing else slipped, and tell the researcher what was found.

## 9:00-10:00  5. What "field-level accuracy" means
- For one field, say benefit amount: across all schemes, how often did the AI's draft match what a careful person would enter?
- Counted per field, not per scheme: a scheme with nine right fields and one wrong deadline is still unsafe.
- Four outcomes: correct, wrong (the dangerous one), missed (empty though the source has it; only costs time), correctly empty.
- Never blend wrong and missed into one score.
- Good enough before 5,000: hand-check about 200 random schemes (mix of Hindi/English, scanned/digital, central/state), proposed bar of zero confident-but-wrong on money, deadline and eligibility, and review measurably faster than typing. Fields that miss the bar keep mandatory review.
