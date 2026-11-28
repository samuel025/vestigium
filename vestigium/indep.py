"""Cases written by an INDEPENDENT author, so we are not grading our own homework.

A different model family (Gemma) writes realistic property dossiers from a one-line, plain-English description of each
situation. It never sees our rules, our generator, our record wording or our graph schema. The answer key comes from the
situation description, not from our engine. Then:
  A  - a documents-only agent (gemini-3.5-flash-lite) reads the dossier and answers;
  V  - Vestigium end to end: our Gemini reader turns the prose into graph facts, the frozen rules decide.
Every disagreement with the answer key is listed for a hand audit (engine, reader, or a dossier that does not actually
show what its author claimed).

    uv run python -m vestigium.indep write      # the author writes the cases      -> results/indep_cases.jsonl
    uv run python -m vestigium.indep run        # arms A and V (resumable)         -> results/indep_runs.jsonl
    uv run python -m vestigium.indep report
"""
import argparse, json, pathlib, random, time
from collections import Counter, defaultdict

ROOT = pathlib.Path(__file__).resolve().parent.parent
CASES, RUNS = ROOT / "results" / "indep_cases.jsonl", ROOT / "results" / "indep_runs.jsonl"
AUTHORS = ["gemini-3.6-flash", "gemma-4-26b-a4b-it"]   # Gemma (another model family) was overloaded on the day; gemini-3.6-flash wrote the cases
AUTHOR = AUTHORS[0]

# situation -> (what the author is told, the correct verdict). Plain English, no rule names, no schema.
SITUATIONS = {
    "clean":            ("Every sale in the history is valid: each seller had bought the property in the previous sale, all paperwork is in order.", "clean"),
    "clean-tricky":     ("Every sale is valid, but it looks risky at first glance: there was a mortgage that WAS properly paid off and released before the property was sold, and one sale was signed by an agent holding a valid power of attorney from the owner that covered selling and was in force on the signing date.", "clean"),
    "not-owner":        ("One sale in the middle of the history was made by someone who never owned the property: the seller is not the person who bought it in the previous sale.", "defective"),
    "sold-twice":       ("The same owner sold the property twice, to two different buyers, months apart.", "defective"),
    "unreleased-lien":  ("A mortgage was taken out on the property and there is no record that it was ever paid off or released before the property was later sold.", "defective"),
    "expired-poa":      ("One sale was signed by an agent under a power of attorney that had already expired before the signing date.", "defective"),
    "poa-wrong-person": ("One sale was signed by an agent under a power of attorney, but that power of attorney was given by someone other than the person selling (for example an earlier owner).", "defective"),
    "poa-scope":        ("One sale was signed by an agent whose power of attorney only allowed managing and renting out the property, not selling it.", "defective"),
    "poa-revoked":      ("One sale was signed by an agent, but the owner had formally revoked that power of attorney (with a recorded revocation) before the signing date.", "defective"),
    "dead-seller":      ("One sale is dated after the seller had died (a death certificate is in the file).", "defective"),
    "missing-link":     ("There is a gap: one seller sells the property, but no document in the file shows how that seller ever acquired it (the deed that would have given it to them is missing). Nothing else is wrong.", "inconclusive"),
    "missing-poa":      ("One sale was signed by an agent 'on behalf of' the owner, but the power of attorney itself is not in the file at all. Nothing else is wrong.", "inconclusive"),
}

BRIEF = """Write a realistic, entirely fictional property file for testing a title-checking tool. Fictional town, fictional people.

Situation to build in (do not state it outright anywhere in the file, and do not label anything as a problem): {situation}

Requirements:
- 4 to 9 records, in chronological order or slightly shuffled. Each record starts on its own line with an id in square brackets, [R1], [R2], ...
- Write the records the way real registry documents read: deeds, mortgages, releases, powers of attorney, revocations, death certificates, and 1 to 3 irrelevant documents (tax notice, survey, insurance). Vary the wording and the date formats.
- Every deed must say who sold, who bought, the date it was signed and the date it was recorded. Every sale must refer to the same property.
- As real deeds do, every deed after the first includes a recital such as "being the same premises which <seller> acquired by deed dated <date>", naming the earlier deed the seller acquired it through (even if that deed is not in the file).
- {extra}

Reply with ONLY a JSON object: {{"dossier": "<the records, separated by blank lines>", "as_of": "<a date after the last record, yyyy-mm-dd>", "broken_record": "<the id of the record where the problem is, or null>", "note": "<one sentence on how you built the situation>"}}"""

EXTRAS = ["", "Include a cover letter that says the title is clear and free of encumbrances.", "Abbreviate a first name in one record (e.g. 'J. Smith').",
          "Write one date in words (e.g. 'the third of March, 2016')."]


