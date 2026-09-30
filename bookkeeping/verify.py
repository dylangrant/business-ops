"""Code-side check of what the agent reports: the saved PDF exists and its text shows the reported total."""
import re
import subprocess
from decimal import Decimal
from pathlib import Path

PDFTOTEXT = "pdftotext"


def pdf_text(pdf: Path) -> str:
    out = subprocess.run([PDFTOTEXT, "-layout", str(pdf), "-"], capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        raise ValueError(f"pdftotext failed: {out.stderr.strip()[:200]}")
    return out.stdout


def amounts_in(text: str) -> set[Decimal]:
    """Every money-looking number: 1,234.56 / $1234.56 / 545.51."""
    found = set()
    for m in re.finditer(r"(?<![\d.])\$?\s?(\d{1,3}(?:,\d{3})+|\d+)\.(\d{2})(?!\d)", text):
        found.add(Decimal(m.group(1).replace(",", "") + "." + m.group(2)))
    return found


def check_bill(pdf: str | Path, amount_total) -> tuple[bool, str]:
    """(ok, reason). Not ok -> the ledger row is written as needs_review with this reason."""
    pdf = Path(pdf)
    if not pdf.is_file() or pdf.stat().st_size == 0:
        return False, f"bill PDF missing: {pdf}"
    try:
        text = pdf_text(pdf)
    except (ValueError, subprocess.TimeoutExpired) as e:
        return False, str(e)
    if not text.strip():
        return False, "bill PDF has no text (scanned image?)"
    want = Decimal(str(amount_total)).quantize(Decimal("0.01"))
    if want in amounts_in(text):
        return True, ""
    return False, f"reported total {want} not found in the bill PDF"
