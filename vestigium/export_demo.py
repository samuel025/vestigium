"""Export demo data (graph, verdicts, timeline, fixes, recorded agent runs) for the static demo page."""
import json, pathlib
from .generator import all_cases, documents
from .engine import run_checks, timeline
from .whatif import build, would_fix

ROOT = pathlib.Path(__file__).resolve().parent.parent

def runs():
    out = {}
    f = ROOT / "results" / "heldout.jsonl"
    if f.exists():
        for l in f.read_text().splitlines():
            r = json.loads(l)
            if not (r["stats"] or {}).get("error"):
                out.setdefault(r["case"], {})[r["arm"]] = r["answer"]
    return out

def export():
    rec = runs()
    cases = []
    for c in all_cases():
        db = build(c)
        r = run_checks(db, c["asset"], c["as_of"], pack=c["pack"])
        dates = sorted({p["recorded"] for l, p in c["nodes"] if l == "Transfer"} | {c["as_of"]})
        tl = timeline(db, c["asset"], dates, c["as_of"]) if False else [
            (d, run_checks(db, c["asset"], c["as_of"], known=d, pack=c["pack"])["verdict"]) for d in dates]
        fixv = would_fix(c, c["key"]["fix"])["verdict"] if c["key"]["fix"] else None
        cases.append(dict(
            id=c["id"], domain=c["domain"], label=c["label"], split=c["split"], as_of=c["as_of"], kind=c["kind"],
            title=f"{c['domain'].title()} · {c['kind']} · {c['n_transfers']} transfers",
            nodes=[dict(label=l, **p) for l, p in c["nodes"]], rels=c["rels"],
            result=r, timeline=tl, fix=(c["key"]["fix"] or {}).get("describe"), fix_verdict=fixv,
            documents=documents(c), agents=rec.get(c["id"], {})))
    (ROOT / "demo" / "data.js").write_text("window.VESTIGIUM = " + json.dumps(cases, default=str) + ";")
    print(f"exported {len(cases)} cases, {sum(1 for c in cases if c['agents'])} with recorded agent runs")

if __name__ == "__main__":
    export()
