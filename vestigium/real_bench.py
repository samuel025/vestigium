"""A benchmark on REAL records, scored against BLIND human labels.

Public registers publish no answer key, so a person supplies one: for each sampled seller-to-previous-buyer link from the
Philadelphia records, they read the two real register entries (without seeing what the engine said) and answer one
question: is the seller of the later deed the same party as the buyer of the earlier one?

    uv run python -m vestigium.real_bench sample          # draw the blind sample  -> data/philly_raw/label_items.json
    uv run python -m vestigium.serve                      # label at http://127.0.0.1:8000/label.html (answers saved locally)
    uv run python -m vestigium.real_bench llm             # optional: the same question put to Gemini, record by record
    uv run python -m vestigium.real_bench score           # engine (and Gemini) vs the human labels -> results/real_bench.json

What it measures: the chain rule (PROP-CHAIN) together with the importer's name matching, on real data. What it does not:
the authority and lien rules, because public registers hold neither powers of attorney's terms nor which payoff released
which mortgage. Real names stay in data/philly_raw/ (gitignored); results/real_bench.json holds counts only.
"""
import argparse, json, pathlib, random
from .philly import chains, RAW
from .acris import group_match, to_case
from .engine import run_checks
from .whatif import build

ROOT = pathlib.Path(__file__).resolve().parent.parent
ITEMS, LABELS, LLM = RAW / "label_items.json", RAW / "labels.json", RAW / "label_llm.json"
OPTIONS = {"same": "Same party", "variant": "Same party, name written differently", "different": "Different party: the chain breaks here",
           "unsure": "Can't tell from these records"}


def links():
    """Every seller-to-previous-buyer link, with what the engine decided about it (kept out of the labelling page)."""
    out = []
    for k, (opa, deeds) in enumerate(chains(), 1):
        res = run_checks(build(to_case(k, deeds)), "A1", max(d["recorded"] for d in deeds), pack="property")
        broken = {f["transfer"] for f in res["findings"] if f["rule"] == "PROP-CHAIN"}
        for i in range(1, len(deeds)):
            out.append(dict(prop=k, prev=deeds[i - 1], deed=deeds[i], flagged=f"T{i+1}" in broken,
                            matched=group_match(deeds[i]["sellers"], deeds[i - 1]["buyers"])))
    return out


