import shutil
import subprocess
from decimal import Decimal

import pytest

from bookkeeping.verify import amounts_in, check_bill

needs_tools = pytest.mark.skipif(not (shutil.which("pdftotext") and shutil.which("cupsfilter")), reason="needs pdftotext + cupsfilter")


def test_amounts_in_formats():
    t = "Amount due $1,234.56  Previous 545.51  kWh 1234  Acct 00012345  Total: $ 80.00"
    assert amounts_in(t) == {Decimal("1234.56"), Decimal("545.51"), Decimal("80.00")}


def test_missing_and_empty_file(tmp_path):
    ok, why = check_bill(tmp_path / "nope.pdf", "1.00")
    assert not ok and "missing" in why
    (tmp_path / "empty.pdf").write_bytes(b"")
    assert not check_bill(tmp_path / "empty.pdf", "1.00")[0]


@needs_tools
def test_real_pdf_match_and_mismatch(tmp_path):
    txt = tmp_path / "bill.txt"
    txt.write_text("Pacific Power\nStatement date 09/08/2026\nAmount due $545.51\n")
    pdf = tmp_path / "bill.pdf"
    pdf.write_bytes(subprocess.run(["cupsfilter", str(txt)], capture_output=True).stdout)
    assert check_bill(pdf, "545.51") == (True, "")
    ok, why = check_bill(pdf, Decimal("545.15"))
    assert not ok and "545.15" in why
