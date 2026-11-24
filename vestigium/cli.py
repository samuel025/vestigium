import argparse, json
from .generator import property_cases
from .engine import run_checks, timeline
from .whatif import build, would_fix


def main():
    ap = argparse.ArgumentParser(prog="vestigium")
    ap.add_argument("case", help="case id, e.g. prop-014")
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    c = next(x for x in property_cases(a.seed) if x["id"] == a.case)
    db = build(c)
    r = run_checks(db, c["asset"], c["as_of"])
    print(f"{c['id']}  verdict: {r['verdict'].upper()}  (answer key: {c['label']})")
    for f in r["findings"] + r["missing"]:
        print(f"  {f['rule']} @ {f['transfer']}: {f['detail']}  evidence={f['evidence']}" + (f"\n    missing: {f['missing']}" if f.get("missing") else ""))
    if c["key"]["fix"]:
        print(f"  what would fix it: {c['key']['fix']['describe']} -> {would_fix(c, c['key']['fix'])['verdict']}")
    dates = sorted({p["recorded"] for l, p in c["nodes"] if l == "Transfer"} | {c["as_of"]})
    print("  verdict timeline:", " ".join(f"{d}:{v}" for d, v in timeline(db, c["asset"], dates, c["as_of"])))

if __name__ == "__main__":
    main()
