# Real records: 30,803 deeds from two cities

How the unchanged rule engine behaves on real public property records from New York and Philadelphia, what it flagged, what we checked by hand, and how to reproduce it.

[← back to the README](../README.md)

## Real records: 30,803 deeds from two cities

**In short:** we ran the unchanged rules on about 10,000 real properties. 9 in 10 sales link up cleanly. Most of the rest are explained by ordinary things (a name spelled differently, an estate selling, a foreclosure), and each is labelled. About 1 break in 5 has **no record anywhere in the public register** of how the seller got the property; those are exactly what a person should look into.

Two importers feed real public deeds into the same graph and the **unchanged** rule engine:

- **New York** (`vestigium/acris.py`): NYC ACRIS, the city's register (NYC Open Data). 5 adjacent Brooklyn blocks: 36 lots, 90 deeds, 2003–2026.
- **Philadelphia** (`vestigium/philly.py`): the city's Real Estate Transfer Tax records (OpenDataPhilly, `rtt_summary`). A repeatable pseudo-random sample of **9,999 properties, 30,713 deeds**, all years on record, including sheriff's (foreclosure) deeds.

Each deed brings its two real dates (signed, recorded) and its seller and buyer names.

![The overview page's Real records section](img/real-records.png)

**See it in the app:** the **Real** tab opens all 36 New York lots and 38 Philadelphia properties chosen to show every kind of finding (e.g. `app.html?case=real-8`, `app.html?case=phl-d81620`), anonymised: owners are numbered, no names, addresses or parcel numbers. Each has the same chain view, proof, time travel and graph lab as the synthetic cases, plus a note saying why it was flagged.

| | New York | Philadelphia |
|---|---|---|
| Properties / deeds / seller-to-previous-buyer links | 36 / 90 / 54 | 9,999 / 30,713 / 20,714 |
| Seller matched the previous buyer | 53 of 54 | 18,630 of 20,714 (90%) |
| Verdicts | 35 clean, 1 defective | 8,210 clean, 1,789 defective |
| Deeds recorded more than 90 days after signing | 12 of 90 | 2,560 of 30,666 (443 over a year) |

**What the flags were.** The one New York flag was read by hand: a real register inconsistency (a buyer recorded as an exchange titleholder "...2006-175" sells as "...2007-175"). In Philadelphia the importer sorts each of the 2,202 findings by a stated rule, and for unexplained breaks it searches the **full** register (every document type, multi-property deeds) for a record of how the seller acquired the property:

| Philadelphia finding | Count | In plain words |
|---|---|---|
| Probable spelling variant (85%+ similar) | 617 | The same person or company spelled differently ("KRZSYTOF" / "KRZYSZTOF"). A person confirms; code does not guess |
| No record of how the seller acquired it | 445 | Nothing in the public register gives the property to the seller. This is what a title examiner chases |
| A deed to the seller exists outside our extract | 262 | Our importer only read single-property deeds; the engine correctly said the chain *it was given* was broken |
| Sheriff sale (foreclosure) | 244 | A lawful break the synthetic rules do not model; 144 properties are "defective" only because of one |
| Estate, trust or agent sells | 231 | An executor, trustee or attorney-in-fact signs. Lawful with the right authority, which the register does not hold |
| Related name, different party | 210 | A spouse, relative, co-owner or sister company sells. Usually explainable, but it needs a document |
| Signed before the previous deed was signed | 119 | Recorded out of order (`PROP-DATE`): the order of events is not what the register suggests, or a seller conveyed before acquiring |
| The seller appears only as a borrower | 74 | They took a loan against the property, but no deed to them is on record |

We read random samples by hand (drawn from the first 1,000 properties, which are part of this sample): 20 of the name group (about 15 spelling variants, 5 related parties) and 15 of the unexplained group (1 alias, "Fannie Mae" vs "Federal National Mortgage Association"; 2 a builder or the city; 12 with no acquisition record we could find). The category shares at 1,000 and at 10,000 properties are nearly identical.

**Real data found bugs in our code**, which is why we test on it: names made of single letters ("S E B M INC"), apostrophes ("ROSHA'S" / "ROSHAS") and names cut at the register's 40-character limit did not match themselves, and one deed carries the impossible date "206-05-07". All fixed and tested; the name fixes also cleared New York's one false alarm (a surname written "LA PIERRE" when the couple bought and "LAPIERRE" when they sold). Near-miss spellings are still never accepted automatically.

**What it shows:** the rule engine runs unchanged on 30,803 real deeds in about a minute and a half; its flags fall into a few explainable kinds; and recording delays are common (1 deed in 12 took over three months), so the two-date model matters. **What it does not show:** that any flagged property has an actual title defect (we did not search beyond the public register), or anything about liens: a satisfaction is not linked to its mortgage in the fields we read, and mortgages are routinely satisfied weeks after a sale. Deeds are linked in recorded order because neither register says which earlier deed a seller acquired through.

**Privacy and reproduction.** Raw downloads hold real names and stay in `data/acris_raw/` and `data/philly_raw/` (gitignored); the committed reports (`results/acris_real.json`, `results/philly_real.json`) and the app data (`demo/real.js`) carry no names, addresses or parcel numbers (app ids are one-way hashes). Philadelphia: `uv run python -m vestigium.philly fetch --n 10000` (about 3 minutes, free public API) then `uv run python -m vestigium.philly` (about 5 minutes including the register lookups). New York: fetch the lots from Real Property Legals (e.g. `https://data.cityofnewyork.us/resource/8h5j-fqxa.json?$where=borough=3 AND block between 5200 and 5204&$limit=5000`), then those documents' rows from Master (`bnx9-e6tj`) and the deeds' parties from Parties (`636b-3b5g`) with `$where=document_id in(...)`; save them as `legals.json`, `master.json` (keyed by `document_id`) and `parties.json` in `data/acris_raw/`, and run `uv run python -m vestigium.acris`, which also rebuilds `demo/real.js`. (The NYC API refused our network, so we fetched those pages through Firecrawl's scraper; the data is the same public API response.)


## A benchmark on real records, against blind human labels

The numbers above describe what the engine flags; they cannot say whether a flag is *right*, because no public register publishes an answer key. So a person supplied one.

**Protocol** (`vestigium/real_bench.py`). From the Philadelphia sample, 150 seller-to-previous-buyer links were drawn with a fixed seed: 75 the engine flagged and 75 it accepted, shuffled under neutral ids. A local labelling page (`demo/label.html`, served by `vestigium.serve`) showed only the two real register entries, never the engine's answer (a test checks this), and asked one question: *is the seller of the later deed the same party as the buyer of the earlier one?* Answers: same party · same party, written differently · different party · can't tell. The same question went to Gemini (`gemini-3.5-flash-lite`), one link at a time, also blind. Real names stay in `data/philly_raw/` (gitignored); `results/real_bench.json` holds counts only.

**Labels:** 71 same party, 34 same party written differently, 45 different party, 0 can't tell.

| Against the human labels | Accuracy | Precision | Recall | Breaks missed | False alarms |
|---|---|---|---|---|---|
| Rule engine (stated name matching + `PROP-CHAIN`) | 80.0% | 60.0% | **100%** | **0 of 45** | 30 |
| Gemini reading the names | 93.9% | 86.0% | 95.6% | 2 of 45 | 7 |
| Engine flags, AI may clear a flag it reads as the same party | 96.7% | 93.5% | 95.6% | 2 of 45 | 3 |
| **Engine decides, AI only labels each flag** | 80.0% | 60.0% | **100%** | **0** | 30, **27 labelled "probable spelling variant"** |

**What we found.**
- **The rules never missed a real break.** All 30 false alarms are typos in the register itself ("SEMMELRITH" / "SEMMELROTH", "MANANGEMENT" / "MANAGEMENT", "PLYMOUNTH" / "PLYMOUTH", "WORLEY" / "WORKLEY"): the matcher deliberately refuses near-miss names.
- **Gemini reads messy names far better**, but it called identical names different (e.g. the same two lenders listed on both deeds) and accepted 2 links the labeller judged broken. Both are arguable: a woman with the same first name and middle initial under a new surname (possibly a marriage), and a trust company that was taken over by another bank (possibly a successor). They are counted as misses.
- **Letting the AI clear flags is the most accurate (96.7%)**, but it lets those 2 through and it means the AI decides. Keeping the rules in charge and using the AI only to **label** flags keeps every real break and pre-sorts 27 of the 30 false alarms as "probable spelling variant", which is how a person would want to review them. This is the project's principle (the AI reads, the rules decide) measured on real data.

**Limits.** One labeller; 150 links; one city; the question is name identity, so this measures the chain rule and the name matching, not the authority or lien rules. The 75/75 split oversamples flags, so precision here is not the precision on the whole register.
