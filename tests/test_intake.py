from vestigium.generator import all_cases
from vestigium.dossier import dossier
from vestigium.extract import read_rules, assemble
from vestigium.intake_bench import judge, gold_where, score_ir

CASES = all_cases()


def test_regex_roundtrip_reproduces_gold_verdict_and_location():
    """The clean dossier states every fact the rules need: reading it back must reproduce the gold finding exactly."""
    bad = []
    for c in CASES:
        ir = read_rules(dossier(c, "clean"))
        v, where, err = judge(c, ir)
        if v != c["label"] or where != gold_where(c) or score_ir(c, ir)["record_exact"] != 1:
            bad.append((c["id"], c["label"], v, err))
    assert not bad, bad[:5]


def test_unreadable_text_is_never_clean():
    ir = read_rules("[P1] some unparseable paragraph about nothing")
    v, _, _ = judge(CASES[0], ir)
    assert v == "inconclusive"


def test_auto_fix_reaches_clean_wherever_the_gold_key_has_a_fix():
    from vestigium.intake import analyze
    bad = [c["id"] for c in CASES if c["key"]["fix"] and analyze(dossier(c, "clean"), reader="rules")["fix_verdict"] != "clean"]
    assert not bad, bad
