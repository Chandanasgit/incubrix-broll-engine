from app.queries import build_queries


def q(text, **kw):
    return build_queries(text, **kw)["queries"]


def test_bank_money_context():
    assert q("The bank keeps it safe.")[0] == "bank building finance"


def test_bank_river_context():
    assert "river bank nature" in q("We sat on the bank of the river.")


def test_cloud_computing_context():
    assert "data center servers technology" in q("Cloud apps make tracking easy.")


def test_cloud_sky_context():
    assert "clouds sky" in q("A cloud drifted across the blue sky.")


def test_mouse_and_python_meanings():
    assert "computer mouse desk" in q("Click the mouse on your desk.")
    assert "python snake" in q("The python slithers through the jungle.")
    assert "programming code laptop" in q("Python is a programming language.")


def test_numbers_become_chart_query():
    assert "growth chart graph business" in q("Sales grew 40% in 2025.")


def test_abstract_trust():
    assert "handshake partnership" in q("Trust is earned slowly.")


def test_avoid_list_drops_queries():
    res = build_queries("Alcohol sales grew.", avoid=["alcohol"])
    assert all("alcohol" not in x for x in res["queries"])
    assert any("avoided" in n for n in res["notes"])


def test_never_returns_empty():
    assert q("")
