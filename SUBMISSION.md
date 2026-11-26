# Vestigium — project description (Devpost draft)

**Tagline:** Check every transfer in an ownership chain against the evidence it needed at the time, and show exactly where it breaks.

## The use case

Before money changes hands on a property or a vehicle, someone has to be sure the seller could actually sell. Defects hide in the connections between records:
a deed signed under a power of attorney that expired the month before, a lien that was never released, a seller who was never the previous buyer, a salvage brand dropped from a later title.
A reader skimming the documents tends to call such a chain "clean". Vestigium reconstructs the history, checks every transfer, and shows the broken link together with the record that proves it.

All data is synthetic, with a fictional jurisdiction and generic rules. It is not legal advice.

## What connects to what (effective use of connected context)

Ownership, claims and authority live in **one Relate graph**: `Asset`, `Party`, `Transfer`, `Claim`, `Authority`, `Document` and `Passage` nodes, linked by relationships such as
`FROM`, `TO`, `MOVES`, `FOLLOWS`, `AGAINST`, `CLEARED_BY`, `ACTED_UNDER` and `EVIDENCED_BY`. Each fact carries two dates, when it took effect and when it was recorded, so the engine can answer both
"was this valid on March 15?" and "what did we know on March 15?".

A **deterministic rule engine** (named Cypher checks with rule IDs) reaches every verdict: **clean**, **defective** (rule, transfer, evidence) or **inconclusive** (lists each missing record, accuses no one).
An **AI agent** investigates the graph, calls the checks and explains the result, and never decides legality itself. Every finding follows one trail: verdict → rule ID → graph path → evidence → exact document passage.

## Standout features

- **What would fix it.** The engine copies the graph into a throwaway Relate instance, adds a hypothetical record (a release, a ratifying authority, a missing link), reruns every check, and reports which record turns the verdict clean.
- **Two-date replay and verdict timeline.** Slide the known-as-of date and watch the verdict change, for example clean until a late-recorded record arrives.
- **Minimal proof.** Every finding comes with the smallest set of records it truly rests on, found by deleting facts until none can go: on average 1.8 records out of a 10-record dossier. It also audited our own citations and caught 33 incomplete ones, now fixed and tested.
- **Honest inconclusive verdicts.** A gap or missing document stops a check from deciding, and the answer names the missing record instead of guessing.
- **Real records.** The unchanged engine checked 90 real NYC deeds (public ACRIS register, 36 lots): 34 clean, 2 flagged, and by hand one flag was a surname spelling variant and the other a genuine inconsistency in the register. One deed in eight took over three months to be recorded, which is what the two-date model is for.
- **Scanned documents.** Upload a PDF or phone photo; a vision model transcribes it (stamps and handwritten notes included) and reports how sure it is. If a verdict rests on a record read with low confidence, the answer says which page to check. The model's own confidence turned out unreliable (it flagged none of its misreads), so every scan is now read twice and any record where the two reads disagree is flagged. Benchmarked on synthetic scans (40 held-out cases per tier): clean PDFs and phone photos 100% correct; poor photos 95–97.5% across two runs, with the double read catching 2–3 of 5 misreads at about 1 in 40 false alarms. A misread both reads share is still missed, and in one of the two runs that produced a defective chain called clean, so bad photos are not safe yet.
- **An overview page.** `demo/index.html` explains the problem, the five-step pipeline, the two-date idea and the benchmark with live, animated examples; the app is `demo/app.html`.
- **Paste a dossier.** Paste deeds, titles, liens and powers of attorney in any wording; a reader extracts the facts, the rule engine decides, and the same proof trail appears. On messy wording a pattern-matching reader gets 17.5% right and Gemini gets 100% (held-out, 3 repeats), and nothing unreadable is ever called clean.
- **MCP server.** Any MCP client (Claude Desktop, Claude Code) can call the engine: its own model reads the documents, our deterministic engine decides, and every cited record comes back with its exact text.
- **Side-by-side race.** A document-only agent next to the rule-backed agent, from recorded runs.

## Does the graph help? A benchmark, with the losses reported

80 synthetic cases (60 property, 20 vehicle) from a fixed seed, with the planted errors published in `answer_key.json`. On the 40 held-out cases, four arms use the same model and the same evidence:

| Arm | Accuracy | Defective chains called clean |
|---|---|---|
| A: documents only | 55.8% | 34.7% |
| B: graph, agent writes its own Cypher (3 repeats) | 54.2% | 33.3% |
| C: graph + rule-engine tools (3 repeats) | 100% | 0% |
| D: rule engine alone (3 repeats) | 100% | 0% |

A graph by itself did not help; connected context plus deterministic checks did. We say plainly that the rules and the generator were written together (so 100% is a ceiling, not a real-world claim,
which is why Arm D exists), that Arm B is noisy (47.5% to 62.5% across its three repeats), that the held-out split is a flag, not a time gap. The generator, answer key, raw answers for every run, full transcripts for 12 showcase cases and a one-command rerun are in the repo.

## How we built it

Relate's embedded Cypher engine (`relate-db`) holds the graph; the demo store is a single persistent file, `vestigium.rl`, that judges can open directly. Single-file mode needs no server, and each benchmark case gets
its own isolated in-memory graph. The rule engine, generator and benchmark harness are Python; the UI is a static page over exported data. Gemini (`gemini-3.5-flash-lite`) powers the agent arms, and the project was built with Claude Code.

## Challenges

Free-tier API quotas shaped the benchmark: we paced requests, rotated keys, wrote our own tool loop so every call is counted and capped, and made runs resumable. Testing the harness also caught a bug that would have hidden every tool's
parameters from the model and unfairly hurt Arm B, which is the kind of error a benchmark has to find before it publishes a number.

## What's next

Read scanned and PDF documents (the extraction stage is scored on synthetic text only), run the held-out set with more repeats and a stronger model, and run the whole demo in the browser with Relate's WebAssembly build.

**Built with:** Relate (Neo4j), Python, Cypher, Google Gemini, Claude Code
