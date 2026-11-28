# Benchmark: does the graph help?

The full benchmark write-up: the 80-case benchmark, the 40-case hard tier written after a rule freeze, the robustness checks, and every limitation we know of.

[← back to the README](../README.md)

## Benchmark

80 synthetic cases from a fixed seed (`vestigium/generator.py`): **60 property** (40 defective incl. 5 adversarial, 10 clean, 10 inconclusive) and
**20 vehicle** (12 defective, 4 clean, 4 inconclusive). Chains run 3–12 transfers with distractor documents; the hard tier includes expired powers of attorney
and a misleading "title is clear" summary. Every third property case plus all vehicle cases (**40**) are the **held-out** set that the headline numbers use.
The answer key is `answer_key.json`; the planted error for each case is listed there.

Four arms, same evidence, same model (`gemini-3.5-flash-lite`, temperature 0.2):

- **A** original documents only, no graph.
- **B** documents as a Relate graph; the agent writes its own read-only Cypher.
- **C** the full system: Relate graph + the rule engine's checks as tools.
- **D** the rule engine alone, no agent.

## Results (held-out, 40 cases)

| Arm | Repeats | Accuracy (mean ± spread) | False-clean¹ | Abstains correctly | Localizes defect | Fix type | Tokens / case |
|---|---|---|---|---|---|---|---|
| A: documents only | 3 | 55.8% ± 1.2 | 34.7% ± 1.9 | 14% | 0% | 27% | 606 |
| B: graph + own Cypher | 3 | 54.2% ± 6.2 | 33.3% ± 11.5 | 5% | 46% | 64% | 23,369 |
| C: graph + rule tools | 3 | 100% ± 0 | 0% | 100% | 100% | 100% | 2,486 |
| D: rules alone | 3 | 100% ± 0 | 0% | 100% | 100% | 100% | 0 |

¹ share of *defective* cases called clean, the worst error. Spread is the standard deviation of per-repeat accuracy. Citation validity: A 92%, B 87%, C 100%, D 100%.
Property and vehicle show the same pattern (A 55% / 57%, B 58% / 50%, C and D 100% / 100%). Raw answers, tool-call counts and tokens for every run are in `results/heldout.jsonl`; full transcripts (every tool call, its arguments and result) are recorded for 12 showcase cases in `results/traces.jsonl`.

**Reading it:** a graph by itself did not help (B is no better than A, at ~39× the tokens, and swings from 47.5% to 62.5% between repeats). Giving the agent the rule engine's checks did (A 56% → C 100%, false-clean 35% → 0%),
and it did so in every repeat. C matches D on every verdict; the agent's contribution is investigation and explanation, which this benchmark does not score.

## The hard tier (40 more held-out cases, written after a rule freeze)

We froze the rules first (`results/rules_frozen.json`, commit `c1f06c0`, before any hard case existed); `bench.py` refuses to score this tier if `rules.py` or `engine.py` change. The 40 cases (`generator.hard_cases()`): **8** chains with two defects, **8** sound chains that look suspicious (released liens, valid agents, a deed filed months late, a false rumour in the paperwork), **6** missing records under a "title is clear" summary, **6** powers of attorney valid on the date but not covering a sale, **6** contradictory records filed on different dates, and **6** defects at T2 or T3 followed by a long run of clean-looking sales. Same model (`gemini-3.5-flash-lite`), same evidence.

| Arm | Runs | Accuracy | Defective called clean | Abstains correctly | Localizes¹ | Fix type | Citations valid | Tokens / case |
|---|---|---|---|---|---|---|---|---|
| A: documents only | 3 × 40 | 72.5% (identical in all 3 repeats) | 15.4% | **0%** | 0% | 55% | 98% | 721 |
| B: graph + own Cypher | 3 × 40 | 48.3% (52.5%, 50%, 42.5%) | 47.4% | 11% | 47% | 59% | 79% | 21,857 |
| C: graph + rule tools | 3 × 40 | **100%** (every repeat) | **0%** | **100%** | 100% | 89% | 100% | 3,805 |
| D: rules alone | 1 × 40 | 100% | 0% | 100% | 100% | 100% | 100% | 0 |

