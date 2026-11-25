"""Metamorphic checks for the rule engine.

A metamorphic test changes a case in a way that must NOT change the verdict (reorder it, rename everything,
shift every date, add unrelated records) and asserts the engine's answer is unchanged. It needs no labelled
answer key, so it tests the rules independently of the generator that "planted" the errors.
"""
import copy
import random
from datetime import date, timedelta

from .engine import run_checks
from .whatif import build

DATE_KEYS = {"effective", "recorded", "valid_from", "valid_to", "died", "died_recorded"}
NAME_KEYS = {"name", "agent", "holder"}


def signature(res, idmap=None):
    """What must stay the same: verdict, which rule fired where, and which passages it cited."""
    m = (lambda x: idmap.get(x, x)) if idmap else (lambda x: x)
    key = lambda rows: sorted((r["rule"], m(r["transfer"]), tuple(sorted(m(e) for e in r.get("evidence", [])))) for r in rows)
    return res["verdict"], key(res["findings"]), key(res["missing"])


def run(case, pack=None, known=None):
    return run_checks(build(case), case["asset"], case["as_of"], known=known, pack=pack or case["pack"])


def _ids(case):
    return [p["id"] for _, p in case["nodes"] if "id" in p]


def shuffle(case, rng):
    c = copy.deepcopy(case)
    rng.shuffle(c["nodes"]); rng.shuffle(c["rels"])
    return c, {}


def rename_ids(case, rng):
    ids = _ids(case)
    new = [f"n{i:04d}" for i in range(len(ids))]
    rng.shuffle(new)                       # random order: an id-order shortcut in a rule would now break
    idmap = dict(zip(ids, new))
    c = copy.deepcopy(case)
    for _, p in c["nodes"]:
        if "id" in p: p["id"] = idmap[p["id"]]
    c["rels"] = [(idmap[a], t, idmap[b]) for a, t, b in c["rels"]]
    c["asset"] = idmap[c["asset"]]
    return c, idmap


def rename_names(case, rng):
    c = copy.deepcopy(case)
    for _, p in c["nodes"]:
        for k in NAME_KEYS & p.keys():
            p[k] = f"Zed{rng.randint(10**5, 10**6)} Q"
    return c, {}


def shift_dates(case, rng, days=None):
    days = days if days is not None else rng.randint(-2000, 4000)
    c = copy.deepcopy(case)
    sh = lambda s: (date.fromisoformat(s) + timedelta(days=days)).isoformat()
    for _, p in c["nodes"]:
        for k in DATE_KEYS & p.keys():
            if p[k]: p[k] = sh(p[k])
    c["as_of"] = sh(c["as_of"])
    return c, {}


def add_noise(case, rng):
    """Unrelated records: stray parties and passages, plus a whole second asset with its own defective chain."""
    c = copy.deepcopy(case)
    c["nodes"] += [("Party", dict(id="zz-p1", name="Stray One")), ("Party", dict(id="zz-p2", name="Stray Two")),
                   ("Passage", dict(id="zz-ps", text="Unrelated note about a different matter.")),
                   ("Asset", dict(id="ZZ-A")),
                   ("Transfer", dict(id="ZZ-T1", effective="2016-01-01", recorded="2016-01-02", root=True)),
                   ("Transfer", dict(id="ZZ-T2", effective="2017-01-01", recorded="2017-01-02")),
                   ("Passage", dict(id="ZZ-P1", text="x")), ("Passage", dict(id="ZZ-P2", text="y"))]
    c["rels"] += [("ZZ-T1", "MOVES", "ZZ-A"), ("ZZ-T2", "MOVES", "ZZ-A"), ("ZZ-T1", "TO", "zz-p1"), ("ZZ-T2", "TO", "zz-p2"),
                  ("zz-p2", "FROM", "ZZ-T1"), ("zz-p2", "FROM", "ZZ-T2"),     # a broken chain on the OTHER asset
                  ("ZZ-T2", "FOLLOWS", "ZZ-T1"), ("ZZ-T1", "EVIDENCED_BY", "ZZ-P1"), ("ZZ-T2", "EVIDENCED_BY", "ZZ-P2")]
    return c, {}


TRANSFORMS = {"shuffle": shuffle, "rename_ids": rename_ids, "rename_names": rename_names,
              "shift_dates": shift_dates, "add_noise": add_noise}


def check_case(case, seed=0):
    """Return a list of failures (empty = every invariance held) for one case."""
    base = signature(run(case))
    out = []
    for name, fn in TRANSFORMS.items():
        c2, idmap = fn(case, random.Random(f"{seed}-{case['id']}-{name}"))
        got = signature(run(c2), None)
        want = signature(run(case), idmap) if idmap else base
        if got != want:
            out.append((case["id"], name, want[0], got[0]))
    if signature(run(case, known=case["as_of"])) != base:
        out.append((case["id"], "known_default", base[0], "differs"))
    return out


def sweep(seeds=range(1000, 1020), invariance_seeds=(2000, 2001, 2002)):
    """Larger robustness sweep used for the README numbers. Returns a dict of counts and any failures."""
    from .generator import property_cases, vehicle_cases
    gen = lambda s: property_cases(seed=s) + vehicle_cases(seed=s + 1)
    key_fail, n_key = [], 0
    for s in seeds:
        for c in gen(s):
            n_key += 1
            r = run_checks(build(c), c["asset"], c["as_of"], pack=c["pack"])
            if r["verdict"] != c["label"]: key_fail.append((s, c["id"], c["label"], r["verdict"]))
    inv_fail, n_inv = [], 0
    for s in invariance_seeds:
        for c in gen(s):
            n_inv += len(TRANSFORMS) + 1
            inv_fail += check_case(c, seed=s)
    return dict(fresh_cases=n_key, key_failures=key_fail, invariance_checks=n_inv, invariance_failures=inv_fail)


if __name__ == "__main__":
    print(sweep())