def write(per=4, seed=3):
    from . import llm
    rng = random.Random(seed)
    done = {json.loads(l)["id"] for l in CASES.read_text().splitlines()} if CASES.exists() else set()
    with CASES.open("a") as f:
        for kind, (situation, verdict) in SITUATIONS.items():
            for j in range(per):
                cid = f"ind-{kind}-{j}"
                if cid in done: continue
                extra = EXTRAS[(j + rng.randint(0, 3)) % len(EXTRAS)] or "Nothing extra."
                ans, who = None, None
                for attempt in range(6):                       # authors get overloaded: back off, then fall back to another model
                    for model in AUTHORS:
                        try:
                            ans, st = llm.ask("You are a careful writer of realistic synthetic legal records for software testing.",
                                              BRIEF.format(situation=situation, extra=extra), model=model, temperature=0.9)
                        except llm.DailyQuotaExhausted:
                            raise
                        except Exception as e:
                            print("  busy:", model, str(e)[:60], flush=True); ans = None
                        if ans and ans.get("dossier"): who = model; break
                    if who: break
                    time.sleep(60 * (attempt + 1))
                if not who:
                    print("author failed", cid, flush=True); continue
                f.write(json.dumps(dict(id=cid, kind=kind, label=verdict, situation=situation, extra=extra, author=who, **ans)) + "\n"); f.flush()
                print("wrote", cid, "by", who, flush=True)


SYS_A = ("You check property ownership chains for a fictional jurisdiction. Not legal advice. Reply with ONLY a JSON object: "
         '{"verdict":"clean|defective|inconclusive","record":"<id of the record where the problem is, or null>","reason":"<one sentence>"}. '
         "clean = every sale valid; defective = a sale is proven invalid; inconclusive = a missing record prevents a decision (do not guess). "
         "A false 'clean' on a defective chain is the worst error.")


def run(repeats=3):
    from . import llm
    from .intake import analyze
    cases = [json.loads(l) for l in CASES.read_text().splitlines()]
    rows = [json.loads(l) for l in RUNS.read_text().splitlines()] if RUNS.exists() else []
    done = {(r["arm"], r["case"], r["rep"]) for r in rows if not r.get("error")}
    with RUNS.open("a") as f:
        for c in cases:
            for rep in range(repeats):
                if ("A", c["id"], rep) not in done:
                    ans, st = llm.ask(SYS_A, f"As of {c.get('as_of')}: can the final buyer rely on this ownership chain?\n\n{c['dossier']}")
                    f.write(json.dumps(dict(arm="A", case=c["id"], rep=rep, verdict=(ans or {}).get("verdict"), record=(ans or {}).get("record"),
                                            tokens=st.get("tokens", 0), error=None if ans else "no answer")) + "\n"); f.flush()
            if ("V", c["id"], 0) not in done:          # the rules are deterministic; the reader runs once per case
                try:
                    out = analyze(c["dossier"], reader="llm", as_of=c.get("as_of"))
                    res = out.get("result") or {}
                    fl = res.get("findings", []) + res.get("missing", [])
                    f.write(json.dumps(dict(arm="V", case=c["id"], rep=0, verdict=res.get("verdict"), rules=[x["rule"] for x in fl],
                                            records=sorted({e for x in fl for e in x.get("evidence", [])}), tokens=out.get("tokens", 0),
                                            error=out.get("error"))) + "\n"); f.flush()
                except llm.DailyQuotaExhausted:
                    raise
                except Exception as e:
                    f.write(json.dumps(dict(arm="V", case=c["id"], rep=0, verdict=None, error=str(e)[:200])) + "\n"); f.flush()


def report():
    cases = {c["id"]: c for c in (json.loads(l) for l in CASES.read_text().splitlines())}
    rows = [json.loads(l) for l in RUNS.read_text().splitlines()]
    out = {}
    for arm in ("A", "V"):
        R = [r for r in rows if r["arm"] == arm and not r.get("error")]
        D = [r for r in R if cases[r["case"]]["label"] == "defective"]
        I = [r for r in R if cases[r["case"]]["label"] == "inconclusive"]
        pct = lambda x: round(100 * sum(x) / len(x), 1) if x else None
        by = defaultdict(list)
        for r in R: by[cases[r["case"]]["kind"]].append(r["verdict"] == cases[r["case"]]["label"])
        out[arm] = dict(runs=len(R), accuracy=pct([r["verdict"] == cases[r["case"]]["label"] for r in R]),
                        defective_called_clean=pct([r["verdict"] == "clean" for r in D]), abstains_on_missing=pct([r["verdict"] == "inconclusive" for r in I]),
                        by_situation={k: pct(v) for k, v in by.items()}, errors=len({(r["case"], r["rep"]) for r in rows if r["arm"] == arm and r.get("error")} - {(r["case"], r["rep"]) for r in R}),
                        retried_after_network_error=sum(1 for r in rows if r["arm"] == arm and r.get("error")))
    out["V_disagreements"] = [dict(case=r["case"], kind=cases[r["case"]]["kind"], expected=cases[r["case"]]["label"], got=r["verdict"], rules=r.get("rules"))
                              for r in rows if r["arm"] == "V" and not r.get("error") and r["verdict"] != cases[r["case"]]["label"]]
    out["cases"] = len(cases); out["authors"] = dict(Counter(c.get("author") for c in cases.values()))
    (ROOT / "results" / "indep_report.json").write_text(json.dumps(out, indent=1))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("cmd", choices=["write", "run", "report"]); ap.add_argument("--per", type=int, default=4); a = ap.parse_args()
    if a.cmd == "write": write(a.per)
    elif a.cmd == "run": run()
    else: print(json.dumps(report(), indent=1))