| Kind of case | A | B | C | D |
|---|---|---|---|---|
| Two defects in one chain | 75% | 54% | 100% | 100% |
| Sound chain that looks suspicious | 88% | 79% | 100% | 100% |
| Missing record under "title is clear" | **0%** | 11% | 100% | 100% |
| Power valid but not covering a sale | 100% | 28% | 100% | 100% |
| Contradictory records, different filing dates | 100% | 67% | 100% | 100% |
| Early defect, then a long clean run | 67% | 39% | 100% | 100% |

¹ Arm A sees only the documents, which cite passage ids (`P5`) and never transfer ids (`T5`), so it cannot name the transfer by construction; this is the same in the main table.

**Reading it.** The sharpest result: shown a chain with a missing record and a summary saying the title is clear, the documents-only agent answered **clean all 18 times**. The agent with the rule engine abstained every time and named the missing record. Writing its own Cypher did not rescue the agent either (48.3% over 3 repeats, at 30 times the tokens of A, and it called 47% of defective chains clean). Documents alone did well where the defect is stated in plain words (a power "authorising the management only"), which is fair to report. The usual caveat holds: the rules and the cases have one author, so C and D at 100% show the engine doing what its rules say, not that the rules are right for any real jurisdiction; the freeze makes sure the rules were not adjusted to these cases. B ran 3 times like A and C (about 12 model calls per case). Raw runs: `results/hard.jsonl`.

## Cases written by an independent author

Every case above was written by the same people who wrote the rules. To stop grading our own homework, a different model (`gemini-3.6-flash`; we wanted Gemma, another model family, but it was overloaded on the day) wrote **48 property files** from a one-line, plain-English description of each of 12 situations ("one sale was signed by an agent whose power of attorney only allowed managing and renting the property"). The author never saw our rules, generator, record wording or graph schema; it chose its own document formats, date styles, abbreviations, irrelevant paperwork and "title is clear" cover letters. The answer key comes from the situation, not from our engine (`vestigium/indep.py`).

- **A**, a documents-only agent (`gemini-3.5-flash-lite`), reads each file and answers, 3 repeats.
- **V** is Vestigium end to end: our Gemini reader turns the prose into graph facts and the frozen rules decide (once per case; the rules are deterministic).

| | A: documents only (3 × 48) | V: Vestigium (48) |
|---|---|---|
| Accuracy | 84.0% | **95.8%** |
| Defective chains called clean | 12.5% | **0%** |
| Abstains when a record is missing | 87.5% | **100%** |
| Unreleased mortgage | **0%** | 100% |
| Seller who never owned it | 50% | 75% |
| Every power-of-attorney situation, sold twice, dead seller | 100% | 100% |

**Every disagreement, audited by hand.** V disagreed with the answer key twice:
1. `ind-clean-1`, **our error.** The file names the buyer "Wm. H. Vance" in one deed and "William H. Vance" in the next; the name matcher does not expand abbreviations, so the chain rule raised a false alarm. We have not fixed it, because a fix made after seeing the test would make this number meaningless; any later fix will be reported as made after the test.
2. `ind-not-owner-2`, **the answer key is debatable.** The author left out the deed the unauthorised seller claimed to have acquired through, so the file shows a gap rather than a proven non-owner. Vestigium answered *inconclusive* and named the missing deed; we count it as wrong anyway.

One V run failed on a network error and passed on retry; nothing else was rerun. Cases: `results/indep_cases.jsonl`; runs: `results/indep_runs.jsonl`; summary: `results/indep_report.json`.

## Robustness checks (no LLM, no answer key needed for the first two)

Because the rules and the generator were written together, we also test the rule engine on its own (`vestigium/metamorphic.py`, `tests/test_metamorphic.py`, run the big sweep with `uv run python -m vestigium.metamorphic`):

