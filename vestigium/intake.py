"""Paste a dossier, get a verdict. reader -> graph -> rule engine -> same data shape the demo UI renders.

The reader (regex for canonical wording, Gemini for anything else) only extracts facts. The rule engine decides.
Every extracted fact is shown back to the user so the reading step can be checked by a person.
"""
import copy
from datetime import date, timedelta
from .engine import run_checks
from .extract import read_rules, read_llm, assemble
from .whatif import build

iso = lambda d: d.isoformat()


def _auto_fix(case, res):
    """Hypothetical record(s) that would resolve the finding, for the rule types where one record can. None otherwise."""
    items = res["findings"] + res["missing"]
    kinds = {f.get("fix_type") for f in items}
    nodes = {p["id"]: (l, p) for l, p in case["nodes"] if "id" in p}
    ts = sorted([p for l, p in case["nodes"] if l == "Transfer"], key=lambda p: (p["effective"], p["id"]))
    if len(kinds) != 1:
        return None
    k = kinds.pop()
    ex = dict(nodes=[], rels=[], set=[])
    if k == "release_of_lien":
        for l, p in case["nodes"]:
            if l == "Claim" and p["kind"] == "lien" and not any(a == p["id"] and t == "CLEARED_BY" for a, t, _ in case["rels"]):
                later = [t["effective"] for t in ts if t["effective"] >= p["effective"]]
                d = max(date.fromisoformat(p["effective"]), date.fromisoformat(min(later)) - timedelta(days=1)) if later else date.fromisoformat(p["effective"])
                ex["nodes"].append(("Document", dict(id="REL-" + p["id"], kind="release", effective=iso(d), recorded=iso(d))))   # a release that predates the sale it must clear
                ex["rels"].append((p["id"], "CLEARED_BY", "REL-" + p["id"]))
        what = "a recorded release of the lien"
    elif k == "valid_authority":
        for f in items:
            t = nodes[f["transfer"]][1]
            d = date.fromisoformat(t["effective"])
            ex["nodes"].append(("Authority", dict(id="AU-FIX-" + t["id"], agent="ratifier", valid_from=iso(d - timedelta(days=1)))))
            ex["rels"].append((t["id"], "ACTED_UNDER", "AU-FIX-" + t["id"]))
        what = "a ratifying resolution valid on the signing date"
    elif k == "link_previous_transfer":
        for f in items:
            i = next(j for j, p in enumerate(ts) if p["id"] == f["transfer"])
            if i:
                ex["rels"].append((f["transfer"], "FOLLOWS", ts[i - 1]["id"]))
        what = "a record showing how the seller acquired the asset"
    elif k == "odometer_reading":
        for f in items:
            i = next(j for j, p in enumerate(ts) if p["id"] == f["transfer"])
            prev = next((q["odometer"] for q in reversed(ts[:i]) if "odometer" in q), 0)
            ex["set"].append((f["transfer"], "odometer", prev + 5000))
        what = "an odometer disclosure statement"
    else:
        return None
    if not (ex["nodes"] or ex["rels"] or ex["set"]):
        return None
    after = run_checks(build(case, ex), case["asset"], case["as_of"], pack=case["pack"])["verdict"]
    return dict(describe=what, verdict=after)


def analyze(text, reader="auto", as_of=None):
    warnings, used, stats = [], reader, {}
    if reader in ("auto", "rules"):
        ir = read_rules(text); used = "rules"
        n = sum(r["type"] in ("deed", "title") for r in ir["records"])
        if n == 0 and reader == "auto":
            reader = "llm"
    if reader == "llm":
        try:
            ir, stats = read_llm(text); used = "llm"
        except Exception as e:
            return dict(error=f"The language-model reader is unavailable ({str(e)[:90]}). Use canonical wording for the offline reader.")
        if not ir:
            return dict(error="The reader could not parse that dossier.")
    case = assemble(ir, as_of=as_of)
    res = run_checks(build(case), case["asset"], case["as_of"], pack=case["pack"])
    transfers = [p for l, p in case["nodes"] if l == "Transfer"]
    if not transfers:
        warnings.append("No deeds or titles were recognised, so nothing could be checked.")
    dates = sorted({p["recorded"] for p in transfers if p.get("recorded")} | {case["as_of"]})
    tl = [(d, run_checks(build(case), case["asset"], case["as_of"], known=d, pack=case["pack"])["verdict"]) for d in dates]
    fx = _auto_fix(case, res) if res["verdict"] != "clean" else None
    return dict(id="pasted", domain=case["pack"], label=None, split="pasted", as_of=case["as_of"], kind="pasted dossier",
                title=f"{case['pack'].title()} · pasted dossier · {len(transfers)} transfers",
                nodes=[dict(label=l, **p) for l, p in case["nodes"]], rels=case["rels"], result=res, timeline=tl,
                fix=fx and fx["describe"], fix_verdict=fx and fx["verdict"], documents=text, agents={},
                reader=used, tokens=stats.get("tokens", 0), warnings=warnings,
                extracted=[{k: v for k, v in r.items() if k != "text"} for r in ir["records"] if r.get("type") != "other"])
