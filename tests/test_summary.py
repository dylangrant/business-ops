from datetime import date
from decimal import Decimal

from bookkeeping.ledger import Entry, Ledger
from bookkeeping.summary import build


def add(l, **kw):
    base = dict(name="Pacific Power", category="Utilities", txn_date=date(2026, 9, 8), amount=Decimal("545.51"),
                adjusted=Decimal("27.28"), deductible=Decimal("27.28"), due_to_owner=Decimal("27.28"))
    l.add(Entry(**{**base, **kw}))


def test_summary(tmp_path):
    l = Ledger(tmp_path)
    add(l, source="a", document="/b/pp.pdf")
    add(l, source="b", name="Rent", category="Rent", amount=Decimal("3520"), adjusted=Decimal("176"),
        deductible=Decimal("176"), due_to_owner=Decimal("176"), txn_date=date(2026, 9, 1))
    add(l, source="c", name="Claude", category="Dues and Subscriptions", amount=Decimal("20"), adjusted=Decimal("20"),
        deductible=Decimal("20"), due_to_owner=Decimal("0"), txn_date=date(2026, 9, 5))
    add(l, source="d", name="NW Natural", txn_date=date(2026, 9, 20), status="needs_review", notes="reported total not in PDF")
    add(l, source="e", txn_date=date(2026, 8, 8))
    s = build(l, "2026-09")
    assert s["subject"] == "ph27 bills 2026-09: $203.28 owed to you, 1 need you"
    assert "Total owed to you (unreimbursed): $230.56" in s["body"]
    assert "(paid by ph27)" in s["body"] and "reported total not in PDF" in s["body"]
    assert "Utilities                    $27.28" in s["body"]
    assert s["attachments"] == ["/b/pp.pdf"]


def test_empty_month(tmp_path):
    s = build(Ledger(tmp_path), "2026-10")
    assert "No bills recorded" in s["body"] and s["subject"] == "ph27 bills 2026-10: $0.00 owed to you"
