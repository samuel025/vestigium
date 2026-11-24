# Vestigium

**Evidence-backed ownership investigation, on Relate.** Vestigium rebuilds the history of an asset (a property or a vehicle),
checks whether every transfer had the ownership and authority evidence it needed *at the time*, and shows exactly where the
chain breaks, which record proves it, and what missing record would resolve any doubt.

> All data is **synthetic**: fictional parties, a fictional jurisdiction, generic rules. Nothing here is real or legal advice.

A deterministic rule engine (Cypher checks) reaches every verdict. An AI agent investigates the graph, calls the checks and explains
the result, so it never invents legal reasoning. A benchmark compares document-only agents against graph-backed ones.

## Why Relate, and why single-file mode

Ownership is a chain of *relationships*: who gave up the asset, who received it, what authority the signer had, which claim was open.
Checks like "was the grantor the previous grantee?" or "was a lien released before this sale?" are graph patterns, so they are short Cypher queries
on Relate. We store the demo graph in single-file mode, `vestigium.rl`: it is persistent, one file a judge can open and inspect, and
needs no server. Each benchmark case is built in its own in-memory Relate graph, so every case is isolated, and the
"what would fix it" check copies a graph into a throwaway instance to rehearse a hypothetical record.

## Setup

```bash
git clone <this repo> && cd vestigium
uv sync                                   # installs relate-db (Relate's Python package) and google-genai
cp .env.example .env                      # only needed for the LLM arms (A, B, C); add GEMINI_API_KEY
uv run pytest -q                          # 9 tests: engine matches the answer key on all 80 cases
uv run python -m vestigium.build_store    # writes vestigium.rl and answer_key.json
```

Inspect the persistent store with any Relate client (Python shown; the `relate` CLI works too):

```python
import relate; db = relate.connect("vestigium.rl")
db.execute("MATCH (t:Transfer)-[:ACTED_UNDER]->(a:Authority) RETURN t.id, a.agent, a.valid_to").data()
```

Run the investigation on one case, or open the UI:

```bash
uv run python -m vestigium.cli prop-014                  # verdict, rule, evidence, fix, verdict timeline
cd demo && python3 -m http.server 8000                   # then open http://127.0.0.1:8000/index.html  (?case=veh-003 to jump)
```

Everything runs offline except the LLM arms. The demo UI is a static page over exported data (`demo/data.js`).

## What it does

| | |
|---|---|
| **Verdicts** | `clean`, `defective` (names the rule and the evidence), or `inconclusive` (lists each missing record, accuses no one). |
| **Evidence trail** | verdict → rule ID → graph path → evidence → exact document passage. |
| **Two dates** | every check takes *valid-as-of* and *known-as-of*, so a chain is replayed as it was true and as it was known (the replay slider). |
| **What would fix it** | copy the graph, add a hypothetical record (a release, a ratifying authority, a missing link), rerun every check, report whether it turns clean. |
| **Verdict timeline** | verdict across known-as-of dates, e.g. clean until a late-recorded deed arrives. |
| **Race panel** | recorded runs of the document-only agent next to the rule-backed agent. |

**Rule packs** (`vestigium/rules.py`): *Property* — PROP-CHAIN, PROP-DUP, PROP-LIEN, PROP-AUTH, PROP-DATE, PROP-DEATH, PROP-GAP, PROP-AUTH-MISSING.
*Vehicle* — VEH-OWN, VEH-LIEN, VEH-BRAND, VEH-ODO, VEH-GAP, VEH-ODO-MISSING. Gap rules produce the *inconclusive* verdict; the rest produce *defective*.

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

### Results (held-out, 40 cases)

| Arm | Repeats | Accuracy (mean ± spread) | False-clean¹ | Abstains correctly | Localizes defect | Fix type | Tokens / case |
|---|---|---|---|---|---|---|---|
| A: documents only | 3 | 55.8% ± 1.2 | 34.7% ± 1.9 | 14% | 0% | 27% | 606 |
| B: graph + own Cypher | **1** | 52.5% | 32.0% | 0% | 44% | 47% | 19,263 |
| C: graph + rule tools | 3 | 100% ± 0 | 0% | 100% | 100% | 100% | 2,486 |
| D: rules alone | 3 | 100% ± 0 | 0% | 100% | 100% | 100% | 0 |

¹ share of *defective* cases called clean, the worst error. Spread is the standard deviation of per-repeat accuracy. Citation validity: A 92%, B 90%, C 100%, D 100%.
Property and vehicle show the same pattern (A 55% / 57%, B 60% / 45%, C and D 100% / 100%). Raw answers, tool calls and tokens for every run are in `results/heldout.jsonl`.

**Reading it:** a graph by itself did not help (B is no better than A, at ~30× the tokens). Giving the agent the rule engine's checks did (A 56% → C 100%, false-clean 35% → 0%),
and it did so in every repeat. C matches D on every verdict; the agent's contribution is investigation and explanation, which this benchmark does not score.

### Limitations — please read

- **Arm B has one repeat, the others three.** Gemini's free-tier daily quota made B (about 12.6 requests per case) too expensive to repeat; its spread is unknown. Rerun with
  `./run_benchmark.sh` (`REPEATS=3`); it resumes and fills the gaps. One C case (prop-011) failed on a malformed answer in the first run; we removed that row, added a JSON repair retry to the harness
  and reran it (correct in all 3 repeats). Across the 120 C runs the repair retry fired once (prop-050, repeat 3) and the repaired answer was correct.
- **Small sample.** 40 cases (3 inconclusive and 4 clean per pack-side are few), one model, so the percentages for A and B are rough.
- **The rules and the generator were written together by the same people.** 100% for C and D is expected and is not evidence the rules are right for the real world. Arm D exists to show this: it is the ceiling of the rules themselves, and it is the agent-free baseline.
- **The held-out split is a flag, not a time gap.** Every third case is marked held-out and not used to tune; cases were not written after a rule freeze.
- **One small model.** A stronger model might narrow the gap for A and B.
- **Not scored yet:** the graph-extraction stage (documents → graph), which the evaluation assumes correct, and per-case fix-by-copy accuracy for agent-proposed records
  (we score the *type* of record the agent names against the answer key; each answer-key fix is separately verified to turn its case clean).
- **Single-file Relate store only for the demo;** benchmark graphs are in-memory per case.
- Not built: running Relate in the browser (WASM), serving the store over MCP (`relate serve`), a document-upload UI.

## Layout

```
vestigium/rules.py       rule packs (Cypher)        vestigium/generator.py  seeded case generator + answer key
vestigium/engine.py      load graph, run checks     vestigium/whatif.py     "what would fix it"
vestigium/arms.py        benchmark arms A–D         vestigium/bench.py      scoring + report (resumable)
vestigium/llm.py         Gemini wrapper, key rotation, pacing, hand-written tool loop
demo/                    static UI                  results/heldout.jsonl   raw answers, tool calls, tokens per run
vestigium.rl             persistent Relate store    answer_key.json         planted errors for all 80 cases
```

## Product capabilities, third-party and AI tools

- **Product:** deterministic ownership-chain checks, evidence-cited verdicts, replay by two dates, what-would-fix-it, verdict timeline, benchmark harness, static UI.
- **Third-party:** Relate (`relate-db`, embedded Cypher graph database), `google-genai`, `pytest`, `uv`.
- **AI tools:** Google Gemini (`gemini-3.5-flash-lite`) powers benchmark Arms A–C. The project was built with Claude Code (Anthropic) as the coding assistant.
