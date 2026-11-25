"""Export demo data (graph, verdicts, timeline, fixes, recorded agent runs) for the static demo page."""
import json, pathlib
from .generator import all_cases, documents
from .engine import run_checks, timeline
from .whatif import build, would_fix
from .proof import proofs
from .graphlab import experiments, preset_rows, rules_info, PRESETS

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

def bench_summary():
    """Per-arm held-out summary (mean over repeats) for the demo's benchmark card."""
    import statistics as st
    f = ROOT / "results" / "heldout.jsonl"
    rows = [json.loads(l) for l in f.read_text().splitlines()] if f.exists() else []
    rows = [r for r in rows if not (r["stats"] or {}).get("error")]
    names = {"A": "Documents only", "B": "Graph + own Cypher", "C": "Graph + rule-engine tools", "D": "Rule engine alone"}
    out = []
    for arm in "ABCD":
        S = [r for r in rows if r["arm"] == arm]
        if not S: continue
        reps = sorted({r["rep"] for r in S})
        rate = lambda k, T: 100 * sum(r[k] for r in T) / len(T) if T else 0
        acc = [rate("correct", [r for r in S if r["rep"] == p]) for p in reps]
        fc = [rate("false_clean", [r for r in S if r["rep"] == p and r["label"] == "defective"]) for p in reps]
        out.append(dict(arm=arm, name=names[arm], repeats=len(reps), cases=len({r["case"] for r in S}), acc=round(st.mean(acc), 1),
                        false_clean=round(st.mean(fc), 1), tokens=int(st.mean(r["stats"].get("tokens", 0) for r in S))))
    return out


def traces():
    f = ROOT / "results" / "traces.jsonl"
    out = {}
    if f.exists():
        for l in f.read_text().splitlines():
            r = json.loads(l)
            if not r.get("error"):
                out.setdefault(r["case"], {})[r["arm"]] = dict(answer=r["answer"], trace=r["trace"], citations=r["citations"], tokens=r["tokens"], tool_calls=r["tool_calls"], label=r["label"])
    return out


def intake_summary():
    """Reader accuracy on the held-out extraction benchmark (regex vs Gemini, clean vs messy wording)."""
    f = ROOT / "results" / "intake.jsonl"
    rows = [json.loads(l) for l in f.read_text().splitlines()] if f.exists() else []
    out = []
    for rd in ("regex", "llm"):
        for sty in ("clean", "messy"):
            S = [r for r in rows if r["reader"] == rd and r["style"] == sty]
            if S: out.append(dict(reader={"regex": "Offline rules", "llm": "Gemini"}[rd], style=sty, n=len(S), verdict=round(100 * sum(r["correct"] for r in S) / len(S), 1)))
    return out


def landing_data(cases):
    c = next(x for x in cases if x["id"] == "prop-014")
    tr = [dict(id=n["id"], effective=n["effective"], recorded=n["recorded"]) for n in c["nodes"] if n["label"] == "Transfer"]
    tr.sort(key=lambda t: int(t["id"][1:]) if t["id"][1:].isdigit() else 999)
    f = c["result"]["findings"][0]
    return dict(arms=bench_summary(), intake=intake_summary(),
                sample=dict(id=c["id"], as_of=c["as_of"], transfers=tr, timeline=c["timeline"], bad=f["transfer"], rule=f["rule"], detail=f["detail"]))


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
            result=r, timeline=tl, proof=[dict(rule=x['rule'], transfer=x['transfer'], passages=x.get('passages', []), records_total=x.get('records_total', 0)) for x in proofs(c, r)], fix=(c["key"]["fix"] or {}).get("describe"), fix_verdict=fixv,
            documents=documents(c), agents=rec.get(c["id"], {}), rm=experiments(c), presets=preset_rows(c), asset=c["asset"]))
    (ROOT / "demo" / "data.js").write_text("window.VESTIGIUM = " + json.dumps(cases, default=str) + ";\nwindow.VESTIGIUM_BENCH = " + json.dumps(bench_summary()) + ";\nwindow.VESTIGIUM_LAB = " + json.dumps(dict(rules={p: rules_info(p) for p in ("property", "vehicle")}, presets={k: dict(title=v["title"], text=v["text"], cypher=v["cypher"].strip()) for k, v in PRESETS.items()})) + ";\nwindow.VESTIGIUM_TRACES = " + json.dumps(traces()) + ";")
    (ROOT / "demo" / "bench.js").write_text("window.VBENCH = " + json.dumps(landing_data(cases)) + ";")
    print(f"exported {len(cases)} cases, {sum(1 for c in cases if c['agents'])} with recorded agent runs")

if __name__ == "__main__":
    export()
