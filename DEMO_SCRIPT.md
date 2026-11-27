# Demo video script — 2 minutes: "Would you buy this property?"

**Setup before recording**
- Open `https://vestigium-demo.vercel.app/app.html?case=prop-014` in a browser about 1400 px wide. Dismiss the "New here?" banner once (it stays dismissed).
- Have these tabs ready (deep links jump straight to each moment):
  - `…/app.html?case=prop-014` (start)
  - `…/app.html?case=prop-014&gap=1` (signed, not yet filed)
  - `…/app.html?case=prop-014&remove=T5>ACTED_UNDER>AU1` (break a link)
  - `…/app.html?case=auth-016&walk=1` (authority in depth, optional)
  - `…/app.html?case=phl-d81620` (real records, optional)
- `prop-014` is a synthetic 12-sale property chain. T5 was signed on 2019-05-01 by an agent whose power of attorney ended on 2019-01-17. The dossier also contains a planted "title is clear" summary.
- Pace: about 140 words a minute; the narration is about 280 words. Lines in *italics* are what is on screen.

---

### 0:00–0:15 · The question
> "Would you buy this property? Twelve sales, every document in order, and a title summary that says it's clear."

*The case header: "Would you buy this property? **No, not on this evidence.** The chain breaks at T5, and 7 later sales rest on it."*

### 0:15–0:35 · Where does it break, and what proves it?
> "Vestigium checks every sale against the evidence it needed at the time. Sale five breaks. The proof is two records out of eighteen: the deed, and a power of attorney that had already expired."

*Click **Where does it break?** (T5 pulses), then **What proves it?** (PROP-AUTH, minimal proof 2 of 18, the two exact passages).*

### 0:35–0:50 · Was the signer allowed?
> "The question is never just 'is there a power of attorney'. Was it in force that day? Did the seller grant it? Does it cover selling? Was it revoked? Did the named agent sign?"

*Click **Was the signer allowed?**: the inspector lists each question with ✓ or ✗. Optional: open `auth-016&walk=1`, where the power was granted by an earlier owner, not the seller.*

### 0:50–1:05 · What else does it break?
> "One broken sale doesn't stay put. Seven later owners bought through it, so their title rests on it too, however clean their own sale looks."

*Click **What else does it break?**: striped boxes after T5 and the "Later sales that rest on it" note. In the graph, T6 to T12 are dashed.*

### 1:05–1:25 · What could you have known?
> "There are two kinds of time. Sale five was signed on the first of May but only filed on the fourth. An investigator checking in between was told the chain was clean. Vestigium answers both: what was true, and what could be known."

*Click **What could you have known?** (or the `gap=1` tab): the header says CLEAN, T5 is dashed "SIGNED · NOT FILED", and the verdict grid shows the staircase.*

### 1:25–1:45 · It's a graph, and the rules are queries
> "All of this lives in one Relate graph, and every rule is a plain Cypher query. Remove the authority link, and the engine stops calling it defective: it says a record is missing, and accuses no one."

*Open the `remove=T5>ACTED_UNDER>AU1` tab: verdict DEFECTIVE → INCONCLUSIVE, PROP-AUTH-MISSING appears, "Show the Cypher that caught it".*

### 1:45–2:00 · Does it hold up?
> "The AI only reads; the rules decide. With the rule engine, an AI agent went from 56 to 100 percent on held-out cases. And on thirty thousand real deeds from New York and Philadelphia, its flags are the ones a title examiner would chase."

*Overview page: benchmark bars, then the Real records section (or the `phl-d81620` tab).*

---

**If you have more time:** paste a dossier in the local app (*Paste or upload → Load a messy sample → Check this dossier*), or show the agent replay (`…/app.html?case=prop-014&replay=4`).

**Avoid:** saying it gives legal advice, or that a real-record flag is a proven defect. It's "worth a look", not proven.
