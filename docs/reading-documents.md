# Reading documents: paste, PDFs and photos

How documents become graph facts (the reader copies, the rules decide), how well that works on messy wording and on scans, and the double read that catches misreads a model is confident about.

[← back to the README](../README.md)

## Paste a dossier: reading documents into the graph

The UI's **Paste a dossier** box takes deeds, titles, liens, powers of attorney, releases and death certificates, extracts the facts, and hands them to the same rule engine
(`vestigium/intake.py`, `extract.py`, `dossier.py`). The reader only *reads*: it never decides legality, every verdict still comes from the rules, and the extracted facts are listed
so a person can check them. Nothing that could not be read is called clean: an empty chain is *inconclusive* ("no ownership records could be read").

We score this stage too (`vestigium/intake_bench.py`, held-out 40 cases, 3 repeats). Dossiers are rendered from the gold graph with every fact stated in text; "messy" wording varies date formats,
abbreviates names ("G. Stone") and shuffles record order. The reader's output is rebuilt into a graph, the engine judges it, and the result is compared with the gold graph.

| Reader | Wording | Verdict accuracy | Defective called clean | Right finding at the right record | Records read exactly |
|---|---|---|---|---|---|
| Offline regex | canonical | 100% | 0% | 100% | 100% |
| Offline regex | messy | 17.5% | 2.7% | 2.5% | 5.4% |
| Gemini (`gemini-3.5-flash-lite`) | canonical | 100% | 0% | 100% | 100% |
| Gemini | messy | 100% | 0% | 100% | 99.6% |

What to take from it: wording variety breaks a pattern-matching reader, and a language model recovers it, with the rule engine still making the call. Honest caveats: the dossiers are synthetic and generated from the same
schema, so real scanned deeds would be harder (OCR noise, free-form clauses); a name that is only ever abbreviated in a dossier stays abbreviated, which is correct to copy and the scorer accepts.
We changed the extraction prompt once after seeing results on this same held-out set (the first prompt let the model invent a first name for "N. Stone", which wrongly broke 2 of 120 messy runs; we now tell it to copy
names exactly and let code match abbreviations). The first run is kept in `results/intake_v1_prompt.jsonl` (98.3% messy verdict accuracy). Raw runs, including each extracted record list, are in `results/intake.jsonl`.

## Scanned documents: PDFs and photos

Nobody types out a 20-page deed. The upload box (and `POST /api/scan`) accepts PDFs and JPEG, PNG or WebP photos (`vestigium/scan.py`). Stage 1 is a vision model that transcribes each page record by record, including clerk's stamps and handwritten notes, and reports a **confidence** (high, medium or low) with *what* it is unsure about. It copies; it never judges. Stage 2 sends the transcript through the same reader, graph and rule engine.

**Confidence is carried into the verdict.** If a finding rests on a record that was read with low confidence, the verdict card says which record and page to check against the original, instead of guessing silently. A CLEAN verdict with low-confidence records is warned about too, not presented as safe, and low confidence on an irrelevant record does not raise a false alarm. A record that looks like a deed or lien but cannot be parsed is never silently dropped: the verdict becomes *inconclusive* and names the unreadable record.

How we test it: `render_scan()` makes synthetic scans from our dossiers, in three tiers (a clean PDF, a phone photo with rotation, uneven lighting, blur and JPEG damage, and a poor photo), with the recording date appearing *only* as a red stamp or a handwriting-style note, as on a real recorded deed. "Try a sample phone photo" in the app renders one and reads it.

**Double read.** A model's own confidence proved unreliable on poor photos (below), so every scan is read **twice**: the second, independent read lists only each record's dates and names, and code compares the two. Any record where they disagree is marked low confidence, whatever the model said, and the verdict names the record and page to check. It is deterministic and does not depend on the model knowing it is wrong.

**Results** (`uv run python -m vestigium.scan_bench`, held-out 40 cases per tier, `gemini-3.5-flash-lite` for vision; raw rows in `results/scan_x2/` with the double read and `results/scan_lite/` with a single read):

| Tier | Verdict accuracy | Defective called clean | Right finding at the right record | Records with every date read exactly | Misreads flagged | Correct records flagged (false alarms) | Wrong verdicts with no warning |
|---|---|---|---|---|---|---|---|
| Clean PDF | 100% | 0% | 100% | 99.8% | 0 of 1 | 1 of 401 | 0 |
| Phone photo | 100% | 0% | 100% | 99.8% | 0 of 1 | 3 of 401 | 0 |
| Poor photo | 95.0% | **0%** | 87.5% | 98.8% | **3 of 5** | 10 of 397 | 2 |
| Poor photo, re-run after the reader fix below | 97.5% | 4.0% (1 case) | 92.5% | 98.8% | 2 of 5 | 9 of 397 | 1 |
| *Poor photo, single read* | *90.0%* | *4.0% (1 case)* | *82.5%* | *99.0%* | *0 of 4* | *–* | *4* |

**What this says, plainly.** Clean PDFs and ordinary phone photos read reliably. On poor photos the model's self-reported confidence caught **none** of its misreads; the double read caught 3 of 5 at the cost of flagging about 1 in 40 correct records, but it is **not a guarantee**: a misread both reads share is not caught. In the re-run, `prop-059` had two dates misread the same way by both reads and was called **clean** with no warning; in the run before, the same case came back defective with a warning. So on poor photos the worst error still happens, about 1 case in 40, and changes from run to run.

**A reader bug the scans exposed.** Two clean poor-photo cases (`prop-017`, `prop-056`) came back *inconclusive* in both earlier runs. No date was misread: the vision model dropped one word, reading "the chain of **title** begins here" as "the chain of begins here", and the offline reader recognised the first transfer only by that exact phrase, so it reported a gap at T1. It now accepts either sentence the record uses ("the first recorded transfer" or "the chain of title begins"), with a test. Both cases are correct in the re-run. This makes the reader tolerant of a lost word in *our* wording; real deeds do not use a fixed sentence, so it is not a general fix. Runs vary: the first read itself differs between runs, so compare the catch rate more than the verdict percentages. An earlier partial run with `gemini-3.5-flash` (33 clean-PDF cases, all correct) is in `results/scan.jsonl`; we switched because that model's free tier allows only 20 requests a day per key. Tested only on synthetic pages: true handwriting, real scanner noise, and dedicated OCR services (Google Document AI, AWS Textract) are untested.
