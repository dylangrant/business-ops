import base64
from datetime import date
from decimal import Decimal

from bookkeeping import summary
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
    assert s["attachments"] == []
    assert "Missing files: pp.pdf" in s["body"]


def test_empty_month(tmp_path):
    s = build(Ledger(tmp_path), "2026-10")
    assert "No bills recorded" in s["body"] and s["subject"] == "ph27 bills 2026-10: $0.00 owed to you"
    assert s["attachments"] == []


def test_attaches_pdf_and_txt(tmp_path):
    l = Ledger(tmp_path)
    (tmp_path / "pp.pdf").write_bytes(b"%PDF-1.4 bill")
    (tmp_path / "rent.txt").write_bytes(b"rent receipt")
    add(l, source="a", document=str(tmp_path / "pp.pdf"))
    add(l, source="b", name="Rent", document="rent.txt", txn_date=date(2026, 9, 9))  # relative -> ledger root
    s = build(l, "2026-09")
    assert s["attachments"] == [
        {"filename": "pp.pdf", "mimeType": "application/pdf", "data": base64.b64encode(b"%PDF-1.4 bill").decode()},
        {"filename": "rent.txt", "mimeType": "text/plain", "data": base64.b64encode(b"rent receipt").decode()},
    ]
    assert "pp.pdf" in s["body"] and "rent.txt" in s["body"]
    assert "Missing files" not in s["body"] and "Not attached" not in s["body"]


def test_other_extension_is_octet_stream(tmp_path):
    l = Ledger(tmp_path)
    (tmp_path / "x.png").write_bytes(b"png")
    add(l, source="a", document=str(tmp_path / "x.png"))
    assert build(l, "2026-09")["attachments"][0]["mimeType"] == "application/octet-stream"


def test_missing_file_skipped_and_named(tmp_path):
    l = Ledger(tmp_path)
    (tmp_path / "ok.pdf").write_bytes(b"ok")
    add(l, source="a", document=str(tmp_path / "gone.pdf"))
    add(l, source="b", document=str(tmp_path / "ok.pdf"), txn_date=date(2026, 9, 9))
    s = build(l, "2026-09")
    assert [a["filename"] for a in s["attachments"]] == ["ok.pdf"]
    assert "Missing files: gone.pdf" in s["body"]


def test_size_cap_leaves_later_files_unattached(tmp_path, monkeypatch):
    monkeypatch.setattr(summary, "MAX_ATTACH_BYTES", 10)
    l = Ledger(tmp_path)
    for i, size in enumerate([6, 6, 1], start=1):  # 2nd busts the cap; 3rd would fit but is skipped too
        (tmp_path / f"f{i}.pdf").write_bytes(b"x" * size)
        add(l, source=str(i), document=str(tmp_path / f"f{i}.pdf"), txn_date=date(2026, 9, i))
    s = build(l, "2026-09")
    assert [a["filename"] for a in s["attachments"]] == ["f1.pdf"]
    assert "Not attached (size limit): f2.pdf, f3.pdf" in s["body"]
