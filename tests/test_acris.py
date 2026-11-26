# Made-up names in the shapes found in the real register (the real names stay out of the repository).
from vestigium.acris import same, group_match, to_case
from vestigium.engine import run_checks
from vestigium.whatif import build


def test_name_matching_is_stated_and_conservative():
    assert same("ARDEN, MAVIS", "MAVIS ARDEN, AS EXECUTRIX")
    assert same("QUILL, WREN L", "QUILL, WREN")
    assert same("ELM ROW PROPERTIES LLC", "ELM ROW PROPERTIES, LLC")
    assert same("FENWICK, OTTO G", "OTTO GRAY FENWICK")
    assert not same("ARDEN, JUNE ROSE", "MAVIS ARDEN REVOCABLE TRUST")     # same family, different party
    assert same("DE LAMB, LUC", "DELAMB, LUC")                              # a space inside a surname (the NYC false alarm, now matched)


def test_a_real_shaped_chain_is_checked_by_the_same_rules():
    d = lambda e, r, s, b: dict(effective=e, recorded=r, sellers=s, buyers=b)
    ok = [d("2004-01-01", "2004-02-01", ["ONE, ANN"], ["SMITH, JANE"]), d("2010-05-01", "2010-06-01", ["SMITH, JANE M"], ["DOE, JOHN"])]
    bad = ok[:1] + [d("2010-05-01", "2010-06-01", ["STRANGER, AL"], ["DOE, JOHN"])]
    for deeds, want in ((ok, "clean"), (bad, "defective")):
        c = to_case(1, deeds)
        assert run_checks(build(c), "A1", c["as_of"])["verdict"] == want
    assert group_match(["NORTH REALTY LLC"], ["NORTH REALTY LLC & SOUTH FUTURE REALTY CORP."])


def test_register_quirks_seen_in_philadelphia():
    assert same("S E B M INC", "S E B M INC")                      # all one-letter tokens
    assert same("ROSA'S 1997 LLC", "ROSAS 1997 LLC")               # apostrophe
    assert same("SECRETARY OF HOUSING AND URBAN DEVELOPME", "SECRETARY OF HOUSING AND URBAN DEVELOPMENT")   # 40-char field cut
    assert not same("NORTH HOLDINGS LLC", "NORTH HOLDING CORP")    # close is not the same; a person decides


def test_philadelphia_categories_are_stated_rules():
    from vestigium.philly import category
    prev = dict(buyers=["KOWALSKI KRZYSZTOF"])
    assert category(dict(type="DEED SHERIFF", sellers=["SHERIFF OF PHILA"]), prev).startswith("sheriff")
    assert category(dict(type="DEED", sellers=["KOWALSKI ANNA EXR"]), prev).startswith("estate")
    assert category(dict(type="DEED", sellers=["KOWALSKI KRZSYTOF"]), prev).startswith("probable spelling")
    assert category(dict(type="DEED", sellers=["KOWALSKI ANNA"]), prev).startswith("related name")
    assert category(dict(type="DEED", sellers=["NOVAK PETRA"]), prev) == "no apparent connection"


def test_impossible_register_dates_are_caught():
    from vestigium.philly import _ok
    assert _ok("2016-05-07T00:00:00Z") and not _ok("206-05-07T") and not _ok(None) and not _ok("0209-09-14")
