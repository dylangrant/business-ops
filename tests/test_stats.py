import json
import threading
import urllib.error
import urllib.request
from datetime import date
from decimal import Decimal
from http.server import ThreadingHTTPServer

import pytest

from bookkeeping.allocate import load_rules
from bookkeeping.ledger import Entry, Ledger
from bookkeeping.stats import build


def add(l, **kw):
    base = {"name": "Pacific Power", "category": "Utilities", "txn_date": date(2026, 9, 8), "amount": Decimal("545.51"),
                "adjusted": Decimal("27.28"), "deductible": Decimal("27.28"), "due_to_owner": Decimal("27.28")}
    l.add(Entry(**{**base, **kw}))


RULES = {
    "fixed_monthly": [{"key": "rent", "name": "Rent", "vendor": "rent"}],
    "vendors": [
        {"key": "rent", "match": ["rent"], "category": "Rent"},
        {"key": "pacific_power", "match": ["pacific power"], "category": "Utilities"},
        {"key": "nw_natural", "match": ["nw natural"], "category": "Utilities"},
        {"key": "claude", "match": ["claude"], "category": "Dues and Subscriptions"},
    ],
}


def test_month_totals(tmp_path):
    l = Ledger(tmp_path)
    add(l, source="a")
    add(l, source="c", name="Claude", category="Dues and Subscriptions", amount=Decimal(20), adjusted=Decimal(20),
        deductible=Decimal(20), due_to_owner=Decimal(0), txn_date=date(2026, 9, 5))
    add(l, source="e", txn_date=date(2026, 8, 8))   # other month
    s = build(l, RULES, "2026-09")
    assert s["business_spend"] == "47.28" and s["due_to_owner"] == "27.28" and s["month"] == "2026-09"


def test_empty_month_is_zeros(tmp_path):
    s = build(Ledger(tmp_path), RULES, "2026-10")
    assert (s["business_spend"], s["due_to_owner"], s["needs_review"]) == ("0.00", "0.00", 0)


def test_needs_review_excluded_from_totals_but_counted(tmp_path):
    l = Ledger(tmp_path)
    add(l, source="a")
    add(l, source="d", name="NW Natural", txn_date=date(2026, 9, 20), status="needs_review")
    s = build(l, RULES, "2026-09")
    assert s["business_spend"] == "27.28" and s["due_to_owner"] == "27.28" and s["needs_review"] == 1
    assert "nw_natural" in s["missing_bills"]   # a review row is not a recorded bill


def test_missing_bills(tmp_path):
    l = Ledger(tmp_path)
    add(l, source="a")
    assert build(l, RULES, "2026-09")["missing_bills"] == ["Rent", "nw_natural"]
    add(l, source="fixed:rent:2026-09", name="Rent", category="Rent", txn_date=date(2026, 9, 1))
    add(l, source="n", name="NW Natural", txn_date=date(2026, 9, 12))
    assert build(l, RULES, "2026-09")["missing_bills"] == []


def test_real_rules_empty_month_lists_expected_bills(tmp_path):
    missing = build(Ledger(tmp_path), load_rules(), "2026-09")["missing_bills"]
    assert {"Rent", "T-Mobile", "USAA Renters Insurance", "pacific_power", "internet"} <= set(missing)


@pytest.mark.parametrize("month", ["2026-13", "26-09", "", None, 202609])
def test_bad_month(tmp_path, month):
    with pytest.raises(ValueError):
        build(Ledger(tmp_path), RULES, month)


@pytest.fixture
def server(tmp_path, monkeypatch):
    monkeypatch.setenv("BOOKKEEPING_TOKEN", "secret")
    monkeypatch.setenv("PH27_LEDGER_ROOT", str(tmp_path))
    import importlib

    from service import server as srv
    importlib.reload(srv)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), srv.H)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    add(Ledger(tmp_path), source="a")
    yield f"http://127.0.0.1:{httpd.server_port}/stats"
    httpd.shutdown()


def post(url, body, token="secret"):
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_endpoint_returns_stats(server):
    code, body = post(server, {"month": "2026-09"})
    assert code == 200 and body["ok"] is True
    assert body["business_spend"] == "27.28" and body["needs_review"] == 0 and "Rent" in body["missing_bills"]


def test_endpoint_requires_bearer(server):
    assert post(server, {"month": "2026-09"}, token="wrong")[0] == 401


def test_endpoint_bad_month_is_400(server):
    code, body = post(server, {"month": "nope"})
    assert code == 400 and body["ok"] is False
    assert post(server, {})[0] == 400
