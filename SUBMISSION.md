# Vestigium — project description (Devpost draft)

**Tagline:** Would you buy this property? Vestigium checks every past sale against the evidence it needed at the time, and shows exactly where the chain breaks, what proves it, and who else it affects.

**Live demo:** https://vestigium-demo.vercel.app/ · **Code:** https://github.com/samuel025/vestigium

## The use case

Before money changes hands on a property or a vehicle, someone has to be sure the seller could actually sell. Defects hide in the connections between records:
a deed signed under a power of attorney that expired the month before, a lien that was never released, a seller who was never the previous buyer, a salvage brand dropped from a later title.
A reader skimming the documents tends to call such a chain "clean". Vestigium reconstructs the history, checks every transfer, and shows the broken link together with the record that proves it.

The benchmark data is synthetic, with a fictional jurisdiction and generic rules; the engine is also run on 30,803 real public deeds. It is not legal advice.

## What connects to what (effective use of connected context)

Ownership, claims and authority live in **one Relate graph**: `Asset`, `Party`, `Transfer`, `Claim`, `Authority`, `Document` and `Passage` nodes, linked by relationships such as
`FROM`, `TO`, `MOVES`, `FOLLOWS`, `AGAINST`, `CLEARED_BY`, `ACTED_UNDER`, `GRANTED_BY`, `REVOKED_BY` and `EVIDENCED_BY`. Each fact carries two dates, when it took effect and when it was recorded, so the engine can answer both
"was this valid on March 15?" and "what did we know on March 15?".

A **deterministic rule engine** (named Cypher checks with rule IDs) reaches every verdict: **clean**, **defective** (rule, transfer, evidence) or **inconclusive** (lists each missing record, accuses no one).
An **AI agent** investigates the graph, calls the checks and explains the result, and never decides legality itself. Every finding follows one trail: verdict → rule ID → graph path → evidence → exact document passage.

## Standout features

- **Power of attorney, in depth.** Most broken chains break where someone signs for the owner. Five rules ask a title examiner's questions as graph patterns: was it in force on the signing date, did the *seller* grant it, does it cover *selling*, was it *revoked* (and was the revocation on file yet), and did the named agent actually sign. A ratification by the seller fixes it.
- **What else it breaks.** When a sale fails, every later sale whose chain of title passes through it is marked, by one graph walk.
- **Two kinds of time.** Separate controls for what was legally true on a date and what an investigator could have known from the register on that date, with a verdict grid for every pair.
- **Minimal proof.** Every finding comes with the smallest set of records it truly rests on, found by deleting facts until none can go: on average 1.8 records out of a 10-record dossier. It also audited our own citations and caught 33 incomplete ones, now fixed and tested.
- **What would fix it.** The engine copies the graph into a throwaway Relate instance, adds a hypothetical record (a release, a ratifying authority, a missing link), reruns every check, and reports which record turns the verdict clean.
- **Honest inconclusive verdicts.** A gap or missing document stops a check from deciding, and the answer names the missing record instead of guessing.
- **Real records.** The unchanged engine checked **30,803 real deeds** (about 10,000 properties) from New York's public ACRIS register and Philadelphia's transfer records. 90% of links match; every kind of flag is labelled, from register spelling variants to foreclosures, and about 1 break in 5 has no record anywhere in the public register of how the seller acquired the property. Real data also exposed bugs in our name matching and one impossible date in the register, now handled and tested. All anonymised and browsable in the app's Real tab.
- **Paste a dossier.** Paste deeds, titles, liens and powers of attorney in any wording; a reader extracts the facts, the rule engine decides, and the same proof trail appears. On messy wording a pattern-matching reader gets 17.5% right and Gemini gets 100% (held-out, 3 repeats), and nothing unreadable is ever called clean.
- **Scanned documents.** Upload a PDF or phone photo; a vision model transcribes it (stamps and handwritten notes included) and reports how sure it is. If a verdict rests on a record read with low confidence, the answer says which page to check. The model's own confidence turned out unreliable (it flagged none of its misreads), so every scan is now read twice and any record where the two reads disagree is flagged. Benchmarked on synthetic scans (40 held-out cases per tier): clean PDFs and phone photos 100% correct; poor photos 95–97.5% across two runs, with the double read catching 2–3 of 5 misreads at about 1 in 40 false alarms. A misread both reads share is still missed, and in one of the two runs that produced a defective chain called clean, so bad photos are not safe yet.
- **MCP server.** Any MCP client (Claude Desktop, Claude Code) can call the engine: its own model reads the documents, our deterministic engine decides, and every cited record comes back with its exact text.
- **Side-by-side race.** A document-only agent next to the rule-backed agent, from recorded runs.
- **An overview page.** `demo/index.html` explains the problem, the five-step pipeline, the two-date idea and the benchmark with live, animated examples; the app is `demo/app.html`.
- **Show me the graph.** The app shows each case as the graph Relate holds: every rule's exact Cypher with the rows it returns, a walk along the chain, and *remove a relationship* to watch the verdict change.

