from datetime import date
from decimal import Decimal

import pytest

from bookkeeping.ledger import Entry, Ledger


def entry(**kw):
    base = dict(name="Pacific Power", category="Utilities", txn_date=date(2026, 9, 8), amount=Decimal("545.51"),
                adjusted=Decimal("27.28"), deductible=Decimal("27.28"), due_to_owner=Decimal("27.28"), source="msg-1")
    return Entry(**{**base, **kw})


def test_add_and_dedupe(tmp_path):
    l = Ledger(tmp_path)
    assert l.add(entry()) is True
    assert l.add(entry()) is False                        # same Gmail id
    assert l.add(entry(source="msg-2")) is False          # same vendor/date/amount, different email
    assert len(l.rows()) == 1
    assert l.add(entry(source="msg-3", txn_date=date(2026, 10, 8))) is True


def test_failed_write_leaves_no_half_row(tmp_path, monkeypatch):
    l = Ledger(tmp_path)
    l.add(entry())
    before = l.path.read_text()
    import bookkeeping.ledger as mod
    monkeypatch.setattr(mod.os, "replace", lambda *a: (_ for _ in ()).throw(OSError("disk")))
    with pytest.raises(OSError):
        l.add(entry(source="msg-9", txn_date=date(2026, 11, 1)))
    assert l.path.read_text() == before
    assert not list(tmp_path.glob("*.tmp"))


def test_balance_ignores_reviews_and_reimbursed(tmp_path):
    l = Ledger(tmp_path)
    l.add(entry())
    l.add(entry(source="m2", txn_date=date(2026, 10, 1), due_to_owner=Decimal("10.00")))
    l.add(entry(source="m3", txn_date=date(2026, 11, 1), due_to_owner=Decimal("99.00"), status="needs_review"))
    assert l.balance_owed() == Decimal("37.28")
    rows = l.rows()
    rows[1]["Reimbursed"] = "2026-11-15"
    l._write(rows)
    assert l.balance_owed() == Decimal("27.28")


def test_file_bill_naming_and_idempotent(tmp_path):
    pdf = tmp_path / "in.pdf"
    pdf.write_bytes(b"%PDF-1.4 x")
    l = Ledger(tmp_path / "root")
    p = l.file_bill(pdf, "Pacific Power", date(2026, 9, 8), Decimal("545.51"))
    assert p.name == "2026-09-08_pacific-power_545.51.pdf" and p.parent.name == "09"
    assert l.file_bill(pdf, "Pacific Power", date(2026, 9, 8), Decimal("545.51")) == p
