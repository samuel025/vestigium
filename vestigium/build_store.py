"""Build the persistent demo store (./vestigium.rl): one synthetic property dossier with a planted authority defect.
   Also writes answer_key.json for every benchmark case."""
import json, pathlib, sys
from .generator import all_cases
from .engine import open_graph, load_case, run_checks

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHOWCASE = "prop-014"

def main():
    store = ROOT / "vestigium.rl"
    if store.exists(): store.unlink()
    for extra in ROOT.glob("vestigium.rl.*"): extra.unlink()
    case = next(c for c in all_cases() if c["id"] == SHOWCASE)
    db = open_graph(str(store)); load_case(db, dict(nodes=case["nodes"], rels=case["rels"])); db.commit() if hasattr(db, "commit") else None; db.close()
    db = open_graph(str(store))
    r = run_checks(db, case["asset"], case["as_of"], pack=case["pack"])
    print(f"store {store.name}: {SHOWCASE} -> {r['verdict']} ({r['findings'][0]['rule']} at {r['findings'][0]['transfer']})")
    key = [dict(id=c["id"], domain=c["domain"], split=c["split"], label=c["label"], kind=c["kind"], adversarial=c["adversarial"],
                planted_transfer=c["key"]["transfer"], planted_rule=c["key"]["rule"], missing=c["key"]["missing"], fix_type=c["key"].get("fix_type"))
           for c in all_cases()]
    (ROOT / "answer_key.json").write_text(json.dumps(key, indent=1))
    print(f"answer_key.json: {len(key)} cases")

if __name__ == "__main__":
    main()