## Does the graph help? A benchmark, with the losses reported

80 synthetic cases (60 property, 20 vehicle) from a fixed seed, with the planted errors published in `answer_key.json`. On the 40 held-out cases, four arms use the same model and the same evidence:

| Arm | Accuracy | Defective chains called clean |
|---|---|---|
| A: documents only (3 repeats) | 55.8% | 34.7% |
| B: graph, agent writes its own Cypher (3 repeats) | 54.2% | 33.3% |
| C: graph + rule-engine tools (3 repeats) | 100% | 0% |
| D: rule engine alone (3 repeats) | 100% | 0% |

**A harder tier** of 40 more held-out cases, written only after the rules were frozen (multi-defect chains, sound chains that look suspicious, missing records under a 'title is clear' summary, powers that do not cover a sale, contradictory filings): documents only 72.5%, graph with its own Cypher 50%, graph with the rule engine **100% in all three repeats**. Shown a missing record under a 'title is clear' summary, the documents-only agent said clean 18 times out of 18; the rule-backed agent abstained every time and named the missing record.

A graph by itself did not help; connected context plus deterministic checks did. We say plainly that the rules and the generator were written together (so 100% is a ceiling, not a real-world claim,
which is why Arm D exists), that Arm B is noisy (47.5% to 62.5% across its three repeats), that the original held-out split is a flag, not a time gap (the hard tier is not: its cases were written after the rules were frozen). The generator, answer key, raw answers for every run, full transcripts for 12 showcase cases and a one-command rerun are in the repo.

## How we built it

Relate's embedded Cypher engine (`relate-db`) holds the graph; the demo store is a single persistent file, `vestigium.rl`, that judges can open directly. Single-file mode needs no server, and each benchmark case gets
its own isolated in-memory graph. The rule engine, generator and benchmark harness are Python; the UI is a static page over exported data. Gemini (`gemini-3.5-flash-lite`) powers the agent arms and the readers. Real records come from NYC Open Data (ACRIS) and OpenDataPhilly, anonymised before anything is committed. The project was built with Claude Code.

## Challenges

Free-tier API quotas shaped the benchmark: we paced requests, rotated keys, wrote our own tool loop so every call is counted and capped, and made runs resumable. Testing the harness also caught a bug that would have hidden every tool's
parameters from the model and unfairly hurt Arm B, which is the kind of error a benchmark has to find before it publishes a number.

## What's next

Test scans on real paperwork and true handwriting (so far only synthetic pages), catch the misreads both scan reads share, check liens on real records by linking each satisfaction to its mortgage (ACRIS publishes these references), check liens and authorities on real records too (the real test covers deeds only), add more cities, run the benchmark with a stronger model and more repeats, and run the whole demo in the browser with Relate's WebAssembly build.

**Built with:** Relate (Neo4j), Python, Cypher, Google Gemini, Claude Code
