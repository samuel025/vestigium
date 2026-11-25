import json
from vestigium.dossier import dossier
from vestigium.extract import split_records
from vestigium.generator import all_cases
from vestigium.scan import render_scan, transcript_text, scan_analyze, TIERS, _strip_recorded

C = {c["id"]: c for c in all_cases()}


def fake(case, low=(), medium=(), drop_stamp=()):
    """A stand-in for the vision model that returns a perfect transcript, except for the confidence we assign."""
    def f(files):
        recs = []
        for rid, s in split_records(dossier(case, "clean")):
            body, rec = _strip_recorded(s)
            conf = "low" if rid in low else "medium" if rid in medium else "high"
            recs.append(dict(id=rid, text=body, annotation=f"RECORDED {rec}" if rec else None, annotation_date=None if rid in drop_stamp else rec,
                             confidence=conf, unsure=[dict(what="date", why="blurred digit")] if conf != "high" else []))
        return dict(pages=[dict(page=1, records=recs)]), dict(tokens=100)
    return f


def test_recording_date_lives_only_on_the_stamp_not_in_the_typed_text():
    files, recs = render_scan(dossier(C["prop-006"], "clean"), "phone", seed=1)
    assert all("recorded" not in body or "first recorded" in body for _, body, _ in recs)       # typed body carries no 'recorded <date>'
    assert any(rec for _, _, rec in recs) and files[0][1] == "image/jpeg"


def test_render_is_deterministic_and_has_all_three_tiers():
    d = dossier(C["prop-006"], "clean")
    for tier in ("phone", "poor"):                                        # photo tiers are byte-identical for the same seed
        a, _ = render_scan(d, tier, seed=3); b, _ = render_scan(d, tier, seed=3)
        assert [x[2] for x in a] == [x[2] for x in b]
    pdf = render_scan(d, "pdf")[0]
    assert len(pdf) == 1 and pdf[0][2][:5] == b"%PDF-" and pdf[0][1] == "application/pdf"     # (a PDF container embeds a timestamp, so only validity is checked)
    assert set(TIERS) == {"pdf", "phone", "poor"}


def test_perfect_transcript_gives_the_gold_verdict_and_no_warnings():
    c = C["prop-006"]
    out = scan_analyze([], as_of=c["as_of"], transcriber=fake(c))
    assert out["result"]["verdict"] == c["label"] and not out["warnings"] and out["reader"] == "rules"


def test_a_verdict_resting_on_a_low_confidence_record_says_so():
    c = C["prop-006"]                                                    # PROP-AUTH at T4: the proof is the deed P4 and the power of attorney PAU
    out = scan_analyze([], as_of=c["as_of"], transcriber=fake(c, low={"P4"}))
    assert out["result"]["verdict"] == "defective"
    assert any("P4" in w and "LOW confidence" in w for w in out["warnings"])
    assert out["scan"]["low_confidence"] == {"P4": 1}


def test_low_confidence_on_an_irrelevant_record_does_not_cry_wolf():
    c = C["prop-006"]
    out = scan_analyze([], as_of=c["as_of"], transcriber=fake(c, low={"X0"}))
    assert not any("rests on record" in w for w in out["warnings"])


def test_clean_verdict_with_low_confidence_records_is_not_presented_as_safe():
    c = C["prop-003"]                                                    # clean chain
    out = scan_analyze([], as_of=c["as_of"], transcriber=fake(c, low={"P2"}))
    assert out["result"]["verdict"] == "clean" and any("CLEAN" in w and "P2" in w for w in out["warnings"])


def test_an_unreadable_stamp_never_invents_a_recording_date():
    c = C["prop-006"]
    ans, _ = fake(c, drop_stamp={"P2"})([])
    text, low, flags = transcript_text(ans)
    p2 = dict(split_records(text))["P2"]
    assert "2016-02-08" not in p2 and "recorded" not in p2.replace("first recorded", "")      # the date is left out, not guessed


def test_scan_pipeline_makes_no_network_call_when_the_transcript_is_canonical(monkeypatch):
    import vestigium.llm as llm
    def boom(*a, **k): raise AssertionError("network call")
    monkeypatch.setattr(llm, "ask", boom); monkeypatch.setattr(llm, "ask_vision", boom)
    c = C["prop-006"]
    assert scan_analyze([], as_of=c["as_of"], transcriber=fake(c))["result"]["verdict"] == "defective"