- **Invariance:** for every case we shuffle record order, rename every id, rename every party, shift every date by a constant, and add unrelated records (including a second, broken asset). The verdict, the rule that fired, the transfer and the cited passages must not change. **1,440 checks on 240 fresh cases: 0 failures** (plus 480 on the 80 benchmark cases).
- **Fresh seeds:** 20 new generator seeds (**1,600 cases** the rules were never tuned on) must match the planted labels. **0 failures.**

These tests found two real problems, now fixed, which is why they are worth running:
1. `PROP-DUP` picked "the duplicate" by string order of ids, so with arbitrary real-world ids it could blame the wrong transfer. It now uses the effective and recorded dates (id is only the final tie-break).
2. In 2 of 1,600 fresh cases the generator chose an `as_of` earlier than a planted record's recorded date, so the engine, correctly, could not know about it yet. The generator now judges with full knowledge. Existing benchmark cases are unchanged.

What this does *not* show: that the rules are right for any real jurisdiction. It shows the engine is deterministic, order- and name-independent, and does what its rules say.

## Limitations — please read

- **Arm B is noisy.** Its three repeats scored 52.5%, 62.5% and 47.5%, so its spread is wide; the free-tier quota meant B (about 12.6 requests per case) took two days to finish. Rerun with
  `./run_benchmark.sh` (`REPEATS=3`); it resumes and fills the gaps. One C case (prop-011) failed on a malformed answer in the first run; we removed that row, added a JSON repair retry to the harness
  and reran it (correct in all 3 repeats). Across the 120 C runs the repair retry fired once (prop-050, repeat 3) and the repaired answer was correct.
- **Small samples.** 40 held-out cases in the main benchmark (3 inconclusive and 4 clean per pack-side are few) and 40 in the hard tier, one model, so the percentages for A and B are rough.
- **Real-record check, blind:** the chain rule was also measured on 150 real Philadelphia links against blind human labels (recall 100%, precision 60%, every false alarm a register typo; see [real records](real-records.md#a-benchmark-on-real-records-against-blind-human-labels)).
- **The rules and the generator were written together by the same people.** 100% for C and D is expected and is not evidence the rules are right for the real world. Arm D exists to show this: it is the ceiling of the rules themselves, and it is the agent-free baseline. The [independent-author test](#cases-written-by-an-independent-author) addresses this (95.8%, 0 defective chains called clean); its author was another Gemini model, not another model family, and it has 48 cases.
- **The real-record test is deeds-only** (30,803 deeds, two cities, see *Real records*); it shows how the rules behave on real data, not whether any flagged property has a real defect. Everything else is synthetic.
- **The original held-out split is a flag, not a time gap.** Every third of the 80 cases is marked held-out and not used to tune, but those cases were not written after a rule freeze. The 40-case **hard tier** was: the rules were frozen first (`results/rules_frozen.json`) and the benchmark refuses to score it against changed rules.
- **One small model.** A stronger model might narrow the gap for A and B.
- **Arms A-D assume a correct graph.** Extraction is scored separately (section above), not chained into the four-arm table. Not scored: per-case fix-by-copy accuracy for agent-proposed records
  (we score the *type* of record the agent names against the answer key; each answer-key fix is separately verified to turn its case clean).
- **The graph lab's edge removal is limited** to `FOLLOWS`, `ACTED_UNDER`, `CLEARED_BY`, `GRANTED_BY` and `REVOKED_BY` (the relationships the rules can notice); outcomes are precomputed for every demo and real case, and editing or running your own Cypher, or removing from a pasted dossier, needs the local server. Custom queries run on a throwaway Relate store opened with `read_only=True`, so Relate itself refuses any write (tested).
- **Single-file Relate store only for the demo;** benchmark graphs are in-memory per case.
- **Scans are tested on synthetic photos only.** The model's own confidence flags were unreliable; the double read catches 3 of 5 poor-photo misreads, not all (see *Scanned documents*).
- Not built: running Relate in the browser (WASM), Relate's own `relate serve` MCP endpoint for the `.rl` store (our MCP server exposes the rule engine instead), Google Document AI or AWS Textract (we use a vision model).
