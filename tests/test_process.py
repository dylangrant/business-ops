import shutil
import subprocess
from datetime import date
from decimal import Decimal

import pytest

from bookkeeping.allocate import load_rules
from bookkeeping.ledger import Ledger
from bookkeeping.process import Email, amount_from_email, process

RULES = load_rules()


def test_amount_from_email():
    assert amount_from_email("Your receipt. Amount paid $20.00. Thanks") == Decimal("20.00")
    assert amount_from_email("Total due: $1,234.56") == Decimal("1234.56")
    assert amount_from_email("Your bill is ready to view.") is None
    assert amount_from_email("Total: $10.00 ... Amount due $12.00") is None


def test_email_only_vendor_recorded_and_paid_by_ph27(tmp_path):
    l = Ledger(tmp_path)
    r = process(Email("m1", "Anthropic <invoice+statements@mail.anthropic.com>", "Your receipt", date(2026, 9, 5), "Amount paid $20.00"), RULES, l)
    assert r["status"] == "recorded"
    row = l.rows()[0]
    assert (row["Name"], row["Prorated Deductible Amount"], row["Due To Owner"], row["Paid From"]) == ("Claude", "20.00", "0.00", "Bluevine")
    assert process(Email("m1", "x@anthropic.com", "Your receipt", date(2026, 9, 5), "Amount paid $20.00"), RULES, l)["status"] == "duplicate"


def test_unlabeled_email_goes_to_review_then_can_be_resolved(tmp_path):
    l = Ledger(tmp_path)
    assert process(Email("m2", "service@usaa.com", "Your renters policy bill", date(2026, 9, 1), "Your bill is ready."), RULES, l)["status"] == "needs_review"
    r = process(Email("m2", "service@usaa.com", "Your renters policy bill", date(2026, 9, 1), "Amount due $68.52"), RULES, l)
    assert r["status"] == "recorded" and r["share"] == "3.43"
    assert [x["Status"] for x in l.rows()] == ["recorded"]


def test_unknown_sender_ignored(tmp_path):
    assert process(Email("m3", "news@shop.com", "", date(2026, 9, 1), ""), RULES, Ledger(tmp_path))["status"] == "ignored"


class FakeFetcher:
    def __init__(self, reply): self.reply, self.calls = reply, []
    def run(self, vendor, start, vault, hint=""): self.calls.append((vendor, start, vault)); return self.reply


@pytest.mark.skipif(not (shutil.which("pdftotext") and shutil.which("cupsfilter")), reason="needs pdftotext + cupsfilter")
def test_portal_vendor_verified_and_filed(tmp_path):
    media = tmp_path / "media"; media.mkdir()
    txt = tmp_path / "b.txt"; txt.write_text("Pacific Power\nAmount due $545.51\n")
    (media / "abc.pdf").write_bytes(subprocess.run(["cupsfilter", str(txt)], capture_output=True).stdout)
    l = Ledger(tmp_path / "root")
    f = FakeFetcher({"status": "saved", "billDate": "2026-09-08", "amountTotal": 545.51, "pdfPath": "FILE:/home/node/x/abc.pdf"})
    r = process(Email("m4", "noreply@pacificpower.net", "Your bill", date(2026, 9, 9), ""), RULES, l, fetcher=f, media_dir=media)
    assert r == {"status": "recorded", "vendor": "Pacific Power", "amount": "545.51", "share": "27.28"}
    assert f.calls[0][2] == "utilities-expenses"
    assert l.rows()[0]["Document"].endswith("2026-09-08_pacific-power_545.51.pdf")
    # wrong amount reported -> review, not recorded
    f2 = FakeFetcher({"status": "saved", "billDate": "2026-10-08", "amountTotal": 999.99, "pdfPath": "FILE:/x/abc.pdf"})
    assert process(Email("m5", "noreply@pacificpower.net", "", date(2026, 10, 9), ""), RULES, l, fetcher=f2, media_dir=media)["status"] == "needs_review"


def test_portal_fetch_failure_goes_to_review(tmp_path):
    l = Ledger(tmp_path)
    r = process(Email("m6", "x@nwnatural.com", "", date(2026, 9, 1), ""), RULES, l, fetcher=FakeFetcher({"status": "guard_stopped", "notes": "payments"}))
    assert r["status"] == "needs_review" and "guard_stopped" in l.rows()[0]["Notes"]


def test_forwarded_and_subject_filters():
    from bookkeeping.process import vendor_for
    assert vendor_for(RULES, "ivygahn@gmail.com", "Fwd: Your bill", "---------- Forwarded message ---------\nFrom: Pacific Power <noreply@pacificpower.net>")["key"] == "pacific_power"
    assert vendor_for(RULES, "ivygahn@gmail.com", "dinner?", "see you at 7") is None
    assert vendor_for(RULES, "USAA.Customer.Service@mailcenter.usaa.com", "Deposit received", "") is None
    assert vendor_for(RULES, "USAA.Customer.Service@mailcenter.usaa.com", "Your renters policy bill is ready", "")["key"] == "insurance"
    assert vendor_for(RULES, "invoice+statements@mail.anthropic.com", "Your receipt from Anthropic, PBC", "")["key"] == "claude"
