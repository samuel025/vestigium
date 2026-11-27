# The rules

All 18 rules, the power-of-attorney checks in depth, and the minimal proof behind every finding.

[← back to the README](../README.md)

**Rule packs** (`vestigium/rules.py`): *Property*: PROP-CHAIN, PROP-DUP, PROP-LIEN, PROP-AUTH, PROP-AUTH-PRINCIPAL, PROP-AUTH-SCOPE, PROP-AUTH-REVOKED, PROP-AUTH-SIGNER, PROP-DATE, PROP-DEATH, PROP-GAP, PROP-AUTH-MISSING. *Vehicle*: VEH-OWN, VEH-LIEN, VEH-BRAND, VEH-ODO, VEH-GAP, VEH-ODO-MISSING.

Each rule is a plain Cypher query in [`vestigium/rules.py`](../vestigium/rules.py). Rules that detect a *missing* record (`PROP-GAP`, `PROP-AUTH-MISSING`, `VEH-GAP`, `VEH-ODO-MISSING`) give *inconclusive*; the rest give *defective*. After the rules run, the engine walks `FOLLOWS` forward from every broken sale and reports the later sales that rest on it.

## Power of attorney, in depth

Most chains break where someone signs *for* the owner. Vestigium asks every question a title examiner would about that power of attorney, each as its own rule on the graph:

| Rule | The question | Graph pattern |
|---|---|---|
| `PROP-AUTH` | Was it in force on the signing date? | the sale's date against the authority's `valid_from` / `valid_to` |
| `PROP-AUTH-PRINCIPAL` | Did the **seller** grant it? | `(authority)-[:GRANTED_BY]->(person)` must be the seller `-[:FROM]->(sale)` |
| `PROP-AUTH-SCOPE` | Does it cover **selling**, not just managing? | the authority's `scope` |
| `PROP-AUTH-REVOKED` | Was it **revoked** before the signing? | `(authority)-[:REVOKED_BY]->(revocation)`, dated before the sale and on file by the date you ask about |
| `PROP-AUTH-SIGNER` | Did the agent it names actually **sign**? | the sale's `signer` against the authority's `agent` |
| `PROP-AUTH-MISSING` | Is there an authority at all? | an agent-signed sale with no `ACTED_UNDER` (inconclusive, not defective) |

A defect fires only when **no other** authority on the sale answers every question (one shared Cypher condition), so a ratification fixes it. A revocation has two dates too: one signed before the sale but filed after it is invisible to an investigator at the sale and appears once filed, which the *Two kinds of time* grid shows. The app's case picker has a **Power of attorney, in depth** group (18 cases: 3 of each defect, 2 late-filed revocations, 4 valid agent sales that look risky); clicking an agent-signed sale, or *Walk the chain*, lists each question with ✓ or ✗. These cases were written after the 80-case benchmark and are not part of its held-out split; the new rules change no verdict on those 80 (tested).

## Minimal proof: what a finding actually rests on

For every finding the engine also computes its **minimal proof** (`vestigium/proof.py`): it deletes facts from the graph (transfers, claims, authorities, links, death records), keeping each deletion only if the
finding still fires, until no single fact can go. What is left is sufficient and necessary: the finding fires on those facts alone and disappears if any one is removed, and every other record could be deleted without
changing it. Across the 70 findings in the 80 cases the proof averages **1.8 records out of a 10.3-record dossier** (17.5%, never more than 2). It is deterministic, needs no LLM, and the UI shows it on the Evidence card.

It also audited our own citations and found a real bug: in **33 of 70 findings** the rule's cited evidence left out a record the proof needs (for example a death-before-signing finding cited the deed but not the death
certificate; a lien finding cited the mortgage but not the sale it clouds). The rules now cite every record their proof rests on, and `tests/test_proof.py` checks that each proof is sufficient, minimal, and fully cited.
(The recorded agent runs predate this fix; the agents' answers were scored on verdicts and valid citations, which it does not change.)