def sample(n=150, seed=7):
    """Half the links the engine flagged, half it accepted, shuffled, with neutral ids. The engine's answer is stored
    separately from what the page shows, so the labeller cannot see it."""
    rng = random.Random(seed)
    L = links()
    fl, ok = [x for x in L if x["flagged"]], [x for x in L if not x["flagged"]]
    pick = rng.sample(fl, n // 2) + rng.sample(ok, n - n // 2)
    rng.shuffle(pick)
    show = lambda d: dict(type=d.get("type", "DEED"), signed=d["effective"], recorded=d["recorded"], sellers=d["sellers"], buyers=d["buyers"])
    items = [dict(id=f"L{i+1:03d}", earlier=show(x["prev"]), later=show(x["deed"]), _engine_flagged=x["flagged"]) for i, x in enumerate(pick)]
    ITEMS.write_text(json.dumps(items, indent=1))
    return len(items), sum(x["_engine_flagged"] for x in items)


def public_items():
    """What the labelling page may see: no engine answer."""
    return [{k: v for k, v in it.items() if not k.startswith("_")} for it in json.loads(ITEMS.read_text())]


def save_label(item_id, label):
    if label not in OPTIONS: raise ValueError("unknown label")
    ids = {it["id"] for it in json.loads(ITEMS.read_text())}
    if item_id not in ids: raise ValueError("unknown item")
    labels = json.loads(LABELS.read_text()) if LABELS.exists() else {}
    labels[item_id] = label
    LABELS.write_text(json.dumps(labels, indent=1))
    return len(labels)


PROMPT = """Two entries from a public property register for the SAME property. The later deed's seller(s) should be the
earlier deed's buyer(s). Names may be written "SURNAME FIRSTNAME", abbreviated, misspelled, or appear as an estate, trust,
executor or trustee of the same person.

EARLIER DEED ({e_type}, signed {e_signed}, recorded {e_rec}): buyer(s): {e_buyers}
LATER DEED ({l_type}, signed {l_signed}, recorded {l_rec}): seller(s): {l_sellers}

Judge only the names, not the document type. Is the later seller the same party as the earlier buyer? Count an estate,
executor or trustee acting for the same person, and an obvious misspelling, as the same party. Count a relative or a
different company as different. If several names are listed, it is the same party if any of them clearly is.
Reply with ONE word: same, different, or unsure."""


def ask_llm():
    """The same question, put to Gemini one link at a time (blind to the engine's answer). Resumable."""
    from . import llm
    items = json.loads(ITEMS.read_text())
    done = json.loads(LLM.read_text()) if LLM.exists() else {}
    for it in items:
        if it["id"] in done: continue
        e, l = it["earlier"], it["later"]
        p = PROMPT.format(e_type=e["type"], e_signed=e["signed"], e_rec=e["recorded"], e_buyers="; ".join(e["buyers"]),
                          l_type=l["type"], l_signed=l["signed"], l_rec=l["recorded"], l_sellers="; ".join(l["sellers"]))
        ans, st = llm.ask("You compare names in property records. Answer with one word.", p, max_calls=0)
        word = str(st.get("final_text") or "").strip().lower().strip('"*. ')
        done[it["id"]] = "same" if word.startswith("same") else "different" if word.startswith("diff") else "unsure"
        LLM.write_text(json.dumps(done, indent=1))
    return len(done)


def score():
    items = {it["id"]: it for it in json.loads(ITEMS.read_text())}
    labels = json.loads(LABELS.read_text()) if LABELS.exists() else {}
    gem = json.loads(LLM.read_text()) if LLM.exists() else {}
    truth = {i: ("break" if l == "different" else "link") for i, l in labels.items() if l != "unsure"}

    def metrics(pred):          # pred[id] in {"break", "link", None}
        ids = [i for i in truth if pred.get(i) in ("break", "link")]
        tp = sum(pred[i] == "break" and truth[i] == "break" for i in ids); fp = sum(pred[i] == "break" and truth[i] == "link" for i in ids)
        fn = sum(pred[i] == "link" and truth[i] == "break" for i in ids); tn = sum(pred[i] == "link" and truth[i] == "link" for i in ids)
        r = lambda a, b: round(100 * a / b, 1) if b else None
        return dict(n=len(ids), accuracy=r(tp + tn, len(ids)), precision=r(tp, tp + fp), recall=r(tp, tp + fn),
                    true_breaks_found=tp, false_alarms=fp, breaks_missed=fn, correct_links=tn)

    engine = {i: ("break" if it["_engine_flagged"] else "link") for i, it in items.items()}
    gemini = {i: {"same": "link", "different": "break"}.get(a) for i, a in gem.items()}
    from collections import Counter
    flagged_labels = Counter(labels[i] for i in labels if items[i]["_engine_flagged"])
    # Two ways to combine them. (1) The AI may clear a flag it reads as the same party (the AI decides: against our principle).
    # (2) The rules decide; the AI only labels each flag "probable spelling variant" or not, so a person checks those first.
    cleared = {i: ("break" if items[i]["_engine_flagged"] and gem.get(i) != "same" else "link") for i in items} if gem else None
    fl = [i for i in truth if items[i]["_engine_flagged"]]
    annotate = dict(flags=len(fl), real_breaks=sum(truth[i] == "break" for i in fl), false_alarms=sum(truth[i] == "link" for i in fl),
                    false_alarms_labelled_probable_variant=sum(truth[i] == "link" and gem.get(i) == "same" for i in fl),
                    real_breaks_labelled_probable_variant=sum(truth[i] == "break" and gem.get(i) == "same" for i in fl)) if gem else None
    out = dict(source="Philadelphia Real Estate Transfer Tax records, deterministic sample of seller-to-previous-buyer links (half flagged by the engine, half accepted), shuffled",
               labelled_by="a person, blind to the engine's answer, reading only the two register entries",
               items=len(items), labelled=len(labels), label_counts=dict(Counter(labels.values())),
               engine=metrics(engine), gemini_reading_names=metrics(gemini) if gem else None,
               engine_flags_ai_may_clear=metrics(cleared) if gem else None, engine_decides_ai_labels_flags=annotate,
               what_the_engine_flagged_turned_out_to_be=dict(flagged_labels))
    (ROOT / "results" / "real_bench.json").write_text(json.dumps(out, indent=1))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("cmd", choices=["sample", "llm", "score"]); ap.add_argument("--n", type=int, default=150); a = ap.parse_args()
    if a.cmd == "sample": print("items, engine-flagged:", sample(a.n))
    elif a.cmd == "llm": print("answered:", ask_llm())
    else: print(json.dumps(score(), indent=1))
