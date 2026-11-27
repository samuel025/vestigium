"""The real-record benchmark's plumbing: the labeller never sees the engine's answer; labels are validated; scoring is right."""
import json
import pytest
import vestigium.real_bench as rb


@pytest.fixture
def tmp_items(tmp_path, monkeypatch):
    items = [dict(id="L001", earlier={}, later={}, _engine_flagged=True), dict(id="L002", earlier={}, later={}, _engine_flagged=False),
             dict(id="L003", earlier={}, later={}, _engine_flagged=True), dict(id="L004", earlier={}, later={}, _engine_flagged=False)]
    for name in ("ITEMS", "LABELS", "LLM"):
        monkeypatch.setattr(rb, name, tmp_path / f"{name}.json")
    rb.ITEMS.write_text(json.dumps(items))
    monkeypatch.setattr(rb, "ROOT", tmp_path); (tmp_path / "results").mkdir()
    return items


def test_the_page_never_sees_the_engines_answer(tmp_items):
    assert all(not any(k.startswith("_") for k in it) for it in rb.public_items())


def test_labels_are_validated(tmp_items):
    assert rb.save_label("L001", "different") == 1
    with pytest.raises(ValueError): rb.save_label("L999", "same")
    with pytest.raises(ValueError): rb.save_label("L002", "maybe")


def test_scoring(tmp_items):
    for i, l in [("L001", "different"), ("L002", "same"), ("L003", "variant"), ("L004", "different")]:
        rb.save_label(i, l)
    e = rb.score()["engine"]
    # flagged L001 (true break) and L003 (a spelling variant: false alarm); accepted L002 (right) and L004 (a missed break)
    assert (e["true_breaks_found"], e["false_alarms"], e["correct_links"], e["breaks_missed"]) == (1, 1, 1, 1)
    assert e["precision"] == 50.0 and e["recall"] == 50.0 and e["accuracy"] == 50.0
