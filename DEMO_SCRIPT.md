# Demo video script — 2 minutes

**Setup before recording:** `cd demo && python3 -m http.server 8000`, then open `http://127.0.0.1:8000/index.html?case=prop-014`.
Browser at about 1400 px wide (the page is dark-only now, so there is no theme to match). Case `prop-014` is a synthetic 5-transfer property chain. The seller of T5 signed as an agent on 2019-05-01, but the power of attorney ended 2019-01-17.
A planted "title is clear and free of encumbrances" summary sits in the dossier to mislead.

Speaking pace is about 140 words a minute; the narration below is about 270 words.

---

### 0:00–0:15 — The problem (page loaded, chain visible, no clicks)

> "Before you buy a property, someone has to be sure the seller could really sell. Defects hide *between* records:
> a signature under a power of attorney that had expired, a lien nobody released. Vestigium finds them, and shows the proof."

*On screen: the transfer boxes joined by arrows, with T5 glowing red in the middle, and the claims-and-authority chip underneath.*

### 0:15–0:35 — The race (scroll or point to the Race panel)

> "Here's a dossier with a planted trap: a summary saying 'title is clear'. An agent reading only the documents trusts it and says clean.
> Vestigium's agent doesn't."

*On screen: Race panel. Document-only agent: CLEAN ✗ answer key defective. Vestigium: DEFECTIVE ✓.*

### 0:35–0:55 — The broken link (top right: verdict card)

> "The rule engine, not the AI, decides. Rule PROP-AUTH fires at transfer T5, and it lights up red in the chain.
> The agent can only call the checks and explain; it can't invent a rule."

*On screen: red outline on T5; finding card "PROP-AUTH · T5 — Heath Agent signed on 2019-05-01 but authority ran 2018-03-27 to 2019-01-17".*

### 0:55–1:10 — The proof (click the finding)

> "Click the finding and you get the exact passages: the deed, and the power of attorney whose term ends before the sale.
> Every claim cites the stored text, and a citation the agent invents is rejected."

*On screen: Evidence card showing passages P5 and PAU.*

### 1:10–1:25 — What would fix it (click "What would fix it?")

> "And it tells you what would resolve it. Vestigium copies the graph into a throwaway Relate instance, adds a ratifying resolution,
> reruns every check, and confirms the chain turns clean."

*On screen: green box "Adding a ratifying resolution valid on the signing date … → CLEAN".*

### 1:25–1:45 — Two dates (drag the slider left, then right)

> "Every fact has two dates: when it took effect, and when we recorded it. Slide back and the verdict was clean
> until the transfer was recorded in May 2019. We can replay a chain as it was true and as it was known."

*On screen: slider moves, verdict strip goes green, then red at 2019-05-04; later transfers fade when not yet recorded.*

### 1:45–2:00 — Does the graph help? (scroll to the "Does the graph help?" card)

> "We built 80 synthetic cases and scored the 40 held out. Documents only: 56% accuracy, and one defective chain in three called clean.
> A graph alone: no better. The graph plus the rule engine: 100%, none missed. We report our losses and publish the answer key.
> That's Vestigium, built on Relate."

*On screen: the benchmark card on the same page, accuracy bars A 55.8% / B 54.2% / C 100% / D 100% and the red "called clean" bars.*

---

## Notes for the take

- If a click is slow, the page is fully static: reload with `?case=prop-014`.
- Say "synthetic data" once if there is room; the page header already says it.
- Do not claim 100% generalises. If asked: the rules and generator were written together, and Arm D is the control. This is in the README.
- Arm B has three repeats but is noisy (47.5%–62.5%); say "about the same as documents only", not an exact number.
- A fallback case if `prop-014` misbehaves: `prop-059` (an unreleased lien, T10; the fix button shows the release).
- The benchmark card is on the page (below the replay strip), so the whole demo stays in one tab.
